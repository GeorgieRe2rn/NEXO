"""Calendario real y seguimiento público ESPN, sin credenciales ni cargos.

Endpoint público sin SLA: se informa fuente y antigüedad; nunca se ruedan fechas.
Las consultas se comparten entre usuarios y se conservan partidos/pronósticos.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import logging
import math

import httpx
from sqlalchemy.orm import Session

from app.domain.identity import norm_name
from app.etl.calendar import aware, kickoff_iso, parse_iso, utcnow, display_window, scoreboard_dates
from app.infrastructure.db.models import ApiCache, FeedState, ForecastSnapshot, ForecastSelection, League, Match, MatchStat, Team

logger = logging.getLogger(__name__)
from app.services.competition_registry import LEAGUES, EXTENDED_COMPETITIONS
HISTORY_LEAGUES = {"MX":{"LIGA MX"}, "PL":{"PREMIER LEAGUE"}, "PD":{"LALIGA", "LA LIGA", "LALIGA EA SPORTS"}, "SA":{"SERIE A"}, "MLS":{"MLS"}}
BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
from app.services.feed_lock import feed_lock as _lock


def get_json(url: str, params: dict) -> dict:
    with httpx.Client(timeout=20, headers={"Accept": "application/json"}) as client:
        res = client.get(url, params=params)
        res.raise_for_status()
        data = res.json()
    if not isinstance(data, dict) or data.get("error") or data.get("code") == 400:
        raise ValueError("Respuesta inválida del proveedor")
    return data


def map_status(status: dict) -> str:
    kind = status.get("type") or {}
    name = (kind.get("name") or "").upper()
    for word, mapped in [("POSTPON", "POSTPONED"), ("CANCEL", "CANCELLED"), ("SUSPEND", "SUSPENDED"), ("ABANDON", "CANCELLED"), ("DELAY", "DELAYED")]:
        if word in name:
            return mapped
    if kind.get("completed") or kind.get("state") == "post":
        return "FINISHED"
    return "LIVE" if kind.get("state") == "in" else "SCHEDULED"


def number(value):
    try:
        n = float(str(value).replace("%", ""))
        return n if math.isfinite(n) and n >= 0 else None
    except (ValueError, TypeError):
        return None


def resolve_team(db: Session, league: League, blob: dict) -> Team:
    ext = int(blob["id"])
    team = db.query(Team).filter(Team.league_id == league.id, Team.espn_id == ext).first()
    if not team:
        candidates = db.query(Team).filter(Team.league_id == league.id, Team.espn_id.is_(None)).all()
        names = {norm_name(blob.get("displayName", "")), norm_name(blob.get("shortDisplayName", ""))} - {""}
        exact = [t for t in candidates if norm_name(t.name) in names or norm_name(t.short_name) in names]
        if len(exact) == 1:
            team = exact[0]
        else:
            acronym = blob.get("abbreviation")
            hits = [t for t in candidates if acronym and t.tla == acronym]
            team = hits[0] if len(hits) == 1 else None
    if not team:
        team = Team(league_id=league.id, name=blob["displayName"], short_name=blob.get("shortDisplayName") or blob["displayName"], tla=blob.get("abbreviation") or "—")
        db.add(team)
    team.espn_id = ext
    team.name = blob.get("displayName") or team.name
    team.short_name = blob.get("shortDisplayName") or blob.get("displayName") or team.short_name
    team.tla = blob.get("abbreviation") or team.tla
    logos = blob.get("logos") or []
    team.logo_url = blob.get("logo") or (logos[0].get("href") if logos else None) or team.logo_url
    db.flush()
    return team


def persist_event(db: Session, league: League, event: dict, fetched_at: datetime) -> Match | None:
    comp = (event.get("competitions") or [None])[0]
    if not comp or not event.get("id") or not (comp.get("date") or event.get("date")):
        return None
    competitors = comp.get("competitors") or []
    h = next((c for c in competitors if c.get("homeAway") == "home"), None)
    a = next((c for c in competitors if c.get("homeAway") == "away"), None)
    if not h or not a or h.get("team", {}).get("id") == a.get("team", {}).get("id"):
        return None
    home, away = resolve_team(db, league, h["team"]), resolve_team(db, league, a["team"])
    ident = str(event["id"])
    match = db.query(Match).filter(Match.provider == "espn", Match.provider_id == ident).first()
    if not match:
        match = Match(external_id=-int(ident), league_id=league.id, home_team_id=home.id, away_team_id=away.id)
        db.add(match)
    match.provider, match.provider_id = "espn", ident
    match.kickoff = parse_iso(comp.get("date") or event["date"])
    match.home_team_id, match.away_team_id = home.id, away.id
    match.status = map_status(comp.get("status") or event.get("status") or {})
    match.venue = (comp.get("venue") or {}).get("fullName") or match.venue
    match.verified_at = fetched_at
    live = dict(match.live_data or {})
    source_status=comp.get("status") or {}
    source_clock=source_status.get("displayClock")
    if live.get("clock")!=source_clock or not live.get("clock_reported_at"):
        live["clock_reported_at"]=kickoff_iso(fetched_at)
    live["clock_running"]=match.status=="LIVE" and not any(word in ((source_status.get("type") or {}).get("name") or "").upper() for word in ("HALFTIME","BREAK","DELAY","SUSPEND","INTERRUPT","SHOOTOUT"))
    live.update({"clock": source_clock,
                 "time_confirmed": comp.get("timeValid", event.get("timeValid", True)),
                 "source_url": f"https://www.espn.com/soccer/match/_/gameId/{ident}",
                 "season": (event.get("season") or {}).get("year")})
    match.live_data = live
    def score(c):
        value = c.get("score")
        return number(value.get("value")) if isinstance(value, dict) else number(value)
    if match.status in {"LIVE", "FINISHED", "SUSPENDED"}:
        hg, ag = score(h), score(a)
        match.home_goals = int(hg) if hg is not None else None
        match.away_goals = int(ag) if ag is not None else None
    else:
        match.home_goals = match.away_goals = None
    db.flush()
    return match


STAT_NAMES = {"possessionPct": "possession", "totalShots": "shots", "shotsOnTarget": "shots_on_target", "wonCorners": "corners", "yellowCards": "yellows", "redCards": "reds", "foulsCommitted": "fouls"}


def apply_summary(db: Session, match: Match, data: dict, now: datetime) -> None:
    header = data.get("header") or {}
    # Una respuesta de otro encuentro nunca puede sobrescribir este partido.
    if str(header.get("id")) != match.provider_id:
        raise ValueError("El resumen no corresponde al encuentro")
    event = dict(header)
    updated = persist_event(db, match.league, event, now)
    if updated is None:
        raise ValueError("Resumen sin encuentro válido")
    live = dict(match.live_data or {})
    stats = {}
    live["period"] = ((header.get("competitions") or [{}])[0].get("status") or {}).get("period")
    for row in (data.get("boxscore") or {}).get("teams") or []:
        tid = str((row.get("team") or {}).get("id"))
        side = "home" if tid == str(match.home_team.espn_id) else "away" if tid == str(match.away_team.espn_id) else None
        if side:
            stats[side] = {STAT_NAMES[s["name"]]: number(s.get("displayValue")) for s in row.get("statistics") or [] if s.get("name") in STAT_NAMES}
    events = {}
    raw_events = list(data.get("keyEvents") or [])
    raw_events += [c.get("play") for c in data.get("commentary") or [] if c.get("play")]
    for e in raw_events:
        kind = (e.get("type") or {}).get("type") or "event"
        if not any(k in kind.lower() for k in ("goal", "corner", "yellow", "red", "substitution", "penalty", "var", "foul")):
            continue
        events[str(e.get("id"))] = {"id": str(e.get("id")), "type": kind,
            "minute": (e.get("clock") or {}).get("displayValue") or "—",
            "seconds": (e.get("clock") or {}).get("value") or 0,
            "text": e.get("text") or e.get("shortText") or (e.get("type") or {}).get("text"),
            "team": (e.get("team") or {}).get("displayName") or (match.home_team.name if str((e.get("team") or {}).get("id"))==str(match.home_team.espn_id) else match.away_team.name if str((e.get("team") or {}).get("id"))==str(match.away_team.espn_id) else None),
            "team_id": (e.get("team") or {}).get("id"),
            "player": next(((p.get("athlete") or {}).get("displayName") for p in e.get("participants") or []), None)}
    live.update({"stats": stats, "events": sorted(events.values(), key=lambda e: e["seconds"], reverse=True), "details_at": kickoff_iso(now)})
    if match.league.code in EXTENDED_COMPETITIONS:
        from app.services.global_form import extract_history
        live["global_history"] = extract_history(data, match)
    # Eventos y marcador pueden llegar en diferentes instantes del proveedor.
    goals = {}
    for e in data.get("keyEvents") or []:
        if e.get("scoringPlay") and not e.get("shootout"):
            tid = str((e.get("team") or {}).get("id"))
            goals[tid] = goals.get(tid, 0) + 1
    live["score_pending_confirmation"] = (
        goals.get(str(match.home_team.espn_id), 0) > (match.home_goals or 0)
        or goals.get(str(match.away_team.espn_id), 0) > (match.away_goals or 0))
    match.live_data = live
    if match.status == "FINISHED" and match.home_goals is not None and match.away_goals is not None:
        from app.ml.form import estimate_xg
        for side, other, tid, gf, ga in [("home","away",match.home_team_id,match.home_goals,match.away_goals),("away","home",match.away_team_id,match.away_goals,match.home_goals)]:
            row = stats.get(side) or {}
            opponent = stats.get(other) or {}
            st = db.query(MatchStat).filter_by(match_id=match.id,team_id=tid).first()
            if st is None:
                st = MatchStat(match_id=match.id,team_id=tid)
                db.add(st)
            st.goals, st.goals_against = gf, ga
            st.result = "W" if gf > ga else "L" if gf < ga else "D"
            for field in ("shots","shots_on_target","corners","yellows","reds","fouls"):
                setattr(st,field,int(row.get(field) or 0))
            st.possession = row.get("possession") if row.get("possession") is not None else 50
            st.xg = estimate_xg(st.shots,st.shots_on_target,gf)
            st.xga = estimate_xg(int(opponent.get("shots") or 0),int(opponent.get("shots_on_target") or 0),ga)
        db.flush()
    # Carga los last-5 que el proveedor identifica como de esta misma competición.
    for group in data.get("lastFiveGames") or []:
        focus = group.get("team") or {}
        for past in group.get("events") or []:
            if not past.get("id") or not past.get("gameDate") or parse_iso(past["gameDate"]) >= aware(match.kickoff):
                continue
            if (past.get("leagueAbbreviation") or "").upper() not in HISTORY_LEAGUES.get(match.league.code,set()):
                continue
            opponent = past.get("opponent") or {}
            blobs = {str(focus.get("id")): focus, str(opponent.get("id")): opponent}
            hid, aid = str(past.get("homeTeamId")), str(past.get("awayTeamId"))
            hg, ag = number(past.get("homeTeamScore")), number(past.get("awayTeamScore"))
            if hid not in blobs or aid not in blobs or hg is None or ag is None:
                continue
            p = persist_event(db, match.league, {"id":past["id"], "date":past["gameDate"], "competitions":[{"date":past["gameDate"], "status":{"type":{"state":"post", "completed":True}}, "competitors":[{"homeAway":"home", "team":blobs[hid],"score":str(hg)}, {"homeAway":"away","team":blobs[aid],"score":str(ag)}]}]}, now)
            if p:
                for tid, gf, ga in [(p.home_team_id,hg,ag),(p.away_team_id,ag,hg)]:
                    st = db.query(MatchStat).filter_by(match_id=p.id, team_id=tid).first()
                    if not st:
                        # Marcador observado, demás valores imputados. El detalle declara esa limitación.
                        from app.ml.form import estimate_xg
                        db.add(MatchStat(match_id=p.id,team_id=tid,goals=int(gf),goals_against=int(ga),xg=estimate_xg(0,0,int(gf)),xga=estimate_xg(0,0,int(ga)),result="W" if gf>ga else "L" if gf<ga else "D"))


def sync_feed(db: Session, *, force_calendar: bool = False) -> dict:
    if not _lock.acquire(blocking=False):
        return {"status": "busy"}
    try:
        from app.etl.fixtures import ensure_leagues
        leagues = ensure_leagues(db)
        for code,(_,name,country) in EXTENDED_COMPETITIONS.items():
            league=db.query(League).filter_by(code=code).first()
            if league is None:
                league=League(code=code,name=name,country=country,season=utcnow().year,is_active=True)
                db.add(league);db.flush()
            leagues[code]=league
        db.commit()
        now = utcnow()
        jobs = []
        states = {}
        for code, slug in LEAGUES.items():
            state = db.get(FeedState, code)
            if state is None:
                state = FeedState(code=code)
                db.add(state)
            states[code] = state
            if not force_calendar and state.attempted_at and now - aware(state.attempted_at) < timedelta(seconds=55):
                continue
            calendar = force_calendar or not state.calendar_at or now - aware(state.calendar_at) > timedelta(hours=3)
            dates = scoreboard_dates(now) if calendar else [(now+timedelta(days=offset)).strftime("%Y%m%d") for offset in (-1,0)]
            for day in dates:
                jobs.append((code, slug, day))
            state.attempted_at = now
        db.commit()
        errors = {}
        successes = set()
        def fetch(job):
            code, slug, day = job
            try:
                data = get_json(f"{BASE}/{slug}/scoreboard", {"dates": day, "limit": 100})
                if "events" not in data:
                    raise ValueError("Calendario sin lista de eventos")
                return code, data, None
            except Exception as exc:
                return code, None, type(exc).__name__
        updated = 0
        with ThreadPoolExecutor(max_workers=4) as executor:
            for code, data, error in executor.map(fetch, jobs):
                if error:
                    errors[code] = error
                    continue
                successes.add(code)
                for event in data.get("events") or []:
                    try:
                        with db.begin_nested():
                            if persist_event(db, leagues[code], event, now):
                                updated += 1
                    except (ValueError, KeyError, TypeError):
                        errors[code] = "Datos incompletos"
        db.commit()
        for code in successes | set(errors):
            state = states[code]
            state.status = "partial" if code in errors else "ok"
            state.message = f"ESPN público · {errors[code]}" if code in errors else "ESPN público · Sin garantía de latencia"
            if code not in errors:
                state.succeeded_at = now
                if len([j for j in jobs if j[0] == code]) > 2:
                    state.calendar_at = now
        for code in errors.keys() - successes:
            states[code].status = "error"
        db.commit()
        # Solo resúmenes necesarios: partidos en curso o próximos sin detalle previo.
        from sqlalchemy import or_, and_
        tracked = db.query(ForecastSnapshot.match_id).distinct()
        candidates = db.query(Match).filter(Match.provider == "espn", Match.kickoff < display_window(now)[1],
            or_(Match.kickoff >= now-timedelta(hours=4), and_(Match.id.in_(tracked),Match.kickoff >= now-timedelta(days=7)))).order_by(Match.kickoff).all()
        pending_ids = {mid for (mid,) in db.query(ForecastSnapshot.match_id).join(ForecastSelection, ForecastSelection.snapshot_id == ForecastSnapshot.id).filter(ForecastSelection.status == "PENDING").distinct()}
        wanted = [m for m in candidates if force_calendar or m.status == "LIVE" or not (m.live_data or {}).get("details_at") or (m.league.code in EXTENDED_COMPETITIONS and m.status == "SCHEDULED" and now-parse_iso(m.live_data["details_at"])>timedelta(hours=6)) or (m.status == "FINISHED" and (m.id in pending_ids or not (m.live_data or {}).get("final_details")))]
        def fetch_summary(m):
            try:
                return m.id, get_json(f"{BASE}/{LEAGUES[m.league.code]}/summary", {"event":m.provider_id}), None
            except Exception as exc:
                return m.id, None, type(exc).__name__
        # Carga relaciones antes de los hilos: ninguna sesión SQLAlchemy se comparte.
        for m in wanted:
            _ = m.league.code
        with ThreadPoolExecutor(max_workers=4) as executor:
            for mid, data, error in executor.map(fetch_summary, wanted):
                m = db.get(Match, mid)
                if error:
                    continue
                try:
                    with db.begin_nested():
                        apply_summary(db, m, data, now)
                        if m.status == "FINISHED":
                            m.live_data = {**(m.live_data or {}), "final_details": True}
                except (ValueError, KeyError, TypeError):
                    logger.exception("Resumen inválido para %s", mid)
        db.commit()
        fill_history(db, candidates, now)
        # Importación aislada: únicamente el historial de córners y amarillas.
        from app.services.count_history import backfill_count_history
        try:
            backfill_count_history(db,candidates,now)
        except Exception:
            db.rollback()
            logger.exception("No se pudo completar el historial de córners/amarillas; continúa la sincronización habitual")
        from app.services.knowledge import rebuild_knowledge
        from app.core.config import get_settings
        if get_settings().forecast_architecture == "legacy-v1":
            rebuild_knowledge(db)
        from app.services.forecasts import capture_forecasts, settle_forecasts, update_learning, record_automatic_selections
        settle_forecasts(db,candidates)
        update_learning(db)
        capture_forecasts(db,candidates)
        record_automatic_selections(db,candidates)
        return {"status":"ok" if not errors else "partial", "updated":updated, "errors":errors}
    finally:
        _lock.release()


def fill_history(db: Session, candidates: list[Match], now: datetime) -> None:
    """Completa las ventanas de liga cuando lastFiveGames mezcla partidos de copa."""
    from app.infrastructure.cache import cache_put
    from app.services.knowledge import _team_slices
    from app.ml.form import estimate_xg
    jobs = {}
    for m in candidates:
        if m.league.code in EXTENDED_COMPETITIONS:
            continue
        if m.status not in {"SCHEDULED", "LIVE"}:
            continue
        for team in (m.home_team, m.away_team):
            if len(_team_slices(db, team.id, m.kickoff)) < 5:
                season = (m.live_data or {}).get("season") or m.league.season
                jobs[team.id] = (team.id, m.league.code, team.espn_id, season)
    def fetch(job):
        tid, code, ext, season = job
        key = f"espn:history:{code}:{ext}:{season}"
        try:
            return job, key, get_json(f"{BASE}/{LEAGUES[code]}/teams/{ext}/schedule", {"season":season}), None
        except Exception as exc:
            return job, key, None, type(exc).__name__
    pending = []
    responses = []
    for job in jobs.values():
        tid,code,ext,season = job
        key = f"espn:history:{code}:{ext}:{season}"
        cached = db.get(ApiCache,key)
        if cached and aware(cached.expires_at) > now:
            responses.append((job,key,cached.payload,None))
        else:
            pending.append(job)
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses.extend(pool.map(fetch,pending))
    for (tid,code,ext,season),key,data,error in responses:
        if error or not isinstance(data.get("events"),list):
            continue
        league = db.query(League).filter_by(code=code).one()
        events = sorted(data["events"],key=lambda e:e.get("date") or "",reverse=True)
        for event in events:
            if (event.get("league") or {}).get("slug") != LEAGUES[code]:
                continue
            comp = (event.get("competitions") or [{}])[0]
            if not event.get("date") or parse_iso(event["date"]) >= now or map_status(comp.get("status") or {}) != "FINISHED":
                continue
            with db.begin_nested():
                match = persist_event(db,league,event,now)
                if not match or match.home_goals is None or match.away_goals is None:
                    continue
                for team_id,gf,ga in [(match.home_team_id,match.home_goals,match.away_goals),(match.away_team_id,match.away_goals,match.home_goals)]:
                    st = db.query(MatchStat).filter_by(match_id=match.id,team_id=team_id).first()
                    if not st:
                        db.add(MatchStat(match_id=match.id,team_id=team_id,goals=gf,goals_against=ga,xg=estimate_xg(0,0,gf),xga=estimate_xg(0,0,ga),result="W" if gf>ga else "L" if gf<ga else "D"))
        db.commit()
        if (tid,code,ext,season) in pending:
            cache_put(db,key,"espn","team/schedule",data,ttl_hours=3)


def feed_metadata(db: Session) -> dict:
    now = utcnow()
    states = {s.code:s for s in db.query(FeedState).all()}
    return {"server_time":kickoff_iso(now), "timezone":"America/Hermosillo", "refresh_seconds":60,
        "source":"ESPN · acceso público", "notice":"Las actualizaciones dependen del proveedor; pueden demorarse. No es un servicio oficial con SLA.",
        "leagues":[{"code":code,"status":states[code].status if code in states else "pending",
            "last_success":kickoff_iso(states[code].succeeded_at) if code in states else None,
            "message":states[code].message if code in states else "Sin sincronización",
            "stale":code not in states or not states[code].succeeded_at or now-aware(states[code].succeeded_at)>timedelta(minutes=3)} for code in LEAGUES]}

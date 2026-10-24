from __future__ import annotations

from app.services.global_form import form_payload as global_form_payload

from sqlalchemy import desc
from sqlalchemy.orm import Session, joinedload

from app.domain.identity import age_from_dob, club_fits_league, norm_name
from app.etl.calendar import aware, is_visible_upcoming, kickoff_iso, utcnow
from app.infrastructure.db.models import (
    EtlRun,
    League,
    Match,
    Player,
    PlayerFormSnapshot,
    Prediction,
    Team,
    TeamFormSnapshot,
)
from app.infrastructure.db.models import MatchStat, PlayerMatchStat
from app.services.knowledge import h2h_matches
from app.services.forecasts import match_forecasts, forecast_summary


def _team_payload(team: Team) -> dict:
    return {
        "id": team.id,
        "name": team.name,
        "short_name": team.short_name,
        "tla": team.tla,
        "logo_url": team.logo_url,
        "city": team.city,
        "stadium": team.stadium,
        "primary_color": team.primary_color,
        "secondary_color": team.secondary_color,
        "founded": team.founded,
        "website": team.website,
        "club_colors": team.club_colors,
        "coach_name": team.coach_name,
    }


def _face_from_squad(db: Session, team_id: int, player: Player) -> Player | None:
    """Solo devuelve un rostro si el nombre coincide de forma única en la plantilla."""
    squad = db.query(Player).filter(Player.team_id == team_id, Player.photo_url.isnot(None)).all()
    target = norm_name(player.name)
    exact = [p for p in squad if norm_name(p.name) == target]
    if len(exact) == 1:
        return exact[0]
    last = target.split()[-1] if target else ""
    if last and len(last) > 4:
        hits = [p for p in squad if norm_name(p.name).split()[-1:] == [last]]
        if len(hits) == 1:
            return hits[0]
    return None


def _last5_for_team(db: Session, team_id: int) -> dict[int, dict]:
    team = db.get(Team, team_id)
    q = (
        db.query(Match.id)
        .join(MatchStat, MatchStat.match_id == Match.id)
        .filter(
            MatchStat.team_id == team_id,
            Match.status == "FINISHED",
            Match.is_h2h_only.is_(False),
        )
    )
    q = q.filter(Match.external_id.isnot(None))
    if team is not None:
        q = q.filter(Match.league_id == team.league_id)
    match_ids = [row[0] for row in q.order_by(desc(Match.kickoff)).limit(5).all()]
    out: dict[int, dict] = {}
    if not match_ids:
        return out
    rows = (
        db.query(PlayerMatchStat)
        .filter(PlayerMatchStat.team_id == team_id, PlayerMatchStat.match_id.in_(match_ids))
        .all()
    )
    for r in rows:
        b = out.setdefault(
            r.player_id,
            {
                "minutes": 0,
                "goals": 0,
                "assists": 0,
                "rating": [],
                "yellows": 0,
                "reds": 0,
                "shots": 0,
                "shots_on_target": 0,
                "key_passes": 0,
            },
        )
        b["minutes"] += r.minutes
        b["goals"] += r.goals
        b["assists"] += r.assists
        b["rating"].append(r.rating)
        b["yellows"] += r.yellows
        b["reds"] += r.reds
        b["shots"] += r.shots
        b["shots_on_target"] += r.shots_on_target
        b["key_passes"] += r.key_passes
    for pid, b in out.items():
        games = max(1, len(b["rating"]))
        b["rating_avg"] = round(sum(b["rating"]) / games, 2)
        b["games"] = games
        del b["rating"]
    return out


def _player_payload(player: Player, recent: dict | None = None) -> dict:
    stats = player.season_stats or {}
    recent = recent or {}
    rating = stats.get("rating")
    return {
        "id": player.id,
        "name": player.name,
        "photo_url": player.photo_url,
        "position": player.position,
        "position_label": player.position_label or player.position,
        "nationality": player.nationality,
        "nationality_code": player.nationality_code,
        "date_of_birth": player.date_of_birth,
        "age": age_from_dob(player.date_of_birth, player.age) or None,
        "verified_at": stats.get("verified_at"),
        "stats_source": stats.get("source"),
        "season_label": stats.get("season_label"),
        "height_cm": player.height_cm or None,
        "weight_kg": player.weight_kg or None,
        "preferred_foot": player.preferred_foot if player.preferred_foot not in {None, "—"} else None,
        "shirt_number": player.shirt_number or None,
        "club": player.team.short_name if player.team else None,
        "injured": bool(player.injured),
        "injury": player.injury,
        "season": {
            "goals": stats.get("goals"),
            "assists": stats.get("assists"),
            "played": stats.get("played"),
            "penalties": stats.get("penalties"),
            "minutes": stats.get("minutes"),
            "yellows": stats.get("yellows"),
            "reds": stats.get("reds"),
            "shots": stats.get("shots"),
            "shots_on_target": stats.get("shots_on_target"),
            "rating": rating,
            "xg": stats.get("xg"),
            "xa": stats.get("xa"),
        },
        "recent": recent or None,
        "tabla": {
            "goles": stats.get("goals"),
            "asistencias": stats.get("assists"),
            "partidos": stats.get("played"),
            "penales": stats.get("penalties"),
            "minutos": stats.get("minutes"),
            "titular": stats.get("lineups"),
            "tiros": stats.get("shots"),
            "tiros_puerta": stats.get("shots_on_target"),
            "pases_clave": stats.get("key_passes"),
            "rating": rating,
            "xg": stats.get("xg"),
            "amarillas": stats.get("yellows"),
            "rojas": stats.get("reds"),
            "vallas": stats.get("clean_sheets"),
            "atajadas": stats.get("saves"),
            "goles_recibidos": stats.get("goals_conceded"),
            "faltas": stats.get("fouls"),
            "faltas_recibidas": stats.get("fouls_suffered"),
            "autogoles": stats.get("own_goals"),
            "suplente": stats.get("sub_ins"),
            "fueras_juego": stats.get("offsides"),
            "tiros_recibidos": stats.get("shots_faced"),
        },
    }


def team_squad(db: Session, team_id: int) -> list[dict]:
    rows = (
        db.query(Player)
        .filter(Player.team_id == team_id)
        .order_by(Player.position.asc(), Player.shirt_number.asc(), Player.name.asc())
        .all()
    )
    last5 = _last5_for_team(db, team_id)
    verified = [p for p in rows if (p.season_stats or {}).get("source") == "espn" and (p.season_stats or {}).get("verified_at")]
    if verified:
        latest = max((p.season_stats or {}).get("verified_at") for p in verified)
        verified = [p for p in verified if (p.season_stats or {}).get("verified_at") == latest]
    out = [_player_payload(p, last5.get(p.id)) for p in verified]
    out.sort(
        key=lambda r: (
            -int((r.get("tabla") or {}).get("minutos") or 0),
            -int((r.get("tabla") or {}).get("titular") or 0),
            -int((r.get("tabla") or {}).get("partidos") or 0),
            -int((r.get("tabla") or {}).get("goles") or 0),
            r.get("name") or "",
        )
    )
    return out


def _prediction_payload(pred: Prediction | None) -> dict | None:
    if not pred:
        return None
    from app.core.config import get_settings
    from app.services.market_pipeline import SCHEMA
    if get_settings().forecast_architecture == SCHEMA and pred.match.status == "SCHEDULED" and aware(pred.match.kickoff)>utcnow() and not pred.model_version.startswith(SCHEMA):
        return None
    return {
        "p_home": pred.p_home,
        "p_draw": pred.p_draw,
        "p_away": pred.p_away,
        "p_over_25": pred.p_over_25,
        "p_under_25": pred.p_under_25,
        "lambda_home": pred.lambda_home,
        "lambda_away": pred.lambda_away,
        "confidence": pred.confidence,
        "confidence_label": pred.confidence_label,
        "pick": pred.pick,
        "model_version": pred.model_version,
        "explanation": pred.explanation,
        "computed_at": kickoff_iso(pred.computed_at),
    }


def _form_payload(snap: TeamFormSnapshot | None) -> dict | None:
    if not snap:
        return None
    return {
        "form_string": snap.form_string,
        "matches_used": snap.matches_used,
        "points": snap.points,
        "gf_avg": snap.gf_avg,
        "ga_avg": snap.ga_avg,
        "xg_avg": None,
        "xga_avg": None,
        "shots_avg": None,
        "sot_avg": None,
        "possession_avg": None,
        "corners_avg": None,
        "cards_avg": None,
        "attack_index": None,
        "defense_index": None,
        "breakdown": {"notice":"Solo se muestran marcadores observados. No se publican xG proxy ni estadísticas imputadas."},
    }


def _key_player(db: Session, team_id: int, match_id: int) -> dict | None:
    snap = (
        db.query(PlayerFormSnapshot)
        .filter(
            PlayerFormSnapshot.team_id == team_id,
            PlayerFormSnapshot.as_of_match_id == match_id,
            PlayerFormSnapshot.is_key_player.is_(True),
        )
        .first()
    )
    if not snap:
        return None
    player = db.get(Player, snap.player_id)
    if not player:
        return None
    payload = _player_payload(
        player,
        {
            "minutes": snap.minutes,
            "goals": snap.goals,
            "assists": snap.assists,
            "rating_avg": snap.rating_avg,
            "yellows": snap.yellows,
            "reds": snap.reds,
            "shots": snap.shots,
            "form_score": snap.form_score,
        },
    )
    face = _face_from_squad(db, team_id, player)
    if face:
        payload["photo_url"] = face.photo_url
        if face.shirt_number:
            payload["shirt_number"] = face.shirt_number
        if face.nationality and face.nationality != "—":
            payload["nationality"] = face.nationality
            payload["nationality_code"] = face.nationality_code
        if face.age:
            payload["age"] = face.age
    else:
        payload["photo_url"] = None
    return payload


def list_leagues(db: Session, active_only: bool = False) -> list[dict]:
    from app.services.competition_registry import LEAGUES
    q = db.query(League).filter(League.code.in_(tuple(LEAGUES)))
    if active_only:
        q = q.filter(League.is_active.is_(True))
    rows = q.order_by(League.id).all()
    return [
        {
            "id": l.id,
            "code": l.code,
            "name": l.name,
            "country": l.country,
            "season": l.season,
            "logo_url": l.logo_url,
            "accent": l.accent,
            "is_active": bool(l.is_active),
        }
        for l in rows
    ]


STATUS_LABEL = {
    "SCHEDULED": "Por jugar",
    "LIVE": "En juego",
    "FINISHED": "Finalizado",
}


def _is_jornada_match(m: Match) -> bool:
    if m.external_id is None:
        return False
    if m.verified_at is None:
        return False
    if not is_visible_upcoming(m.kickoff, m.status):
        return False
    home, away, league = m.home_team, m.away_team, m.league
    if not home or not away or not league or not league.is_active:
        return False
    if home.league_id != m.league_id or away.league_id != m.league_id:
        return False
    if home.id == away.id:
        return False
    return club_fits_league(home.name, league.code) and club_fits_league(away.name, league.code)


def list_upcoming(db: Session, league_code: str | None = None) -> list[dict]:
    q = (
        db.query(Match)
        .options(
            joinedload(Match.home_team),
            joinedload(Match.away_team),
            joinedload(Match.league),
            joinedload(Match.prediction),
        )
        .join(League)
        .filter(
            Match.status.in_(("SCHEDULED", "LIVE")),
            Match.is_h2h_only.is_(False),
            League.is_active.is_(True),
        )
    )
    if league_code and league_code != "ALL":
        q = q.filter(League.code == league_code)
    matches = [m for m in q.order_by(Match.kickoff.asc()).all() if _is_jornada_match(m)]

    out = []
    for m in matches:
        home_form = (
            db.query(TeamFormSnapshot)
            .filter(TeamFormSnapshot.as_of_match_id == m.id, TeamFormSnapshot.team_id == m.home_team_id)
            .first()
        )
        away_form = (
            db.query(TeamFormSnapshot)
            .filter(TeamFormSnapshot.as_of_match_id == m.id, TeamFormSnapshot.team_id == m.away_team_id)
            .first()
        )
        out.append(
            {
                "id": m.id,
                "kickoff": kickoff_iso(m.kickoff),
                "venue": m.venue,
                "matchday": m.matchday,
                "status": m.status,
                "status_label": STATUS_LABEL.get(m.status, m.status),
                "league": {
                    "code": m.league.code,
                    "name": m.league.name,
                    "country": m.league.country,
                    "logo_url": m.league.logo_url,
                    "accent": m.league.accent,
                },
                "home": _team_payload(m.home_team),
                "away": _team_payload(m.away_team),
                "prediction": _prediction_payload(m.prediction),
                "home_form": home_form.form_string if home_form else "—",
                "away_form": away_form.form_string if away_form else "—",
                "home_key_player": (_key_player(db, m.home_team_id, m.id) or {}).get("name"),
                "away_key_player": (_key_player(db, m.away_team_id, m.id) or {}).get("name"),
            }
        )
    return out


def get_match_detail(db: Session, match_id: int) -> dict | None:
    m = (
        db.query(Match)
        .options(
            joinedload(Match.home_team),
            joinedload(Match.away_team),
            joinedload(Match.league),
            joinedload(Match.prediction),
        )
        .filter(Match.id == match_id)
        .one_or_none()
    )
    if not m:
        return None
    home_form = (
        db.query(TeamFormSnapshot)
        .filter(TeamFormSnapshot.as_of_match_id == m.id, TeamFormSnapshot.team_id == m.home_team_id)
        .first()
    )
    away_form = (
        db.query(TeamFormSnapshot)
        .filter(TeamFormSnapshot.as_of_match_id == m.id, TeamFormSnapshot.team_id == m.away_team_id)
        .first()
    )
    h2h = []
    for h in h2h_matches(db, m.home_team_id, m.away_team_id, 3):
        if h.id == m.id or aware(h.kickoff) >= aware(m.kickoff):
            continue
        h2h.append(
            {
                "id": h.id,
                "kickoff": kickoff_iso(h.kickoff),
                "home": h.home_team.short_name,
                "away": h.away_team.short_name,
                "home_tla": h.home_team.tla,
                "away_tla": h.away_team.tla,
                "home_goals": h.home_goals,
                "away_goals": h.away_goals,
            }
        )
    return {
        "id": m.id,
        **_live_payload(m),
        "kickoff": kickoff_iso(m.kickoff),
        "venue": m.venue,
        "matchday": m.matchday,
        "status": m.status,
        "status_label": _live_payload(m)["status_label"],
        "league": {
            "code": m.league.code,
            "name": m.league.name,
            "country": m.league.country,
            "logo_url": m.league.logo_url,
            "accent": m.league.accent,
        },
        "home": {
            **_team_payload(m.home_team),
            "form": global_form_payload(m,"home") or (_form_payload(home_form) if home_form else _form_before(db, m.home_team_id, m.kickoff)),
            "key_player": _key_player(db, m.home_team_id, m.id),
            "squad": team_squad(db, m.home_team_id),
        },
        "away": {
            **_team_payload(m.away_team),
            "form": global_form_payload(m,"away") or (_form_payload(away_form) if away_form else _form_before(db, m.away_team_id, m.kickoff)),
            "key_player": _key_player(db, m.away_team_id, m.id),
            "squad": team_squad(db, m.away_team_id),
        },
        "prediction": _prediction_payload(m.prediction),
        "forecasts": match_forecasts(db,m),
        "h2h": h2h,
    }


def list_league_teams(db: Session, league_code: str) -> list[dict]:
    league = db.query(League).filter(League.code == league_code).one_or_none()
    if not league:
        return []
    teams = db.query(Team).filter(Team.league_id == league.id, Team.espn_id.isnot(None)).order_by(Team.name.asc()).all()
    # Los antecedentes pueden incluir clubes de temporadas anteriores.
    from app.infrastructure.db.models import ApiCache
    directory=db.get(ApiCache,f"espn:directory:{league_code}")
    member_ids=set((directory.payload or {}).get("team_ids",[])) if directory else set()
    if member_ids:
        teams=[t for t in teams if str(t.espn_id) in member_ids]
    out = []
    for t in teams:
        squad = team_squad(db, t.id)
        out.append({**_team_payload(t), "squad": squad, "squad_size": len(squad)})
    return out


def list_league_players(db: Session, league_code: str) -> list[dict]:
    teams = list_league_teams(db, league_code)
    rows = []
    for t in teams:
        for p in t.get("squad") or []:
            rows.append({**p, "team": {"id": t["id"], "name": t["short_name"] or t["name"], "logo_url": t["logo_url"], "tla": t["tla"]}})
    rows.sort(
        key=lambda r: (
            -int((r.get("tabla") or {}).get("minutos") or 0),
            -int((r.get("tabla") or {}).get("titular") or 0),
            -int((r.get("tabla") or {}).get("partidos") or 0),
            -int((r.get("tabla") or {}).get("goles") or 0),
            r.get("name") or "",
        )
    )
    return rows


def _gk_conceded(db: Session, league_id: int) -> dict[int, dict]:
    """Goles recibidos por portero en partidos oficiales de esa liga (mín. 45 min)."""
    rows = (
        db.query(PlayerMatchStat, MatchStat)
        .join(Match, Match.id == PlayerMatchStat.match_id)
        .join(
            MatchStat,
            (MatchStat.match_id == PlayerMatchStat.match_id)
            & (MatchStat.team_id == PlayerMatchStat.team_id),
        )
        .join(Player, Player.id == PlayerMatchStat.player_id)
        .join(Team, Team.id == Player.team_id)
        .filter(
            Team.league_id == league_id,
            Player.position == "GK",
            Match.status == "FINISHED",
            Match.league_id == league_id,
            Match.external_id.isnot(None),
            Match.is_h2h_only.is_(False),
            PlayerMatchStat.minutes >= 1,
        )
        .all()
    )
    out: dict[int, dict] = {}
    for pms, st in rows:
        bucket = out.setdefault(
            pms.player_id,
            {"goles_recibidos": 0, "goles_favor": 0, "partidos": 0, "minutos": 0},
        )
        bucket["goles_recibidos"] += int(st.goals_against or 0)
        bucket["goles_favor"] += int(st.goals or 0)
        bucket["partidos"] += 1
        bucket["minutos"] += int(pms.minutes or 0)
    for bucket in out.values():
        bucket["diferencia"] = bucket["goles_favor"] - bucket["goles_recibidos"]
    return out


def league_leaders(db: Session, league_code: str) -> dict:
    league = db.query(League).filter(League.code == league_code).one_or_none()
    players = list_league_players(db, league_code)
    top = None
    for p in players:
        goles = int((p.get("tabla") or {}).get("goles") or 0)
        if goles <= 0:
            continue
        if top is None or goles > int((top.get("tabla") or {}).get("goles") or 0):
            top = p
    gk = None
    if league:
        conceded = _gk_conceded(db, league.id)
        candidates = []
        for p in players:
            if p.get("position") != "GK":
                continue
            extra = conceded.get(p["id"])
            if extra and extra["partidos"] >= 1:
                avg = extra["goles_recibidos"] / extra["partidos"]
                candidates.append((avg, extra["goles_recibidos"], -extra["diferencia"], extra, p))
        if candidates:
            candidates.sort()
            extra, p = candidates[0][3], candidates[0][4]
            gk = {
                **p,
                "goles_recibidos": extra["goles_recibidos"],
                "goles_favor": extra["goles_favor"],
                "diferencia": extra["diferencia"],
                "partidos_portero": extra["partidos"],
            }
        if gk is None:
            with_sheets = [
                p
                for p in players
                if p.get("position") == "GK" and int((p.get("tabla") or {}).get("vallas") or 0) > 0
            ]
            if with_sheets:
                with_sheets.sort(key=lambda p: -int((p.get("tabla") or {}).get("vallas") or 0))
                best = with_sheets[0]
                gk = {
                    **best,
                    "goles_recibidos": None,
                    "goles_favor": None,
                    "diferencia": None,
                    "vallas": int((best.get("tabla") or {}).get("vallas") or 0),
                }
    return {"top_scorer": top, "least_conceded_gk": gk}


def admin_overview(db: Session, league_code: str = "ALL") -> dict:
    from app.infrastructure.db.models import FeedState
    upcoming = [m for m in list_feed_matches(db,league_code) if m["status"] == "SCHEDULED"]
    picks = {"LOCAL": 0, "EMPATE": 0, "VISITANTE": 0}
    conf = {"ALTA": 0, "MEDIA": 0, "BAJA": 0}
    for m in upcoming:
        p = m.get("prediction")
        if p:
            picks[p["pick"]] = picks.get(p["pick"], 0) + 1
            conf[p["confidence_label"]] = conf.get(p["confidence_label"], 0) + 1
    ligas = []
    roster = []
    for lg in list_leagues(db):
        if league_code != "ALL" and lg["code"] != league_code:
            continue
        teams = list_league_teams(db, lg["code"])
        people = [p for t in teams for p in t["squad"]]
        roster.extend(people)
        ligas.append({"code":lg["code"],"name":lg["name"],"equipos":len(teams),"jugadores":len(people)})
    last = db.query(FeedState).filter(FeedState.succeeded_at.isnot(None)).order_by(FeedState.succeeded_at.desc()).first()
    return {
        "jugadores":len(roster),
        "con_goles_oficiales":sum(1 for p in roster if (p["tabla"]["goles"] or 0)>0 or (p["tabla"]["asistencias"] or 0)>0),
        "con_foto":sum(bool(p["photo_url"]) for p in roster),
        "equipos":sum(l["equipos"] for l in ligas),
        "partidos_por_jugar":len(upcoming), "pronosticos":picks,"confianza":conf,"ligas":ligas,
        "ultima_sync":{"cuando":kickoff_iso(last.succeeded_at) if last else None,"que":"espn","ok":bool(last and last.status=="ok")},
        "proximos":upcoming[:8],
    }


def get_team_detail(db: Session, team_id: int) -> dict | None:
    team = db.get(Team, team_id)
    if not team:
        return None
    league = db.get(League, team.league_id)
    return {
        **_team_payload(team),
        "league": {
            "code": league.code if league else None,
            "name": league.name if league else None,
            "logo_url": league.logo_url if league else None,
        },
        "squad": team_squad(db, team.id),
        "espn_id": team.espn_id,
        "form": _current_form(db, team.id),
        "data_notice": "La plantilla y sus estadísticas pueden corresponder a una sincronización anterior. No representan alineaciones confirmadas.",
    }


def _current_form(db: Session, team_id: int) -> dict:
    return _form_before(db, team_id, utcnow())


def _form_before(db: Session, team_id: int, before) -> dict:
    from app.services.knowledge import _team_slices
    from app.ml.form import compute_team_form
    form = compute_team_form(team_id, _team_slices(db, team_id, before))
    return {"form_string":form.form_string,"matches_used":form.matches_used,"points":form.points if form.matches_used else None,"gf_avg":form.gf_avg if form.matches_used else None,"ga_avg":form.ga_avg if form.matches_used else None,"breakdown":{"notice":"Sin estadísticas publicadas adicionales; no se rellenan datos ausentes."}}


def _live_payload(m: Match) -> dict:
    live = m.live_data or {}
    age = (utcnow() - aware(m.verified_at)).total_seconds() if m.verified_at else None
    stale = age is None or age > 180
    labels = {"SCHEDULED":"Programado", "LIVE":"En vivo", "FINISHED":"Finalizado", "POSTPONED":"Pospuesto", "CANCELLED":"Cancelado", "SUSPENDED":"Suspendido", "DELAYED":"Retrasado"}
    status_label = "Estado por confirmar" if m.status == "LIVE" and stale else labels.get(m.status,m.status)
    if m.status == "SCHEDULED" and aware(m.kickoff) < utcnow():
        status_label = "Esperando confirmación"
    return {"home_goals":m.home_goals,"away_goals":m.away_goals,"live":live,
            "verified_at":kickoff_iso(m.verified_at),"source":m.provider,"stale":stale,
            "status_label": status_label}


def list_feed_matches(db: Session, league_code: str = "ALL") -> list[dict]:
    from app.etl.calendar import display_window
    from datetime import timedelta
    now = utcnow()
    query = db.query(Match).options(joinedload(Match.home_team),joinedload(Match.away_team),joinedload(Match.league),joinedload(Match.prediction)).join(League).filter(
        Match.provider == "espn", Match.verified_at.isnot(None), Match.is_h2h_only.is_(False),
        Match.kickoff >= now-timedelta(days=7), Match.kickoff < display_window(now)[1])
    if league_code != "ALL":
        query = query.filter(League.code == league_code)
    out = []
    for m in query.order_by(Match.kickoff).all():
        payload = _live_payload(m)
        # Programado con hora vencida no se convierte por inferencia en partido en vivo.
        if m.status == "SCHEDULED" and aware(m.kickoff) < now:
            payload["status_label"] = "Esperando confirmación"
        out.append({"id":m.id,"kickoff":kickoff_iso(m.kickoff),"status":m.status,**payload,
            "venue":m.venue,"matchday":m.matchday,
            "league":{"code":m.league.code,"name":m.league.name,"logo_url":m.league.logo_url},
            "home":_team_payload(m.home_team),"away":_team_payload(m.away_team),
            "prediction":_prediction_payload(m.prediction), "forecast":forecast_summary(db,m)})
    return out

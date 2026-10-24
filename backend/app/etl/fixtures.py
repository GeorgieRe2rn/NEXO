"""Sincroniza la jornada: solo torneos activos, fechas vivas, sin edición manual."""

from __future__ import annotations

import logging
from datetime import timedelta
from threading import Lock

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.etl.calendar import (
    FIXTURE_CACHE_HOURS,
    GRACE_HOURS,
    HORIZON_DAYS,
    STALE_AFTER_HOURS,
    aware,
    current_season_year,
    is_in_season,
    is_visible_upcoming,
    parse_iso,
    roll_kickoff,
    upcoming_window,
    utcnow,
)
from app.infrastructure.cache import cache_invalidate
from app.infrastructure.db.models import (
    EtlRun,
    League,
    Match,
    MatchStat,
    PlayerFormSnapshot,
    PlayerMatchStat,
    Prediction,
    Team,
    TeamFormSnapshot,
)
from app.domain.identity import club_fits_league
from app.seed.catalog import FIXTURES, LEAGUES, TEAMS
from app.services.knowledge import rebuild_knowledge

logger = logging.getLogger(__name__)
_SYNC_LOCK = Lock()


def ensure_leagues(db: Session) -> dict[str, League]:
    now = utcnow()
    out: dict[str, League] = {}
    for row in LEAGUES:
        lg = db.query(League).filter(League.code == row["code"]).one_or_none()
        if lg is None:
            payload = dict(row)
            payload["season"] = current_season_year(row["code"], now)
            payload["is_active"] = is_in_season(row["code"], now)
            lg = League(**payload)
            db.add(lg)
            db.flush()
        else:
            if not lg.logo_url:
                lg.logo_url = row.get("logo_url")
            if not lg.accent:
                lg.accent = row.get("accent") or lg.accent
        out[lg.code] = lg
    db.commit()
    return out


def mark_league_activity(db: Session, af=None, fd=None) -> dict[str, bool]:
    """Marca is_active / season. El calendario es la base; las APIs lo refinan."""
    now = utcnow()
    leagues = ensure_leagues(db)
    flags: dict[str, bool] = {}
    for code, lg in leagues.items():
        cal_active = is_in_season(code, now)
        season = current_season_year(code, now)
        api_active: bool | None = None
        try:
            if fd is not None and code in {"PL", "PD", "SA"} and fd.settings.has_football_data:
                info = fd.competition(code) or {}
                cs = info.get("currentSeason") or {}
                if cs:
                    start = parse_iso(cs.get("startDate"), now)
                    end = parse_iso(cs.get("endDate"), now)
                    if cs.get("startDate") and cs.get("endDate"):
                        api_active = start - timedelta(days=7) <= now <= end + timedelta(days=7)
                    if cs.get("startDate"):
                        season = start.year if start.month >= 8 else start.year
            if af is not None and lg.api_football_id and af.settings.has_api_football:
                cur = af.current_season(lg.api_football_id)
                if cur and cur.get("year"):
                    season = int(cur["year"])
                    start = parse_iso(cur.get("start"), now)
                    end = parse_iso(cur.get("end"), now)
                    if cur.get("start") and cur.get("end"):
                        api_active = start - timedelta(days=3) <= now <= end + timedelta(days=7)
                    elif cur.get("current") is False:
                        api_active = False
                    elif cur.get("current"):
                        api_active = True
        except Exception:
            logger.exception("No se pudo leer la temporada vigente de %s", code)
        lg.season = season
        lg.is_active = cal_active if api_active is None else (cal_active and api_active)
        flags[code] = bool(lg.is_active)
    db.commit()
    return flags


def _expired_scheduled(db: Session) -> list[Match]:
    now = utcnow()
    cutoff = now - timedelta(hours=GRACE_HOURS)
    rows = (
        db.query(Match)
        .filter(Match.status == "SCHEDULED", Match.is_h2h_only.is_(False))
        .all()
    )
    out = []
    for m in rows:
        kick = aware(m.kickoff)
        if kick is not None and kick <= now:
            out.append(m)
    return out


def _upcoming_visible(db: Session) -> int:
    now = utcnow()
    start, end = upcoming_window(now)
    n = 0
    rows = (
        db.query(Match)
        .join(League)
        .filter(
            Match.status.in_(("SCHEDULED", "LIVE")),
            Match.is_h2h_only.is_(False),
            League.is_active.is_(True),
        )
        .all()
    )
    for m in rows:
        kick = aware(m.kickoff)
        if is_visible_upcoming(m.kickoff, m.status) and _is_valid_league_match(m):
            n += 1
    return n


def _last_ok_age(db: Session, sources: tuple[str, ...] | None = None):
    q = db.query(EtlRun).filter(EtlRun.status == "ok")
    if sources:
        q = q.filter(EtlRun.source.in_(sources))
    last = q.order_by(EtlRun.id.desc()).first()
    if not last or not last.finished_at:
        return None
    finished = aware(last.finished_at)
    if finished is None:
        return None
    return utcnow() - finished


def _seed_jornada_without_api_ids(db: Session) -> bool:
    settings = get_settings()
    if not (settings.has_api_football or settings.has_football_data):
        return False
    return (
        db.query(Match)
        .filter(
            Match.status.in_(("SCHEDULED", "LIVE")),
            Match.is_h2h_only.is_(False),
            Match.external_id.is_(None),
        )
        .count()
        > 0
    )


def needs_refresh(db: Session) -> bool:
    age = _last_ok_age(db)
    if _seed_jornada_without_api_ids(db):
        live_age = _last_ok_age(db, ("calendar", "live"))
        if live_age is not None and live_age < timedelta(hours=FIXTURE_CACHE_HOURS):
            return False
        return True
    if _expired_scheduled(db) or _upcoming_visible(db) == 0:
        return age is None or age > timedelta(hours=FIXTURE_CACHE_HOURS)
    if age is None or age > timedelta(hours=STALE_AFTER_HOURS):
        return True
    return False


def _team_in_league(db: Session, league_id: int, tla: str, name: str | None = None) -> Team | None:
    team = db.query(Team).filter(Team.league_id == league_id, Team.tla == tla).one_or_none()
    if team and club_fits_league(team.name, db.get(League, league_id).code if db.get(League, league_id) else ""):
        return team
    if name:
        from app.domain.identity import fold

        target = fold(name)
        for row in db.query(Team).filter(Team.league_id == league_id).all():
            if fold(row.name) == target or fold(row.short_name) == target:
                return row
    return None


def _is_valid_league_match(m: Match) -> bool:
    home, away, league = m.home_team, m.away_team, m.league
    if not home or not away or not league:
        return False
    if home.league_id != m.league_id or away.league_id != m.league_id:
        return False
    if home.id == away.id:
        return False
    return club_fits_league(home.name, league.code) and club_fits_league(away.name, league.code)


def purge_synthetic_matches(db: Session) -> int:
    """Elimina partidos sin id externo: son seed o simulación, no cartelera oficial."""
    ids = [row[0] for row in db.query(Match.id).filter(Match.external_id.is_(None)).all()]
    if not ids:
        return 0
    db.query(Prediction).filter(Prediction.match_id.in_(ids)).delete(synchronize_session=False)
    db.query(TeamFormSnapshot).filter(TeamFormSnapshot.as_of_match_id.in_(ids)).delete(synchronize_session=False)
    db.query(PlayerFormSnapshot).filter(PlayerFormSnapshot.as_of_match_id.in_(ids)).delete(
        synchronize_session=False
    )
    db.query(PlayerMatchStat).filter(PlayerMatchStat.match_id.in_(ids)).delete(synchronize_session=False)
    db.query(MatchStat).filter(MatchStat.match_id.in_(ids)).delete(synchronize_session=False)
    db.query(Match).filter(Match.id.in_(ids)).delete(synchronize_session=False)
    db.commit()
    logger.info("purged synthetic matches=%s", len(ids))
    return len(ids)


def purge_invalid_jornada(db: Session) -> int:
    """Quita programados vencidos y partidos que no son de esa liga."""
    ids = []
    rows = (
        db.query(Match)
        .filter(Match.status.in_(("SCHEDULED", "LIVE")), Match.is_h2h_only.is_(False))
        .all()
    )
    for m in rows:
        if m.status == "SCHEDULED" and not is_visible_upcoming(m.kickoff, m.status):
            ids.append(m.id)
            continue
        if not _is_valid_league_match(m):
            ids.append(m.id)
    if not ids:
        return 0
    db.query(Prediction).filter(Prediction.match_id.in_(ids)).delete(synchronize_session=False)
    db.query(TeamFormSnapshot).filter(TeamFormSnapshot.as_of_match_id.in_(ids)).delete(synchronize_session=False)
    db.query(PlayerFormSnapshot).filter(PlayerFormSnapshot.as_of_match_id.in_(ids)).delete(
        synchronize_session=False
    )
    db.query(PlayerMatchStat).filter(PlayerMatchStat.match_id.in_(ids)).delete(synchronize_session=False)
    db.query(Match).filter(Match.id.in_(ids)).delete(synchronize_session=False)
    db.commit()
    return len(ids)


def _delete_scheduled(db: Session) -> int:
    rows = (
        db.query(Match)
        .filter(Match.status.in_(("SCHEDULED", "LIVE")), Match.is_h2h_only.is_(False))
        .all()
    )
    ids = [m.id for m in rows]
    if not ids:
        return 0
    db.query(Prediction).filter(Prediction.match_id.in_(ids)).delete(synchronize_session=False)
    db.query(TeamFormSnapshot).filter(TeamFormSnapshot.as_of_match_id.in_(ids)).delete(
        synchronize_session=False
    )
    db.query(PlayerFormSnapshot).filter(PlayerFormSnapshot.as_of_match_id.in_(ids)).delete(
        synchronize_session=False
    )
    db.query(PlayerMatchStat).filter(PlayerMatchStat.match_id.in_(ids)).delete(synchronize_session=False)
    db.query(Match).filter(Match.id.in_(ids)).delete(synchronize_session=False)
    db.flush()
    return len(ids)


def refresh_seed_upcoming(db: Session) -> dict:
    """Reescribe la jornada seed: solo ligas en temporada, fechas a partir de hoy."""
    now = utcnow()
    mark_league_activity(db)
    dropped = _delete_scheduled(db)
    catalog = {t["tla"]: t for t in TEAMS}
    leagues = {lg.code: lg for lg in db.query(League).all()}
    created = 0
    for home_tla, away_tla, iso, venue, md in FIXTURES:
        meta = catalog.get(home_tla)
        if not meta:
            continue
        code = meta["league"]
        lg = leagues.get(code)
        if not lg or not lg.is_active:
            continue
        away_meta = catalog.get(away_tla) or {}
        home = _team_in_league(db, lg.id, home_tla, meta.get("name") or meta.get("short_name"))
        away = _team_in_league(db, lg.id, away_tla, away_meta.get("name") or away_meta.get("short_name"))
        if not home or not away or home.league_id != lg.id or away.league_id != lg.id:
            continue
        kick = roll_kickoff(iso, now)
        db.add(
            Match(
                league_id=lg.id,
                home_team_id=home.id,
                away_team_id=away.id,
                kickoff=kick,
                status="SCHEDULED",
                venue=venue,
                matchday=md,
                is_h2h_only=False,
            )
        )
        created += 1
    db.commit()
    knowledge = rebuild_knowledge(db)
    return {
        "status": "seed_rolled",
        "dropped": dropped,
        "created": created,
        "horizon_days": HORIZON_DAYS,
        "knowledge": knowledge,
    }


def fill_missing_seed_jornada(db: Session) -> int:
    """Si una liga activa no trajo jornada de la API, usa los emparejamientos seed con fecha viva."""
    now = utcnow()
    start, end = upcoming_window(now)
    catalog = {t["tla"]: t for t in TEAMS}
    created = 0
    for lg in db.query(League).all():
        if not lg.is_active:
            continue
        visible = 0
        for m in (
            db.query(Match)
            .filter(
                Match.league_id == lg.id,
                Match.status.in_(("SCHEDULED", "LIVE")),
                Match.is_h2h_only.is_(False),
            )
            .all()
        ):
            if is_visible_upcoming(m.kickoff, m.status) and _is_valid_league_match(m):
                visible += 1
        if visible:
            continue
        expired_ids = [
            m.id
            for m in db.query(Match)
            .filter(
                Match.league_id == lg.id,
                Match.status.in_(("SCHEDULED", "LIVE")),
                Match.is_h2h_only.is_(False),
            )
            .all()
        ]
        if expired_ids:
            db.query(Prediction).filter(Prediction.match_id.in_(expired_ids)).delete(synchronize_session=False)
            db.query(TeamFormSnapshot).filter(TeamFormSnapshot.as_of_match_id.in_(expired_ids)).delete(
                synchronize_session=False
            )
            db.query(PlayerFormSnapshot).filter(PlayerFormSnapshot.as_of_match_id.in_(expired_ids)).delete(
                synchronize_session=False
            )
            db.query(Match).filter(Match.id.in_(expired_ids)).delete(synchronize_session=False)
        for home_tla, away_tla, iso, venue, md in FIXTURES:
            meta = catalog.get(home_tla)
            if not meta or meta["league"] != lg.code:
                continue
            away_meta = catalog.get(away_tla) or {}
            home = _team_in_league(db, lg.id, home_tla, meta.get("name") or meta.get("short_name"))
            away = _team_in_league(db, lg.id, away_tla, away_meta.get("name") or away_meta.get("short_name"))
            if not home or not away or home.league_id != lg.id or away.league_id != lg.id:
                continue
            if not club_fits_league(home.name, lg.code) or not club_fits_league(away.name, lg.code):
                continue
            db.add(
                Match(
                    league_id=lg.id,
                    home_team_id=home.id,
                    away_team_id=away.id,
                    kickoff=roll_kickoff(iso, now),
                    status="SCHEDULED",
                    venue=venue,
                    matchday=md,
                    is_h2h_only=False,
                )
            )
            created += 1
    if created:
        db.commit()
        logger.info("seed fill jornada=%s", created)
    return created


def ingest_active_live(db: Session) -> dict:
    from app.etl.hybrid import ingest_api_football, ingest_football_data
    from app.infrastructure.providers.api_football import ApiFootballProvider
    from app.infrastructure.providers.football_data import FootballDataProvider

    fd = FootballDataProvider(db)
    af = ApiFootballProvider(db)
    flags = mark_league_activity(db, af=af, fd=fd)
    n_fd = 0
    n_af = 0
    try:
        n_fd = ingest_football_data(db, fd) if fd.settings.has_football_data else 0
    except Exception:
        logger.exception("ingesta football-data falló")
        db.rollback()
    try:
        n_af = ingest_api_football(db, af) if af.settings.has_api_football else 0
    except Exception:
        logger.exception("ingesta API-Football falló")
        db.rollback()
    purge_synthetic_matches(db)
    knowledge = rebuild_knowledge(db)
    return {
        "status": "live",
        "active": flags,
        "rows_upserted": n_fd + n_af,
        "requests_made": fd.requests_made + af.requests_made,
        "cache_hits": fd.cache_hits + af.cache_hits,
        "knowledge": knowledge,
    }


def sync_active_calendar(db: Session, *, force: bool = False) -> dict:
    """Punto único: actualiza fechas cuando hace falta. Seguro para el scheduler."""
    if not _SYNC_LOCK.acquire(blocking=False):
        return {"status": "busy"}
    try:
        running = (
            db.query(EtlRun)
            .filter(EtlRun.status == "running")
            .order_by(EtlRun.id.desc())
            .first()
        )
        if running:
            started = aware(running.started_at)
            stale = started is None or utcnow() - started > timedelta(minutes=4)
            if not stale and not force:
                return {"status": "busy"}
            if stale:
                running.status = "error"
                running.finished_at = utcnow()
                running.notes = (running.notes or "") + " | stale-running"
                db.commit()
        purge_synthetic_matches(db)
        purge_invalid_jornada(db)
        if not force and not needs_refresh(db):
            mark_league_activity(db)
            return {"status": "fresh", "upcoming": _upcoming_visible(db)}

        if _expired_scheduled(db) or force:
            cache_invalidate(db, "af:fixtures:")
            cache_invalidate(db, "fd:competitions/")

        settings = get_settings()
        run = EtlRun(started_at=utcnow(), status="running", source="calendar")
        db.add(run)
        db.commit()
        try:
            if not (settings.has_api_football or settings.has_football_data):
                result = {"status": "missing_api_keys"}
            else:
                result = ingest_active_live(db)
            run.status = "ok" if result.get("status") != "error" else "error"
            run.finished_at = utcnow()
            run.requests_made = int(result.get("requests_made") or 0)
            run.cache_hits = int(result.get("cache_hits") or 0)
            run.rows_upserted = int(result.get("rows_upserted") or 0)
            run.notes = f"calendar {result.get('status')} upcoming={_upcoming_visible(db)}"
            db.commit()
            result["upcoming"] = _upcoming_visible(db)
            return result
        except Exception as exc:
            logger.exception("calendar sync failed")
            run.status = "error"
            run.finished_at = utcnow()
            run.notes = str(exc)
            db.commit()
            return {"status": "error", "upcoming": _upcoming_visible(db)}
    finally:
        _SYNC_LOCK.release()

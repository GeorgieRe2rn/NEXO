"""Identidad oficial (nombre + escudo) y plantillas completas por liga."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.domain.identity import age_from_dob, fold, map_position, nat_code, norm_name
from app.infrastructure.db.models import EtlRun, League, Player, Team
from app.infrastructure.providers.api_football import ApiFootballProvider
from app.infrastructure.providers.football_data import FootballDataProvider

logger = logging.getLogger(__name__)

FD_LEAGUES = ("PL", "PD", "SA")
AF_ROSTER_LEAGUES = {
    "MX": {"api_id": 262, "season": 2024},
    "MLS": {"api_id": 253, "season": 2024},
}
# Mapa de nombres seed → id correcto API-Football (el seed original tenía IDs cruzados).
NAME_TO_AF = {
    "club america": 2287,
    "america": 2287,
    "chivas": 2278,
    "chivas guadalajara": 2278,
    "guadalajara": 2278,
    "guadalajara chivas": 2278,
    "tigres": 2279,
    "tigres uanl": 2279,
    "monterrey": 2282,
    "rayados monterrey": 2282,
    "cruz azul": 2295,
    "pumas": 2286,
    "pumas unam": 2286,
    "u.n.a.m. - pumas": 2286,
    "inter miami": 9568,
    "inter miami cf": 9568,
    "lafc": 1616,
    "los angeles fc": 1616,
    "la galaxy": 1605,
    "los angeles galaxy": 1605,
    "seattle": 1595,
    "seattle sounders": 1595,
    "nycfc": 1604,
    "new york city": 1604,
    "new york city fc": 1604,
    "atlanta": 1608,
    "atlanta united": 1608,
    "atlanta united fc": 1608,
}


def _name_key(name: str) -> str:
    parts = [p for p in re.split(r"[\s.]+", fold(name)) if p]
    if not parts:
        return ""
    return f"{parts[0][0]}|{parts[-1]}"


def _photo_id_ok(photo: str | None, ext: int | None) -> bool:
    if not photo or not ext:
        return False
    return f"/{int(ext)}." in photo.replace("\\", "/")


def _upsert_player(
    db: Session,
    team: Team,
    *,
    ext: int | None,
    name: str,
    position_raw: str | None,
    nationality: str | None,
    dob: str | None,
    age: int | None,
    number: int | None,
    photo: str | None,
) -> Player:
    pos, label = map_position(position_raw)
    player = None
    if ext:
        hits = db.query(Player).filter(Player.external_id == ext, Player.team_id == team.id).all()
        player = hits[0] if hits else None
    if player is None:
        nk = _name_key(name)
        if nk:
            for cand in db.query(Player).filter(Player.team_id == team.id).all():
                if _name_key(cand.name) == nk:
                    player = cand
                    break
    if player is None:
        player = Player(team_id=team.id, name=name)
        db.add(player)
    # No pisar una ficha FotMob ya resuelta con un id de otro proveedor.
    if ext and (player.season_stats or {}).get("source") != "fotmob":
        player.external_id = ext
    if name and (not player.name or len(name) >= len(player.name)):
        player.name = name
    player.position = pos
    player.position_label = label
    player.nationality = nationality or player.nationality or "—"
    if nationality:
        player.nationality_code = nat_code(nationality)
    player.date_of_birth = dob or player.date_of_birth
    player.age = age or age_from_dob(dob, player.age or 0)
    if number:
        player.shirt_number = int(number)
    if photo and _photo_id_ok(photo, ext) and (player.season_stats or {}).get("source") != "fotmob":
        player.photo_url = photo
    return player


def _find_team(db: Session, league: League, *, ext: int | None, name: str, tla: str | None) -> Team | None:
    if ext:
        hit = db.query(Team).filter(Team.league_id == league.id, Team.external_id == ext).one_or_none()
        if hit:
            return hit
    if tla:
        hit = db.query(Team).filter(Team.league_id == league.id, Team.tla == tla[:8]).one_or_none()
        if hit:
            return hit
    target = norm_name(name)
    for team in db.query(Team).filter(Team.league_id == league.id).all():
        if norm_name(team.name) == target or norm_name(team.short_name) == target:
            return team
        if target in norm_name(team.name) or norm_name(team.name) in target:
            return team
    return None


def ingest_football_data_rosters(db: Session, fd: FootballDataProvider) -> int:
    n = 0
    for code in FD_LEAGUES:
        league = db.query(League).filter(League.code == code).one_or_none()
        if not league:
            continue
        payload = fd.get(f"competitions/{code}/teams")
        teams = payload.get("teams") or []
        for blob in teams:
            ext = blob.get("id")
            name = blob.get("name") or "Unknown"
            short = blob.get("shortName") or name
            tla = (blob.get("tla") or short)[:8]
            team = _find_team(db, league, ext=ext, name=name, tla=tla)
            if team is None:
                team = Team(league_id=league.id, name=name, short_name=short[:40], tla=tla.upper())
                db.add(team)
                db.flush()
            team.external_id = ext
            team.name = name
            team.short_name = short[:40]
            team.tla = tla.upper()
            team.logo_url = blob.get("crest") or team.logo_url
            team.stadium = blob.get("venue") or team.stadium
            team.founded = blob.get("founded") or team.founded
            team.website = blob.get("website") or team.website
            team.club_colors = blob.get("clubColors") or team.club_colors
            area = blob.get("area") or {}
            team.city = area.get("name") or team.city
            coach = blob.get("coach") or {}
            if coach.get("name"):
                team.coach_name = coach.get("name")
            for p in blob.get("squad") or []:
                _upsert_player(
                    db,
                    team,
                    ext=p.get("id"),
                    name=p.get("name") or "Jugador",
                    position_raw=p.get("position"),
                    nationality=p.get("nationality"),
                    dob=p.get("dateOfBirth"),
                    age=None,
                    number=None,
                    photo=None,
                )
                n += 1
        db.commit()
        logger.info("FD roster %s teams=%s", code, len(teams))
    return n


def ingest_api_football_rosters(db: Session, af: ApiFootballProvider, budget: int = 90) -> int:
    n = 0
    used = 0
    for code, meta in AF_ROSTER_LEAGUES.items():
        league = db.query(League).filter(League.code == code).one_or_none()
        if not league:
            continue
        data = af.get("teams", {"league": meta["api_id"], "season": meta["season"]})
        used += 1
        rows = data.get("response") or []
        af_by_id = {}
        af_by_name = {}
        for row in rows:
            tm = row.get("team") or {}
            tid = tm.get("id")
            name = tm.get("name") or ""
            af_by_id[tid] = tm
            af_by_name[norm_name(name)] = tm
        for team in db.query(Team).filter(Team.league_id == league.id).all():
            mapped = NAME_TO_AF.get(norm_name(team.name)) or NAME_TO_AF.get(norm_name(team.short_name))
            blob = af_by_id.get(mapped) if mapped else None
            if blob is None:
                blob = af_by_name.get(norm_name(team.name)) or af_by_name.get(norm_name(team.short_name))
            if blob is None:
                for key, tm in af_by_name.items():
                    if key in norm_name(team.name) or norm_name(team.name) in key:
                        blob = tm
                        break
            if not blob:
                continue
            team.external_id = blob.get("id")
            team.logo_url = blob.get("logo") or team.logo_url
            if blob.get("name"):
                # Conserva el nombre local si es más descriptivo, pero el escudo SIEMPRE va con el id correcto.
                team.short_name = (team.short_name or blob["name"])[:40]
        for tm in rows:
            blob = tm.get("team") or {}
            ext = blob.get("id")
            name = blob.get("name") or "Unknown"
            team = _find_team(db, league, ext=ext, name=name, tla=(name[:3] if name else "UNK"))
            if team is None:
                team = Team(
                    league_id=league.id,
                    external_id=ext,
                    name=name,
                    short_name=name[:40],
                    tla=name[:3].upper(),
                    logo_url=blob.get("logo"),
                    city=(tm.get("venue") or {}).get("city"),
                    stadium=(tm.get("venue") or {}).get("name"),
                )
                db.add(team)
                db.flush()
            else:
                team.external_id = ext
                team.logo_url = blob.get("logo") or team.logo_url
                team.city = team.city or (tm.get("venue") or {}).get("city")
                team.stadium = team.stadium or (tm.get("venue") or {}).get("name")
            if used >= budget:
                continue
            squad_payload = af.get("players/squads", {"team": ext})
            used += 1
            resp = squad_payload.get("response") or []
            players = (resp[0].get("players") or []) if resp else []
            for p in players:
                _upsert_player(
                    db,
                    team,
                    ext=p.get("id"),
                    name=p.get("name") or "Jugador",
                    position_raw=p.get("position"),
                    nationality=None,
                    dob=None,
                    age=p.get("age"),
                    number=p.get("number"),
                    photo=p.get("photo"),
                )
                n += 1
        db.commit()
        logger.info("AF roster %s used=%s players=%s", code, used, n)
    return n


def ingest_af_photos_for_europe(db: Session, af: ApiFootballProvider, budget: int = 40) -> int:
    """Fusiona fotos/números de API-Football 2024 sobre plantillas 2026/27 de football-data."""
    n = used = 0
    af_leagues = {"PL": 39, "PD": 140, "SA": 135}
    for code, api_id in af_leagues.items():
        if used >= budget:
            break
        league = db.query(League).filter(League.code == code).one_or_none()
        if not league:
            continue
        data = af.get("teams", {"league": api_id, "season": 2024})
        used += 1
        for row in data.get("response") or []:
            if used >= budget:
                break
            blob = row.get("team") or {}
            ext = blob.get("id")
            name = blob.get("name") or ""
            team = _find_team(db, league, ext=None, name=name, tla=None)
            if team is None:
                continue
            squad_payload = af.get("players/squads", {"team": ext})
            used += 1
            resp = squad_payload.get("response") or []
            players = (resp[0].get("players") or []) if resp else []
            roster = db.query(Player).filter(Player.team_id == team.id).all()
            by_norm = {norm_name(p.name): p for p in roster}
            by_nk = {_name_key(p.name): p for p in roster if _name_key(p.name)}
            for p in players:
                raw_name = p.get("name") or ""
                local = by_norm.get(norm_name(raw_name)) or by_nk.get(_name_key(raw_name))
                if local is None:
                    continue
                if (local.season_stats or {}).get("source") == "fotmob":
                    continue
                photo = p.get("photo")
                ext = p.get("id")
                if photo and _photo_id_ok(photo, ext):
                    local.photo_url = photo
                    if ext:
                        local.external_id = int(ext)
                if p.get("number"):
                    local.shirt_number = int(p["number"])
                if p.get("age") and not local.age:
                    local.age = int(p["age"])
                n += 1
        db.commit()
    return n


def run_roster_ingest(db: Session) -> dict:
    run = EtlRun(started_at=datetime.now(timezone.utc), status="running", source="rosters")
    db.add(run)
    db.commit()
    fd = FootballDataProvider(db)
    af = ApiFootballProvider(db)
    try:
        n_fd = ingest_football_data_rosters(db, fd) if fd.settings.has_football_data else 0
        n_af = ingest_api_football_rosters(db, af) if af.settings.has_api_football else 0
        n_ph = ingest_af_photos_for_europe(db, af, budget=35) if af.settings.has_api_football else 0
        run.status = "ok"
        run.finished_at = datetime.now(timezone.utc)
        run.requests_made = fd.requests_made + af.requests_made
        run.cache_hits = fd.cache_hits + af.cache_hits
        run.rows_upserted = n_fd + n_af
        run.notes = f"fd_players={n_fd} af_players={n_af} photos_merged={n_ph}"
        db.commit()
        return {
            "status": "ok",
            "players_football_data": n_fd,
            "players_api_football": n_af,
            "photos_merged": n_ph,
            "requests_made": run.requests_made,
            "cache_hits": run.cache_hits,
        }
    except Exception as exc:
        logger.exception("roster ingest failed")
        run.status = "error"
        run.finished_at = datetime.now(timezone.utc)
        run.notes = str(exc)
        db.commit()
        raise

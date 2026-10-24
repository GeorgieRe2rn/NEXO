"""Enriquece goles/asistencias (football-data scorers) y lesiones (API-Football)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.domain.identity import norm_name
from app.infrastructure.db.models import EtlRun, League, Player, Team
from app.infrastructure.providers.api_football import ApiFootballProvider
from app.infrastructure.providers.football_data import FootballDataProvider

logger = logging.getLogger(__name__)

FD_CODES = ("PL", "PD", "SA")
AF_INJURY = {"PL": 39, "PD": 140, "SA": 135, "MX": 262, "MLS": 253}


def _apply_to_player(players: list[Player], name: str) -> Player | None:
    """Solo nombre completo. Nunca por apellido: evita mezclar fichas y fotos."""
    target = norm_name(name)
    exact = [p for p in players if norm_name(p.name) == target]
    return exact[0] if len(exact) == 1 else None


def enrich_scorers(db: Session, fd: FootballDataProvider) -> int:
    n = 0
    for code in FD_CODES:
        league = db.query(League).filter(League.code == code).one_or_none()
        if not league:
            continue
        data = fd.get(f"competitions/{code}/scorers", {"limit": 200})
        roster = (
            db.query(Player)
            .join(Team, Team.id == Player.team_id)
            .filter(Team.league_id == league.id)
            .all()
        )
        by_team: dict[int, list[Player]] = {}
        for p in roster:
            by_team.setdefault(p.team_id, []).append(p)
        for row in data.get("scorers") or []:
            player_blob = row.get("player") or {}
            team_blob = row.get("team") or {}
            team = (
                db.query(Team)
                .filter(Team.league_id == league.id, Team.external_id == team_blob.get("id"))
                .one_or_none()
            )
            pool = by_team.get(team.id, roster) if team else roster
            player = _apply_to_player(pool, player_blob.get("name") or "")
            if not player:
                continue
            stats = dict(player.season_stats or {})
            stats.update(
                {
                    "goals": row.get("goals") or 0,
                    "assists": row.get("assists") or 0,
                    "played": row.get("playedMatches") or 0,
                    "penalties": row.get("penalties") or 0,
                    "source": "football-data-scorers",
                }
            )
            player.season_stats = stats
            n += 1
        db.commit()
    return n


def enrich_injuries(db: Session, af: ApiFootballProvider, budget: int = 5) -> int:
    n = used = 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=21)
    db.query(Player).update({Player.injured: False, Player.injury: None})
    db.commit()
    for code, league_id in AF_INJURY.items():
        if used >= budget:
            break
        league = db.query(League).filter(League.code == code).one_or_none()
        if not league:
            continue
        season = 2024
        data = af.get("injuries", {"league": league_id, "season": season})
        used += 1
        roster = (
            db.query(Player)
            .join(Team, Team.id == Player.team_id)
            .filter(Team.league_id == league.id)
            .all()
        )
        by_team: dict[str, list[Player]] = {}
        for p in roster:
            by_team.setdefault(norm_name(p.team.short_name if p.team else ""), []).append(p)
            by_team.setdefault(norm_name(p.team.name if p.team else ""), []).append(p)
        for row in data.get("response") or []:
            fx_date = (row.get("fixture") or {}).get("date")
            if fx_date:
                try:
                    when = datetime.fromisoformat(str(fx_date).replace("Z", "+00:00"))
                    if when < cutoff:
                        continue
                except ValueError:
                    continue
            pblob = row.get("player") or {}
            tblob = row.get("team") or {}
            pool = by_team.get(norm_name(tblob.get("name") or ""), roster)
            player = _apply_to_player(pool, pblob.get("name") or "")
            if not player:
                continue
            player.injured = True
            player.injury = (pblob.get("reason") or pblob.get("type") or "Lesión")[:160]
            n += 1
        db.commit()
    return n


def run_enrich(db: Session) -> dict:
    run = EtlRun(started_at=datetime.now(timezone.utc), status="running", source="enrich")
    db.add(run)
    db.commit()
    fd = FootballDataProvider(db)
    af = ApiFootballProvider(db)
    try:
        n_sc = enrich_scorers(db, fd) if fd.settings.has_football_data else 0
        n_in = enrich_injuries(db, af, budget=5) if af.settings.has_api_football else 0
        run.status = "ok"
        run.finished_at = datetime.now(timezone.utc)
        run.requests_made = fd.requests_made + af.requests_made
        run.cache_hits = fd.cache_hits + af.cache_hits
        run.rows_upserted = n_sc + n_in
        run.notes = f"scorers={n_sc} injuries={n_in}"
        db.commit()
        return {"status": "ok", "scorers": n_sc, "injuries": n_in, "requests_made": run.requests_made}
    except Exception as exc:
        logger.exception("enrich failed")
        run.status = "error"
        run.finished_at = datetime.now(timezone.utc)
        run.notes = str(exc)
        db.commit()
        raise

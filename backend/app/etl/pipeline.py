"""Pipeline ETL: Extract → Transform → Load → Knowledge (form snapshots + predicción).

Diseñado para el cupo gratuito:
- Cada request HTTP se cachea 12h en `api_cache`.
- Si un partido ya tiene `match_stats`, no se vuelve a pedir.
- Liga MX y MLS solo existen en API-Football; football-data.org es fallback europeo.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.etl.transform import parse_fixture, parse_player_stats, parse_team_stats
from app.infrastructure.db.models import (
    EtlRun,
    Match,
    MatchStat,
    Player,
    PlayerMatchStat,
    Team,
)
from app.infrastructure.providers.api_football import LEAGUES, ApiFootballProvider
from app.ml.form import estimate_xg
from app.services.knowledge import rebuild_knowledge

logger = logging.getLogger(__name__)


def _upsert_team(db: Session, league_id: int, blob: dict, color: str = "#00E5A8") -> Team | None:
    ext = blob.get("id")
    if not ext:
        return None
    team = db.query(Team).filter(Team.external_id == ext).one_or_none()
    if team is None:
        team = Team(
            external_id=ext,
            league_id=league_id,
            name=blob.get("name") or "Unknown",
            short_name=(blob.get("name") or "UNK")[:24],
            tla=(blob.get("name") or "UNK")[:3].upper(),
            logo_url=blob.get("logo"),
            primary_color=color,
        )
        db.add(team)
        db.flush()
    else:
        team.logo_url = blob.get("logo") or team.logo_url
        team.name = blob.get("name") or team.name
    return team


def _result(gf: int, ga: int) -> str:
    if gf > ga:
        return "W"
    if gf < ga:
        return "L"
    return "D"


def run_live_etl(db: Session) -> dict:
    settings = get_settings()
    run = EtlRun(
        started_at=datetime.now(timezone.utc),
        status="running",
        source="live",
    )
    db.add(run)
    db.commit()

    provider = ApiFootballProvider(db)
    upserts = 0

    try:
        from app.infrastructure.db.models import League

        for code, meta in LEAGUES.items():
            league = db.query(League).filter(League.code == code).one_or_none()
            if league is None:
                continue
            fixtures = provider.fixtures(code, next_n=10)
            upcoming_ids: list[int] = []
            team_ext: set[int] = set()

            for item in fixtures:
                parsed = parse_fixture(item)
                home = _upsert_team(db, league.id, parsed["home"])
                away = _upsert_team(db, league.id, parsed["away"])
                if not home or not away:
                    continue
                match = (
                    db.query(Match)
                    .filter(Match.external_id == parsed["external_id"])
                    .one_or_none()
                )
                if match is None:
                    match = Match(
                        external_id=parsed["external_id"],
                        league_id=league.id,
                        home_team_id=home.id,
                        away_team_id=away.id,
                        kickoff=parsed["kickoff"],
                        status=parsed["status"],
                        venue=parsed["venue"],
                    )
                    db.add(match)
                    db.flush()
                    upserts += 1
                upcoming_ids.append(match.id)
                team_ext.add(home.external_id or 0)
                team_ext.add(away.external_id or 0)

            db.commit()

            for ext_id in [t for t in team_ext if t]:
                last = provider.last_fixtures(ext_id, last=5)
                for item in last:
                    parsed = parse_fixture(item)
                    if parsed["status"] != "FINISHED":
                        continue
                    home = _upsert_team(db, league.id, parsed["home"])
                    away = _upsert_team(db, league.id, parsed["away"])
                    if not home or not away:
                        continue
                    match = (
                        db.query(Match)
                        .filter(Match.external_id == parsed["external_id"])
                        .one_or_none()
                    )
                    if match is None:
                        match = Match(
                            external_id=parsed["external_id"],
                            league_id=league.id,
                            home_team_id=home.id,
                            away_team_id=away.id,
                            kickoff=parsed["kickoff"],
                            status="FINISHED",
                            venue=parsed["venue"],
                            home_goals=parsed["home_goals"] or 0,
                            away_goals=parsed["away_goals"] or 0,
                        )
                        db.add(match)
                        db.flush()
                        upserts += 1
                    else:
                        match.home_goals = parsed["home_goals"]
                        match.away_goals = parsed["away_goals"]
                        match.status = "FINISHED"

                    existing_stats = db.query(MatchStat).filter(MatchStat.match_id == match.id).count()
                    if existing_stats >= 2:
                        continue

                    raw_stats = provider.fixture_statistics(parsed["external_id"])
                    rows = parse_team_stats(raw_stats)
                    by_ext = {r["external_team_id"]: r for r in rows}
                    for team, gf, ga in (
                        (home, match.home_goals or 0, match.away_goals or 0),
                        (away, match.away_goals or 0, match.home_goals or 0),
                    ):
                        row = by_ext.get(team.external_id) or {}
                        shots = int(row.get("shots") or 0)
                        sot = int(row.get("shots_on_target") or 0)
                        xg = row.get("xg") or estimate_xg(shots, sot, gf)
                        db.add(
                            MatchStat(
                                match_id=match.id,
                                team_id=team.id,
                                goals=gf,
                                goals_against=ga,
                                xg=xg,
                                xga=0,
                                shots=shots,
                                shots_on_target=sot,
                                possession=float(row.get("possession") or 50),
                                corners=int(row.get("corners") or 0),
                                yellows=int(row.get("yellows") or 0),
                                reds=int(row.get("reds") or 0),
                                fouls=int(row.get("fouls") or 0),
                                result=_result(gf, ga),
                            )
                        )
                        upserts += 1
                    db.flush()
                    pair = (
                        db.query(MatchStat)
                        .filter(MatchStat.match_id == match.id)
                        .all()
                    )
                    if len(pair) == 2:
                        pair[0].xga = pair[1].xg
                        pair[1].xga = pair[0].xg

                    raw_players = provider.fixture_players(parsed["external_id"])
                    for prow in parse_player_stats(raw_players):
                        player = (
                            db.query(Player)
                            .filter(Player.external_id == prow["external_player_id"])
                            .one_or_none()
                        )
                        team = (
                            db.query(Team)
                            .filter(Team.external_id == prow["external_team_id"])
                            .one_or_none()
                        )
                        if team is None:
                            continue
                        if player is None:
                            player = Player(
                                external_id=prow["external_player_id"],
                                team_id=team.id,
                                name=prow["name"] or "Jugador",
                                photo_url=prow["photo"],
                                position=(prow["position"] or "M")[:2].upper() if prow["position"] else "MF",
                                nationality="—",
                                nationality_code="UN",
                                age=26,
                                height_cm=180,
                                weight_kg=75,
                                preferred_foot="Derecho",
                                shirt_number=10,
                            )
                            db.add(player)
                            db.flush()
                        db.add(
                            PlayerMatchStat(
                                match_id=match.id,
                                player_id=player.id,
                                team_id=team.id,
                                minutes=prow["minutes"],
                                goals=prow["goals"],
                                assists=prow["assists"],
                                rating=prow["rating"],
                                shots=prow["shots"],
                                shots_on_target=prow["shots_on_target"],
                                key_passes=prow["key_passes"],
                                yellows=prow["yellows"],
                                reds=prow["reds"],
                            )
                        )
                        upserts += 1
                db.commit()

        rebuilt = rebuild_knowledge(db)
        run.status = "ok"
        run.finished_at = datetime.now(timezone.utc)
        run.requests_made = provider.requests_made
        run.cache_hits = provider.cache_hits
        run.rows_upserted = upserts
        run.notes = f"knowledge={rebuilt}; keys={bool(settings.api_football_key)}"
        db.commit()
        return {
            "status": "ok",
            "requests_made": provider.requests_made,
            "cache_hits": provider.cache_hits,
            "rows_upserted": upserts,
            "knowledge": rebuilt,
        }
    except Exception as exc:
        logger.exception("ETL failed")
        run.status = "error"
        run.finished_at = datetime.now(timezone.utc)
        run.notes = str(exc)
        db.commit()
        raise


def run_etl(db: Session, source: str | None = None) -> dict:
    settings = get_settings()
    mode = (source or settings.data_source or "live").lower()
    if mode == "live":
        from app.services.live_feed import sync_feed
        return sync_feed(db, force_calendar=True)
    from app.etl.fixtures import ensure_leagues, purge_synthetic_matches, sync_active_calendar

    ensure_leagues(db)
    purge_synthetic_matches(db)
    if settings.has_api_football or settings.has_football_data:
        from app.etl.hybrid import run_hybrid_live

        if mode != "seed":
            return run_hybrid_live(db)
        return sync_active_calendar(db, force=True)
    if mode == "seed":
        from app.seed.seeder import seed_database

        return seed_database(db)
    return {"status": "missing_api_keys", "upcoming": 0}

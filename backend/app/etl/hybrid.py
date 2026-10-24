"""Ingesta live con cupo controlado.

football-data.org (10 req/min): Premier League, La Liga, Serie A.
  2 llamadas por liga (jornada + resultados) y last-5 se recorta en local.

API-Football (100 req/día): Liga MX y MLS.
  2 llamadas por liga + estadísticas/jugadores con tope.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.domain.identity import club_fits_league
from app.etl.calendar import aware, upcoming_window, utcnow
from app.etl.transform import parse_fixture, parse_player_stats, parse_team_stats
from app.infrastructure.db.models import (
    EtlRun,
    League,
    Match,
    MatchStat,
    Player,
    PlayerFormSnapshot,
    PlayerMatchStat,
    Prediction,
    Team,
    TeamFormSnapshot,
)
from app.infrastructure.providers.api_football import ApiFootballProvider
from app.infrastructure.providers.football_data import FootballDataProvider
from app.ml.form import estimate_xg
from app.services.knowledge import rebuild_knowledge

logger = logging.getLogger(__name__)

FD_LEAGUES = ("PL", "PD", "SA")
AF_LEAGUES = ("MX", "MLS")
AF_STAT_BUDGET = 24
AF_PLAYER_BUDGET = 12


def _now() -> datetime:
    return utcnow()


def _parse_iso(value: str | None) -> datetime:
    if not value:
        return _now()
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _league_active(league: League | None) -> bool:
    return bool(league and league.is_active)


def _result(gf: int, ga: int) -> str:
    if gf > ga:
        return "W"
    if gf < ga:
        return "L"
    return "D"


def _purge_league_matches(db: Session, league_id: int) -> None:
    ids = [row[0] for row in db.query(Match.id).filter(Match.league_id == league_id).all()]
    if not ids:
        return
    db.query(Prediction).filter(Prediction.match_id.in_(ids)).delete(synchronize_session=False)
    db.query(TeamFormSnapshot).filter(TeamFormSnapshot.as_of_match_id.in_(ids)).delete(synchronize_session=False)
    db.query(PlayerFormSnapshot).filter(PlayerFormSnapshot.as_of_match_id.in_(ids)).delete(synchronize_session=False)
    db.query(PlayerMatchStat).filter(PlayerMatchStat.match_id.in_(ids)).delete(synchronize_session=False)
    db.query(MatchStat).filter(MatchStat.match_id.in_(ids)).delete(synchronize_session=False)
    db.query(Match).filter(Match.id.in_(ids)).delete(synchronize_session=False)
    db.flush()


def _stats_from_official_score(gf: int, ga: int) -> dict:
    """Solo el marcador oficial. Sin tiros ni posesión inventados."""
    return {
        "goals": gf,
        "goals_against": ga,
        "xg": estimate_xg(0, 0, gf),
        "xga": estimate_xg(0, 0, ga),
        "shots": 0,
        "shots_on_target": 0,
        "possession": 50.0,
        "corners": 0,
        "yellows": 0,
        "reds": 0,
        "fouls": 0,
        "result": _result(gf, ga),
    }


def _write_pair(db: Session, match: Match, home: Team, away: Team, hg: int, ag: int, home_row: dict, away_row: dict) -> None:
    home_row = dict(home_row)
    away_row = dict(away_row)
    home_row["xga"] = away_row.get("xg") or 0
    away_row["xga"] = home_row.get("xg") or 0
    if home_row.get("possession") and away_row.get("possession") is None:
        away_row["possession"] = round(100 - float(home_row["possession"]), 1)
    db.add(MatchStat(match_id=match.id, team_id=home.id, **home_row))
    db.add(MatchStat(match_id=match.id, team_id=away.id, **away_row))


def _upsert_team(db: Session, league: League, *, ext: int | None, name: str, short: str, tla: str, logo: str | None) -> Team | None:
    if name and not club_fits_league(name, league.code):
        logger.warning("equipo %s no pertenece a %s", name, league.code)
        return None
    team = None
    if ext:
        team = db.query(Team).filter(Team.league_id == league.id, Team.external_id == ext).one_or_none()
    if team is None and tla:
        hit = db.query(Team).filter(Team.league_id == league.id, Team.tla == tla[:8]).one_or_none()
        if hit and club_fits_league(hit.name, league.code):
            team = hit
    if team is None:
        team = db.query(Team).filter(Team.league_id == league.id, Team.name == name).one_or_none()
    if team is None:
        team = Team(
            external_id=ext,
            league_id=league.id,
            name=name,
            short_name=(short or name)[:40],
            tla=(tla or name)[:8].upper(),
            logo_url=logo,
        )
        db.add(team)
        db.flush()
        return team
    team.external_id = ext or team.external_id
    team.name = name or team.name
    team.short_name = (short or team.short_name)[:40]
    if tla:
        team.tla = tla[:8].upper()
    if logo:
        team.logo_url = logo
    return team


def _upsert_match(
    db: Session,
    league: League,
    home: Team,
    away: Team,
    *,
    ext: int | None,
    kickoff: datetime,
    status: str,
    venue: str | None,
    matchday: int | None,
    hg: int | None,
    ag: int | None,
    h2h_only: bool = False,
) -> Match | None:
    if home.league_id != league.id or away.league_id != league.id:
        return None
    if not club_fits_league(home.name, league.code) or not club_fits_league(away.name, league.code):
        return None
    match = None
    if ext:
        match = db.query(Match).filter(Match.external_id == ext).one_or_none()
    if match is None:
        match = Match(league_id=league.id, home_team_id=home.id, away_team_id=away.id)
        db.add(match)
    match.external_id = ext
    match.league_id = league.id
    match.home_team_id = home.id
    match.away_team_id = away.id
    match.kickoff = kickoff
    match.status = status
    match.venue = venue
    match.matchday = matchday
    match.home_goals = hg
    match.away_goals = ag
    match.is_h2h_only = h2h_only
    db.flush()
    return match


def ingest_football_data(db: Session, fd: FootballDataProvider) -> int:
    upserts = 0
    start, horizon = upcoming_window()
    date_from = start.date().isoformat()
    date_to = horizon.date().isoformat()

    for code in FD_LEAGUES:
        league = db.query(League).filter(League.code == code).one_or_none()
        if not _league_active(league):
            logger.info("football-data skip %s (inactive)", code)
            continue
        try:
            upserts += _ingest_one_fd_league(db, fd, league, code, start, horizon, date_from, date_to)
        except Exception:
            logger.exception("football-data falló %s", code)
            db.rollback()
    return upserts


def _ingest_one_fd_league(
    db: Session,
    fd: FootballDataProvider,
    league: League,
    code: str,
    start,
    horizon,
    date_from: str,
    date_to: str,
) -> int:
    upserts = 0
    pooled: list[dict] = []
    for st in ("TIMED", "SCHEDULED", "IN_PLAY", "PAUSED"):
        pooled.extend(fd.competition_matches(code, st) or [])
    if not pooled:
        pooled = fd.competition_matches(code, date_from=date_from, date_to=date_to) or []
    finished = fd.competition_matches(code, "FINISHED") or []

    upcoming = []
    seen_ids: set[int] = set()
    for raw in pooled:
        ext = raw.get("id")
        if ext in seen_ids:
            continue
        st = raw.get("status") or ""
        if st not in {"TIMED", "SCHEDULED", "IN_PLAY", "PAUSED"}:
            continue
        kick = aware(_parse_iso(raw.get("utcDate")))
        if kick and start <= kick <= horizon:
            seen_ids.add(ext)
            upcoming.append(raw)
    upcoming.sort(key=lambda r: r.get("utcDate") or "")
    upcoming = upcoming[:12]
    if not upcoming:
        logger.warning("football-data %s sin jornada en el horizonte", code)
        return 0
    _purge_league_matches(db, league.id)

    finished_sorted = sorted(finished, key=lambda r: r.get("utcDate") or "", reverse=True)

    def team_from(blob: dict) -> Team:
        return _upsert_team(
            db,
            league,
            ext=blob.get("id"),
            name=blob.get("name") or "Unknown",
            short=blob.get("shortName") or blob.get("name") or "UNK",
            tla=blob.get("tla") or (blob.get("shortName") or "UNK")[:3],
            logo=blob.get("crest"),
        )

    stored_finished: dict[int, Match] = {}

    def persist_finished(raw: dict) -> Match | None:
        ext = raw.get("id")
        if ext in stored_finished:
            return stored_finished[ext]
        score = ((raw.get("score") or {}).get("fullTime")) or {}
        hg, ag = score.get("home"), score.get("away")
        if hg is None or ag is None:
            return None
        home = team_from(raw.get("homeTeam") or {})
        away = team_from(raw.get("awayTeam") or {})
        if not home or not away:
            return None
        status_raw = raw.get("status") or "FINISHED"
        if status_raw not in {"FINISHED", "AWARDED"}:
            return None
        match = _upsert_match(
            db,
            league,
            home,
            away,
            ext=ext,
            kickoff=_parse_iso(raw.get("utcDate")),
            status="FINISHED",
            venue=raw.get("venue"),
            matchday=raw.get("matchday"),
            hg=int(hg),
            ag=int(ag),
        )
        if match is None:
            return None
        hs = _stats_from_official_score(int(hg), int(ag))
        aws = _stats_from_official_score(int(ag), int(hg))
        _write_pair(db, match, home, away, int(hg), int(ag), hs, aws)
        stored_finished[ext] = match
        return match

    needed_finished: set[int] = set()
    last5_by_team: dict[int, list[dict]] = {}
    for raw in finished_sorted:
        hid = (raw.get("homeTeam") or {}).get("id")
        aid = (raw.get("awayTeam") or {}).get("id")
        for tid in (hid, aid):
            if tid is None:
                continue
            bucket = last5_by_team.setdefault(tid, [])
            if len(bucket) < 5:
                bucket.append(raw)
                if raw.get("id"):
                    needed_finished.add(raw["id"])

    for raw in finished_sorted:
        if raw.get("id") in needed_finished:
            persist_finished(raw)
            upserts += 1

    for raw in upcoming:
        home = team_from(raw.get("homeTeam") or {})
        away = team_from(raw.get("awayTeam") or {})
        if not home or not away:
            continue
        st = raw.get("status") or "SCHEDULED"
        _upsert_match(
            db,
            league,
            home,
            away,
            ext=raw.get("id"),
            kickoff=_parse_iso(raw.get("utcDate")),
            status="LIVE" if st in {"IN_PLAY", "PAUSED"} else "SCHEDULED",
            venue=raw.get("venue"),
            matchday=raw.get("matchday"),
            hg=None,
            ag=None,
        )
        upserts += 1
        pair = []
        hid = (raw.get("homeTeam") or {}).get("id")
        aid = (raw.get("awayTeam") or {}).get("id")
        for past in finished_sorted:
            ph = (past.get("homeTeam") or {}).get("id")
            pa = (past.get("awayTeam") or {}).get("id")
            if {ph, pa} == {hid, aid}:
                pair.append(past)
            if len(pair) >= 3:
                break
        for past in pair:
            m = persist_finished(past)
            if m and past.get("id") not in needed_finished:
                m.is_h2h_only = True
                upserts += 1

    db.commit()
    logger.info("football-data %s upcoming=%s", code, len(upcoming))
    return upserts


def ingest_api_football(db: Session, af: ApiFootballProvider) -> int:
    upserts = 0
    stats_left = AF_STAT_BUDGET
    players_left = AF_PLAYER_BUDGET

    start, horizon = upcoming_window()
    date_from = start.date().isoformat()
    date_to = horizon.date().isoformat()

    for code in AF_LEAGUES:
        league = db.query(League).filter(League.code == code).one_or_none()
        if not _league_active(league) or not league.api_football_id:
            logger.info("api-football skip %s (inactive)", code)
            continue
        season = league.season or 2026
        nxt: list[dict] = []
        seasons_to_try = [season]
        if season:
            seasons_to_try.append(season - 1)
        recent: list[dict] = []
        used_season = season
        for yr in seasons_to_try:
            nxt = af.fixtures_window(league.api_football_id, yr, date_from, date_to)
            if not nxt:
                nxt = af.fixtures(code, next_n=15, season=yr)
            windowed = []
            for item in nxt or []:
                parsed = parse_fixture(item)
                kick = aware(parsed["kickoff"])
                if kick and start <= kick <= horizon:
                    windowed.append(item)
            nxt = windowed[:12]
            recent = af.get("fixtures", {"league": league.api_football_id, "season": yr, "last": 40}).get("response") or []
            if nxt or recent:
                used_season = yr
                league.season = yr
                break
        if not nxt and not recent:
            logger.warning("API-Football sin datos para %s season=%s", code, season)
            continue
        if not nxt:
            logger.warning("API-Football %s sin jornada en el horizonte season=%s", code, used_season)
            continue
        _purge_league_matches(db, league.id)

        def team_from(blob: dict) -> Team:
            return _upsert_team(
                db,
                league,
                ext=blob.get("id"),
                name=blob.get("name") or "Unknown",
                short=blob.get("name") or "UNK",
                tla=(blob.get("name") or "UNK")[:3],
                logo=blob.get("logo"),
            )

        parsed_recent = [parse_fixture(item) for item in recent]
        parsed_recent = [p for p in parsed_recent if p["status"] == "FINISHED"]
        parsed_recent.sort(key=lambda p: p["kickoff"], reverse=True)

        stored: dict[int, Match] = {}

        def persist_finished(parsed: dict, raw_item: dict | None = None) -> Match | None:
            nonlocal stats_left, players_left, upserts
            ext = parsed["external_id"]
            if ext in stored:
                return stored[ext]
            home = team_from(parsed["home"])
            away = team_from(parsed["away"])
            if not home or not away:
                return None
            hg = int(parsed["home_goals"] or 0)
            ag = int(parsed["away_goals"] or 0)
            match = _upsert_match(
                db,
                league,
                home,
                away,
                ext=ext,
                kickoff=parsed["kickoff"],
                status="FINISHED",
                venue=parsed["venue"],
                matchday=None,
                hg=hg,
                ag=ag,
            )
            if match is None:
                return None
            home_row = away_row = None
            if stats_left > 0 and ext:
                db.commit()
                raw_stats = af.fixture_statistics(ext)
                stats_left -= 1
                rows = {r["external_team_id"]: r for r in parse_team_stats(raw_stats)}
                def pack(team: Team, gf: int, ga: int) -> dict:
                    row = rows.get(team.external_id) or {}
                    shots = int(row.get("shots") or 0)
                    sot = int(row.get("shots_on_target") or 0)
                    xg = row.get("xg") or estimate_xg(shots or 8, sot or max(gf, 1), gf)
                    return {
                        "goals": gf,
                        "goals_against": ga,
                        "xg": float(xg),
                        "xga": 0.0,
                        "shots": shots or max(6, gf * 3),
                        "shots_on_target": sot or max(gf, 1),
                        "possession": float(row.get("possession") or 50),
                        "corners": int(row.get("corners") or 0),
                        "yellows": int(row.get("yellows") or 0),
                        "reds": int(row.get("reds") or 0),
                        "fouls": int(row.get("fouls") or 0),
                        "result": _result(gf, ga),
                    }
                home_row, away_row = pack(home, hg, ag), pack(away, ag, hg)
            else:
                home_row = _stats_from_official_score(hg, ag)
                away_row = _stats_from_official_score(ag, hg)
            _write_pair(db, match, home, away, hg, ag, home_row, away_row)

            if players_left > 0 and ext:
                db.commit()
                raw_players = af.fixture_players(ext)
                players_left -= 1
                for prow in parse_player_stats(raw_players):
                    team = db.query(Team).filter(Team.external_id == prow["external_team_id"]).one_or_none()
                    if team is None:
                        continue
                    player = (
                        db.query(Player).filter(Player.external_id == prow["external_player_id"]).one_or_none()
                    )
                    pos = (prow.get("position") or "MF")[:2].upper()
                    if pos not in {"GK", "DF", "MF", "FW"}:
                        pos = "MF"
                    if player is None:
                        player = Player(
                            external_id=prow["external_player_id"],
                            team_id=team.id,
                            name=prow["name"] or "Jugador",
                            photo_url=prow.get("photo"),
                            position=pos,
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
            stored[ext] = match
            upserts += 1
            return match

        last5: dict[int, list[dict]] = {}
        for parsed in parsed_recent:
            for blob in (parsed["home"], parsed["away"]):
                tid = blob.get("id")
                if not tid:
                    continue
                bucket = last5.setdefault(tid, [])
                if len(bucket) < 5:
                    bucket.append(parsed)

        needed = {p["external_id"] for rows in last5.values() for p in rows}
        by_ext = {p["external_id"]: p for p in parsed_recent}
        for ext in needed:
            persist_finished(by_ext[ext])

        for item in nxt:
            parsed = parse_fixture(item)
            home = team_from(parsed["home"])
            away = team_from(parsed["away"])
            if not home or not away:
                continue
            _upsert_match(
                db,
                league,
                home,
                away,
                ext=parsed["external_id"],
                kickoff=parsed["kickoff"],
                status="SCHEDULED" if parsed["status"] != "LIVE" else "LIVE",
                venue=parsed["venue"],
                matchday=None,
                hg=None,
                ag=None,
            )
            upserts += 1
            hid, aid = parsed["home"].get("id"), parsed["away"].get("id")
            h2h = 0
            for past in parsed_recent:
                ph, pa = past["home"].get("id"), past["away"].get("id")
                if {ph, pa} == {hid, aid}:
                    m = persist_finished(past)
                    if m and past["external_id"] not in needed:
                        m.is_h2h_only = True
                    h2h += 1
                if h2h >= 3:
                    break
        db.commit()
        logger.info("api-football %s upcoming=%s stats_left=%s", code, len(nxt), stats_left)
    return upserts


def run_hybrid_live(db: Session) -> dict:
    from app.etl.fixtures import mark_league_activity

    run = EtlRun(started_at=_now(), status="running", source="live")
    db.add(run)
    db.commit()
    fd = FootballDataProvider(db)
    af = ApiFootballProvider(db)
    try:
        mark_league_activity(db, af=af, fd=fd)
        n_fd = ingest_football_data(db, fd) if fd.settings.has_football_data else 0
        n_af = ingest_api_football(db, af) if af.settings.has_api_football else 0
        knowledge = rebuild_knowledge(db)
        run.status = "ok"
        run.finished_at = _now()
        run.requests_made = fd.requests_made + af.requests_made
        run.cache_hits = fd.cache_hits + af.cache_hits
        run.rows_upserted = n_fd + n_af
        run.notes = f"hybrid fd={n_fd} af={n_af} knowledge={knowledge}"
        db.commit()
        return {
            "status": "ok",
            "source": "live",
            "requests_made": run.requests_made,
            "cache_hits": run.cache_hits,
            "rows_upserted": run.rows_upserted,
            "knowledge": knowledge,
        }
    except Exception as exc:
        logger.exception("hybrid live failed")
        run.status = "error"
        run.finished_at = _now()
        run.notes = str(exc)
        db.commit()
        raise

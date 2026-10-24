"""Seeder determinista: genera últimos 5 + H2H + jugador clave y materializa conocimiento."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
from sqlalchemy.orm import Session

from app.etl.calendar import current_season_year, is_in_season, roll_kickoff, utcnow
from app.infrastructure.db.models import (
    EtlRun,
    League,
    Match,
    MatchStat,
    Player,
    PlayerMatchStat,
    Team,
)
from app.ml.form import estimate_xg
from app.seed.catalog import FILLERS, FIXTURES, LEAGUES, TEAMS
from app.services.knowledge import rebuild_knowledge

CDN_TEAM = "https://media.api-sports.io/football/teams/{}.png"
CDN_PLAYER = "https://media.api-sports.io/football/players/{}.png"


def _clamp(n: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, n))


def _goals(rng: np.random.Generator, lam: float) -> int:
    return int(min(5, rng.poisson(max(0.25, lam))))


def _result(gf: int, ga: int) -> str:
    return "W" if gf > ga else "L" if gf < ga else "D"


def seed_database(db: Session, force: bool = False) -> dict:
    existing = db.query(Match).filter(Match.status == "SCHEDULED").count()
    if existing and not force:
        from app.etl.fixtures import sync_active_calendar

        return sync_active_calendar(db)

    if force:
        for model in (
            PlayerMatchStat,
            MatchStat,
            Player,
            Match,
            Team,
            League,
        ):
            db.query(model).delete()
        db.commit()

    run = EtlRun(
        started_at=datetime.now(timezone.utc),
        status="running",
        source="seed",
    )
    db.add(run)
    db.commit()

    now = utcnow()
    leagues: dict[str, League] = {}
    for row in LEAGUES:
        payload = dict(row)
        payload["season"] = current_season_year(row["code"], now)
        payload["is_active"] = is_in_season(row["code"], now)
        lg = League(**payload)
        db.add(lg)
        db.flush()
        leagues[lg.code] = lg

    teams: dict[str, Team] = {}
    players: dict[str, Player] = {}
    catalog = {t["tla"]: t for t in TEAMS}

    def add_team(tla: str, league_code: str, name: str, short: str, ext: int, city: str, stadium: str, primary="#8899AA"):
        team = Team(
            external_id=ext,
            league_id=leagues[league_code].id,
            name=name,
            short_name=short,
            tla=tla,
            logo_url=CDN_TEAM.format(ext),
            city=city,
            stadium=stadium,
            primary_color=primary,
            secondary_color="#0D1526",
        )
        db.add(team)
        db.flush()
        teams[tla] = team
        return team

    for t in TEAMS:
        team = add_team(
            t["tla"], t["league"], t["name"], t["short_name"], t["ext"], t["city"], t["stadium"], t["primary"]
        )
        p = t["player"]
        player = Player(
            external_id=p["ext"],
            team_id=team.id,
            name=p["name"],
            photo_url=CDN_PLAYER.format(p["ext"]),
            position=p["pos"],
            nationality=p["nat"],
            nationality_code=p["cc"],
            age=p["age"],
            height_cm=p["h"],
            weight_kg=p["w"],
            preferred_foot=p["foot"],
            shirt_number=p["no"],
        )
        db.add(player)
        db.flush()
        players[t["tla"]] = player

    for code, fillers in FILLERS.items():
        for tla, name, short, ext, city, stadium in fillers:
            if tla not in teams:
                add_team(tla, code, name, short, ext, city, stadium)

    db.commit()

    def persist_match(
        home: Team,
        away: Team,
        kickoff: datetime,
        league_id: int,
        status: str,
        hg: int | None,
        ag: int | None,
        venue: str | None,
        h2h_only: bool,
        home_stats: dict | None,
        away_stats: dict | None,
        matchday: int | None = None,
    ) -> Match:
        m = Match(
            league_id=league_id,
            home_team_id=home.id,
            away_team_id=away.id,
            kickoff=kickoff,
            status=status,
            venue=venue,
            home_goals=hg,
            away_goals=ag,
            is_h2h_only=h2h_only,
            matchday=matchday,
        )
        db.add(m)
        db.flush()
        if home_stats and away_stats and status == "FINISHED":
            db.add(MatchStat(match_id=m.id, team_id=home.id, **home_stats))
            db.add(MatchStat(match_id=m.id, team_id=away.id, **away_stats))
        return m

    def simulate(home_tla: str, away_tla: str, rng: np.random.Generator) -> tuple[dict, dict, int, int]:
        h = catalog.get(home_tla, {"atk": 1.0, "defn": 1.0, "player": {"finishing": 0.6}})
        a = catalog.get(away_tla, {"atk": 1.0, "defn": 1.0, "player": {"finishing": 0.6}})
        lam_h = 1.28 * h.get("atk", 1.0) * a.get("defn", 1.0)
        lam_a = 1.10 * a.get("atk", 1.0) * h.get("defn", 1.0)
        hg = _goals(rng, lam_h)
        ag = _goals(rng, lam_a)
        def pack(gf: int, ga: int, atk: float, is_home: bool) -> dict:
            shots = _clamp(int(rng.normal(11 + atk * 4, 2.4)), 4, 26)
            sot = _clamp(int(shots * rng.uniform(0.28, 0.48) + gf), 1, shots)
            poss = float(_clamp(int(rng.normal(50 + (8 if is_home else -4) + (atk - 1) * 12, 6)), 32, 72))
            corners = _clamp(int(rng.normal(4.5 + atk, 1.6)), 0, 14)
            yellows = _clamp(int(rng.poisson(1.6)), 0, 6)
            reds = 1 if rng.random() < 0.06 else 0
            xg = estimate_xg(shots, sot, gf)
            return {
                "goals": gf,
                "goals_against": ga,
                "xg": xg,
                "xga": 0.0,
                "shots": shots,
                "shots_on_target": sot,
                "possession": poss,
                "corners": corners,
                "yellows": yellows,
                "reds": reds,
                "fouls": _clamp(int(rng.normal(12, 3)), 6, 22),
                "result": _result(gf, ga),
            }

        hs = pack(hg, ag, h.get("atk", 1.0), True)
        aws = pack(ag, hg, a.get("atk", 1.0), False)
        hs["xga"] = aws["xg"]
        aws["xga"] = hs["xg"]
        # posesión complementaria
        aws["possession"] = round(100 - hs["possession"], 1)
        return hs, aws, hg, ag

    def player_line(tla: str, match: Match, team: Team, gf: int, rng: np.random.Generator, is_home: bool) -> None:
        if tla not in players:
            return
        pmeta = catalog[tla]["player"]
        fin = pmeta["finishing"]
        goals = 0
        for _ in range(gf):
            if rng.random() < 0.38 + fin * 0.28:
                goals += 1
        goals = min(gf, goals)
        assists = 1 if gf - goals > 0 and rng.random() < 0.45 else 0
        minutes = int(rng.choice([78, 84, 90, 90, 90, 72]))
        rating = round(float(np.clip(rng.normal(6.6 + goals * 0.55 + assists * 0.35 + fin * 0.4, 0.28), 5.8, 9.6)), 2)
        db.add(
            PlayerMatchStat(
                match_id=match.id,
                player_id=players[tla].id,
                team_id=team.id,
                minutes=minutes,
                goals=goals,
                assists=assists,
                rating=rating,
                shots=_clamp(int(rng.normal(2.2 + fin * 2.2, 1.1)), 0, 8),
                shots_on_target=_clamp(goals + int(rng.integers(0, 3)), 0, 6),
                key_passes=_clamp(int(rng.normal(1.4 + (0.8 if not is_home else 1.1), 0.9)), 0, 6),
                yellows=1 if rng.random() < 0.14 else 0,
                reds=0,
            )
        )

    rng = np.random.default_rng(20260916)
    upcoming_pairs = {(h, a) for h, a, *_ in FIXTURES}

    # Últimos 5 de cada equipo protagonista
    for t in TEAMS:
        league_code = t["league"]
        pool = [x["tla"] for x in TEAMS if x["league"] == league_code and x["tla"] != t["tla"]]
        pool += [f[0] for f in FILLERS[league_code]]
        # evita repetir el rival de la jornada como único rival
        upcoming_opp = None
        for h, a, *_ in FIXTURES:
            if h == t["tla"]:
                upcoming_opp = a
            if a == t["tla"]:
                upcoming_opp = h
        choices = [p for p in pool if p != upcoming_opp]
        rng.shuffle(choices)
        opps = list(dict.fromkeys(choices))[:5]
        for i, opp_tla in enumerate(opps):
            kickoff = now - timedelta(days=7 * (i + 1), hours=int(rng.integers(0, 10)))
            is_home = bool(i % 2 == 0)
            home_tla, away_tla = (t["tla"], opp_tla) if is_home else (opp_tla, t["tla"])
            hs, aws, hg, ag = simulate(home_tla, away_tla, rng)
            match = persist_match(
                teams[home_tla],
                teams[away_tla],
                kickoff,
                leagues[league_code].id,
                "FINISHED",
                hg,
                ag,
                teams[home_tla].stadium,
                False,
                hs,
                aws,
            )
            player_line(home_tla, match, teams[home_tla], hg, rng, True)
            player_line(away_tla, match, teams[away_tla], ag, rng, False)

    # H2H (más antiguo, no entra en last-5)
    for home_tla, away_tla, *_rest in FIXTURES:
        league_code = catalog[home_tla]["league"]
        for k in range(3):
            kickoff = datetime(2025, 11, 1, tzinfo=timezone.utc) + timedelta(days=40 * k)
            swap = k == 1
            ht, at = (away_tla, home_tla) if swap else (home_tla, away_tla)
            hs, aws, hg, ag = simulate(ht, at, rng)
            persist_match(
                teams[ht],
                teams[at],
                kickoff,
                leagues[league_code].id,
                "FINISHED",
                hg,
                ag,
                teams[ht].stadium,
                True,
                hs,
                aws,
            )

    # Jornada próxima: solo torneos en curso, fechas a partir de hoy
    for home_tla, away_tla, iso, venue, md in FIXTURES:
        league_code = catalog[home_tla]["league"]
        lg = leagues[league_code]
        if not lg.is_active:
            continue
        persist_match(
            teams[home_tla],
            teams[away_tla],
            roll_kickoff(iso, now),
            lg.id,
            "SCHEDULED",
            None,
            None,
            venue,
            False,
            None,
            None,
            matchday=md,
        )

    db.commit()
    knowledge = rebuild_knowledge(db)
    run.status = "ok"
    run.finished_at = datetime.now(timezone.utc)
    run.requests_made = 0
    run.cache_hits = 0
    run.rows_upserted = db.query(Match).count()
    run.notes = f"seed knowledge={knowledge} pairs={len(upcoming_pairs)}"
    db.commit()
    return {
        "status": "seeded",
        "teams": db.query(Team).count(),
        "matches": db.query(Match).count(),
        "knowledge": knowledge,
    }

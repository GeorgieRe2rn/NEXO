"""Normaliza respuestas crudas de API-Football a estructuras de dominio."""

from __future__ import annotations

from datetime import datetime, timezone


def _stat_map(block: dict) -> dict[str, float | int | None]:
    out: dict[str, float | int | None] = {}
    for item in block.get("statistics", []):
        key = (item.get("type") or "").strip().lower()
        val = item.get("value")
        if val is None:
            out[key] = 0
            continue
        if isinstance(val, str) and val.endswith("%"):
            try:
                out[key] = float(val.replace("%", ""))
            except ValueError:
                out[key] = 0
        else:
            try:
                out[key] = float(val)
            except (TypeError, ValueError):
                out[key] = 0
    return out


def parse_team_stats(response: list[dict]) -> list[dict]:
    rows = []
    for block in response:
        team = block.get("team") or {}
        m = _stat_map(block)
        shots = int(m.get("total shots") or m.get("shots total") or 0)
        sot = int(m.get("shots on goal") or m.get("shots on target") or 0)
        xg = m.get("expected_goals") or m.get("expected goals") or m.get("xg")
        rows.append(
            {
                "external_team_id": team.get("id"),
                "team_name": team.get("name"),
                "shots": shots,
                "shots_on_target": sot,
                "possession": float(m.get("ball possession") or 50),
                "corners": int(m.get("corner kicks") or m.get("corners") or 0),
                "yellows": int(m.get("yellow cards") or 0),
                "reds": int(m.get("red cards") or 0),
                "fouls": int(m.get("fouls") or 0),
                "xg": float(xg) if xg else None,
            }
        )
    return rows


def parse_fixture(item: dict) -> dict:
    fx = item.get("fixture") or {}
    league = item.get("league") or {}
    teams = item.get("teams") or {}
    goals = item.get("goals") or {}
    status = (fx.get("status") or {}).get("short") or "NS"
    mapped = "FINISHED" if status in {"FT", "AET", "PEN"} else "LIVE" if status in {"1H", "2H", "HT", "ET", "P", "LIVE"} else "SCHEDULED"
    date = fx.get("date")
    kickoff = datetime.fromisoformat(date.replace("Z", "+00:00")) if date else datetime.now(timezone.utc)
    return {
        "external_id": fx.get("id"),
        "kickoff": kickoff,
        "status": mapped,
        "venue": (fx.get("venue") or {}).get("name"),
        "matchday": league.get("round"),
        "home": teams.get("home") or {},
        "away": teams.get("away") or {},
        "home_goals": goals.get("home"),
        "away_goals": goals.get("away"),
        "league_external": league.get("id"),
    }


def parse_player_stats(response: list[dict]) -> list[dict]:
    rows = []
    for team_block in response:
        team = team_block.get("team") or {}
        for entry in team_block.get("players") or []:
            p = entry.get("player") or {}
            stats = (entry.get("statistics") or [{}])[0]
            games = stats.get("games") or {}
            goals = stats.get("goals") or {}
            shots = stats.get("shots") or {}
            cards = stats.get("cards") or {}
            minutes = games.get("minutes") or 0
            if not minutes:
                continue
            rating_raw = games.get("rating")
            try:
                rating = float(rating_raw) if rating_raw else 6.5
            except (TypeError, ValueError):
                rating = 6.5
            rows.append(
                {
                    "external_player_id": p.get("id"),
                    "name": p.get("name"),
                    "photo": p.get("photo"),
                    "external_team_id": team.get("id"),
                    "minutes": int(minutes),
                    "goals": int(goals.get("total") or 0),
                    "assists": int(goals.get("assists") or 0),
                    "rating": rating,
                    "shots": int(shots.get("total") or 0),
                    "shots_on_target": int(shots.get("on") or 0),
                    "key_passes": int((stats.get("passes") or {}).get("key") or 0),
                    "yellows": int(cards.get("yellow") or 0),
                    "reds": int(cards.get("red") or 0),
                    "position": games.get("position") or "MF",
                }
            )
    return rows

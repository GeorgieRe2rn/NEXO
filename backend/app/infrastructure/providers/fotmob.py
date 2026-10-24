"""FotMob (gratuito, sin clave): plantillas y estadísticas individuales."""

from __future__ import annotations

import logging

import httpx
from sqlalchemy.orm import Session

from app.infrastructure.cache import cache_get, cache_put

logger = logging.getLogger(__name__)

LEAGUES = {"PL": 47, "PD": 87, "SA": 55, "MLS": 130, "MX": 230}

# Conteos (no per-90). Las per-90 se convierten con minutos.
COUNT_STATS = (
    "mins_played",
    "goals",
    "goal_assist",
    "rating",
    "yellow_card",
    "red_card",
    "expected_goals",
    "expected_assists",
    "big_chance_created",
    "clean_sheet",
    "penalty_won",
)
PER90_STATS = (
    "total_scoring_att",
    "ontarget_scoring_att",
    "accurate_pass",
    "saves",
    "fouls",
    "total_tackle",
    "interception",
)
STAT_FILES = COUNT_STATS + PER90_STATS
PER90_SET = set(PER90_STATS)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
}


class FotmobProvider:
    name = "fotmob"

    def __init__(self, db: Session):
        self.db = db
        self.requests_made = 0
        self.cache_hits = 0

    def get_json(self, url: str) -> dict:
        key = f"fm:{url}"
        cached = cache_get(self.db, key)
        if cached is not None:
            self.cache_hits += 1
            return cached
        with httpx.Client(timeout=45.0, headers=HEADERS, follow_redirects=True) as client:
            res = client.get(url)
            res.raise_for_status()
            payload = res.json()
        if not isinstance(payload, dict):
            payload = {"items": payload}
        self.requests_made += 1
        cache_put(self.db, key, self.name, url, payload)
        return payload

    def league_page(self, league_code: str) -> dict:
        lid = LEAGUES.get(league_code)
        if not lid:
            return {}
        return self.get_json(f"https://www.fotmob.com/api/data/leagues?id={lid}")

    def season_path(self, league_code: str) -> str | None:
        data = self.league_page(league_code)
        cats = ((data.get("stats") or {}).get("players")) or []
        for cat in cats:
            url = cat.get("fetchAllUrl") or ""
            if "/stats/" in url and "/season/" in url:
                return url.rsplit("/", 1)[0]
        return None

    def league_teams(self, league_code: str) -> list[dict]:
        data = self.league_page(league_code)
        tables = data.get("table") or []
        if not tables:
            return []
        block = tables[0] if isinstance(tables, list) else tables
        payload = block.get("data") or {}
        row_groups: list[list] = []
        simple = (payload.get("table") or {}).get("all") or []
        if simple:
            row_groups.append(simple)
        for sub in payload.get("tables") or []:
            inner = ((sub.get("table") or {}) if isinstance(sub, dict) else {}).get("all") or []
            if inner:
                row_groups.append(inner)
        out = []
        seen: set[int] = set()
        for rows in row_groups:
            for row in rows:
                tid = row.get("id")
                name = row.get("name") or ""
                if not tid or not name:
                    continue
                tid = int(tid)
                if tid in seen:
                    continue
                seen.add(tid)
                out.append(
                    {
                        "id": tid,
                        "name": name,
                        "shortName": row.get("shortName") or name,
                    }
                )
        return out

    def team_squad(self, fotmob_team_id: int) -> list[dict]:
        data = self.get_json(f"https://www.fotmob.com/api/data/teams?id={fotmob_team_id}")
        groups = ((data.get("squad") or {}).get("squad") or [])
        members: list[dict] = []
        for group in groups:
            title = (group.get("title") or "").lower()
            if title == "coach":
                continue
            for member in group.get("members") or []:
                if not member.get("id"):
                    continue
                member = dict(member)
                member["_group"] = title
                members.append(member)
        return members

    def stat_list(self, season_path: str, filename: str) -> list[dict]:
        url = f"{season_path}/{filename}.json"
        try:
            data = self.get_json(url)
        except Exception:
            logger.warning("FotMob sin archivo %s", filename)
            return []
        lists = data.get("TopLists") or []
        if not lists:
            return []
        return lists[0].get("StatList") or []

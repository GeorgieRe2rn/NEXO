"""Cliente de API-Football (api-sports.io / RapidAPI).

Cubre las 5 ligas requeridas, estadísticas de partido y jugadores.
Todas las respuestas se cachean en PostgreSQL (api_cache) para no quemar
el cupo gratuito de 100 req/día.
"""

from __future__ import annotations

import logging

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.etl.calendar import FIXTURE_CACHE_HOURS, SEASON_CACHE_HOURS, current_season_year
from app.infrastructure.cache import cache_get, cache_put
from app.infrastructure.providers.base import RateLimiter

logger = logging.getLogger(__name__)

LEAGUES = {
    "PL": {"api_id": 39, "season": 2026, "name": "Premier League"},
    "PD": {"api_id": 140, "season": 2026, "name": "La Liga"},
    "SA": {"api_id": 135, "season": 2026, "name": "Serie A"},
    "MX": {"api_id": 262, "season": 2026, "name": "Liga MX"},
    "MLS": {"api_id": 253, "season": 2026, "name": "Major League Soccer"},
}


class ApiFootballProvider:
    name = "api-football"

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.limiter = RateLimiter(self.settings.etl_max_requests_per_min)
        self.requests_made = 0
        self.cache_hits = 0

    def _headers(self) -> dict[str, str]:
        if self.settings.api_football_rapidapi:
            return {
                "X-RapidAPI-Key": self.settings.api_football_key,
                "X-RapidAPI-Host": self.settings.api_football_host,
            }
        return {"x-apisports-key": self.settings.api_football_key}

    def _url(self, path: str) -> str:
        host = self.settings.api_football_host.rstrip("/")
        if not host.startswith("http"):
            host = f"https://{host}"
        return f"{host}/{path.lstrip('/')}"

    def get(
        self,
        path: str,
        params: dict | None = None,
        *,
        ttl_hours: float | None = None,
        skip_cache: bool = False,
    ) -> dict:
        params = params or {}
        key = f"af:{path}:" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        if not skip_cache:
            cached = cache_get(self.db, key)
            if cached is not None:
                self.cache_hits += 1
                return cached
        if not self.settings.api_football_key:
            return {"response": []}

        self.limiter.acquire()
        url = self._url(path)
        logger.info("API-Football GET %s %s", path, params)
        try:
            with httpx.Client(timeout=25.0) as client:
                res = client.get(url, params=params, headers=self._headers())
                res.raise_for_status()
                payload = res.json()
        except httpx.HTTPError:
            logger.exception("API-Football falló %s %s", path, params)
            return {"response": []}
        self.requests_made += 1
        if ttl_hours is None and path.startswith("fixtures"):
            ttl_hours = FIXTURE_CACHE_HOURS
        cache_put(self.db, key, self.name, path, payload, ttl_hours=ttl_hours)
        return payload

    def current_season(self, api_id: int) -> dict | None:
        data = self.get("leagues", {"id": api_id, "current": "true"}, ttl_hours=SEASON_CACHE_HOURS)
        resp = data.get("response") or []
        if not resp:
            return None
        seasons = resp[0].get("seasons") or []
        current = next((s for s in seasons if s.get("current")), None)
        picked = current or (seasons[-1] if seasons else None)
        if not picked:
            return None
        return {
            "year": picked.get("year"),
            "start": picked.get("start"),
            "end": picked.get("end"),
            "current": bool(picked.get("current")),
        }

    def fixtures(self, league_code: str, next_n: int = 12, season: int | None = None) -> list[dict]:
        meta = LEAGUES[league_code]
        year = season or current_season_year(league_code)
        data = self.get(
            "fixtures",
            {"league": meta["api_id"], "season": year, "next": next_n},
            ttl_hours=FIXTURE_CACHE_HOURS,
        )
        return data.get("response", [])

    def fixtures_window(self, api_id: int, season: int, date_from: str, date_to: str) -> list[dict]:
        data = self.get(
            "fixtures",
            {"league": api_id, "season": season, "from": date_from, "to": date_to},
            ttl_hours=FIXTURE_CACHE_HOURS,
        )
        return data.get("response") or []

    def last_fixtures(self, team_id: int, last: int = 5) -> list[dict]:
        data = self.get("fixtures", {"team": team_id, "last": last})
        return data.get("response", [])

    def fixture_statistics(self, fixture_id: int) -> list[dict]:
        data = self.get("fixtures/statistics", {"fixture": fixture_id})
        return data.get("response", [])

    def fixture_players(self, fixture_id: int) -> list[dict]:
        data = self.get("fixtures/players", {"fixture": fixture_id})
        return data.get("response", [])

    def h2h(self, home_id: int, away_id: int, last: int = 3) -> list[dict]:
        data = self.get("fixtures/headtohead", {"h2h": f"{home_id}-{away_id}", "last": last})
        return data.get("response", [])

    def squad(self, team_id: int) -> list[dict]:
        data = self.get("players/squads", {"team": team_id})
        resp = data.get("response", [])
        if not resp:
            return []
        return resp[0].get("players", [])

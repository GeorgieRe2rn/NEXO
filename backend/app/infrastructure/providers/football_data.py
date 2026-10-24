"""Fallback football-data.org (gratis, 10 req/min).

Cubre Premier League, La Liga y Serie A. No incluye Liga MX ni MLS
en el plan gratuito, ni xG/tiros/posesión detallados.
"""

from __future__ import annotations

import logging

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.etl.calendar import FIXTURE_CACHE_HOURS, SEASON_CACHE_HOURS
from app.infrastructure.cache import cache_get, cache_put
from app.infrastructure.providers.base import RateLimiter

logger = logging.getLogger(__name__)

CODES = {"PL": "PL", "PD": "PD", "SA": "SA"}


class FootballDataProvider:
    name = "football-data"
    BASE = "https://api.football-data.org/v4"

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.limiter = RateLimiter(self.settings.etl_max_requests_per_min)
        self.requests_made = 0
        self.cache_hits = 0

    def get(
        self,
        path: str,
        params: dict | None = None,
        *,
        ttl_hours: float | None = None,
        skip_cache: bool = False,
    ) -> dict:
        params = params or {}
        key = f"fd:{path}:" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        if not skip_cache:
            cached = cache_get(self.db, key)
            if cached is not None:
                self.cache_hits += 1
                return cached
        if not self.settings.football_data_key:
            return {}

        self.limiter.acquire()
        url = f"{self.BASE}/{path.lstrip('/')}"
        headers = {"X-Auth-Token": self.settings.football_data_key}
        logger.info("football-data GET %s %s", path, params)
        try:
            with httpx.Client(timeout=45.0) as client:
                res = client.get(url, params=params, headers=headers)
                res.raise_for_status()
                payload = res.json()
        except httpx.HTTPError:
            logger.exception("football-data falló %s %s", path, params)
            return {}
        self.requests_made += 1
        if ttl_hours is None and "matches" in path:
            ttl_hours = FIXTURE_CACHE_HOURS
        cache_put(self.db, key, self.name, path, payload, ttl_hours=ttl_hours)
        return payload

    def competition(self, code: str) -> dict:
        fd = CODES.get(code)
        if not fd:
            return {}
        return self.get(f"competitions/{fd}", ttl_hours=SEASON_CACHE_HOURS)

    def competition_matches(
        self,
        code: str,
        status: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict]:
        fd = CODES.get(code)
        if not fd:
            return []
        params: dict[str, str] = {}
        if status:
            params["status"] = status
        if date_from:
            params["dateFrom"] = date_from
        if date_to:
            params["dateTo"] = date_to
        data = self.get(f"competitions/{fd}/matches", params, ttl_hours=FIXTURE_CACHE_HOURS)
        return data.get("matches", [])

    def team_matches(self, team_id: int, status: str = "FINISHED", limit: int = 5) -> list[dict]:
        data = self.get(f"teams/{team_id}/matches", {"status": status, "limit": limit})
        return data.get("matches", [])[:limit]

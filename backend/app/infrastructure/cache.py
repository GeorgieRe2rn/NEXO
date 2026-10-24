from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.infrastructure.db.models import ApiCache


def cache_get(db: Session, key: str) -> dict | None:
    row = db.get(ApiCache, key)
    if not row:
        return None
    now = datetime.now(timezone.utc)
    exp = row.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < now:
        return None
    row.hit_count += 1
    db.add(row)
    db.commit()
    return row.payload


def cache_put(
    db: Session,
    key: str,
    provider: str,
    endpoint: str,
    payload: dict,
    ttl_hours: float | None = None,
) -> None:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    hours = settings.cache_ttl_hours if ttl_hours is None else ttl_hours
    row = db.get(ApiCache, key)
    if row is None:
        row = ApiCache(cache_key=key)
    row.provider = provider
    row.endpoint = endpoint
    row.payload = payload
    row.fetched_at = now
    row.expires_at = now + timedelta(hours=hours)
    db.merge(row)
    db.commit()


def cache_invalidate(db: Session, prefix: str) -> int:
    rows = db.query(ApiCache).filter(ApiCache.cache_key.startswith(prefix)).all()
    n = len(rows)
    for row in rows:
        db.delete(row)
    if n:
        db.commit()
    return n

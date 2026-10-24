"""Torneos en curso y fechas de jornada.

Las 5 ligas del producto no juegan todo el año. La jornada solo muestra
partidos de competiciones activas y un horizonte corto (próximas jornadas).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

# (mes_inicio, día_inicio, mes_fin, día_fin). Si inicio > fin, cruza año.
SEASON_WINDOWS: dict[str, tuple[int, int, int, int]] = {
    "PL": (8, 1, 5, 31),
    "PD": (8, 1, 5, 31),
    "SA": (8, 10, 5, 31),
    "MX": (7, 1, 5, 31),
    "MLS": (2, 15, 12, 15),
}

LEAGUE_CODES = tuple(SEASON_WINDOWS.keys())
HORIZON_DAYS = 21
GRACE_HOURS = 3
SONORA_TZ = "America/Hermosillo"
DISPLAY_DAYS = 10
REFRESH_CHECK_MINUTES = 30
STALE_AFTER_HOURS = 6
FIXTURE_CACHE_HOURS = 12
SEASON_CACHE_HOURS = 24


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def display_window(now: datetime | None = None):
    """Diez días locales completos, sin truncar la noche del último día."""
    from zoneinfo import ZoneInfo
    current = (aware(now) or utcnow()).astimezone(ZoneInfo(SONORA_TZ))
    start = current.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(timezone.utc), (start+timedelta(days=DISPLAY_DAYS)).astimezone(timezone.utc)


def scoreboard_dates(now: datetime | None = None):
    start, end = display_window(now)
    day = start.date()-timedelta(days=1)
    dates=[]
    while day <= end.date():
        dates.append(day.strftime("%Y%m%d"))
        day += timedelta(days=1)
    return dates


def aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def is_in_season(code: str, now: datetime | None = None) -> bool:
    window = SEASON_WINDOWS.get(code)
    if not window:
        return False
    now = aware(now) or utcnow()
    start_m, start_d, end_m, end_d = window
    year = now.year
    start = datetime(year, start_m, start_d, tzinfo=timezone.utc)
    end = datetime(year, end_m, end_d, 23, 59, 59, tzinfo=timezone.utc)
    if start <= end:
        return start <= now <= end
    return now >= start or now <= end


def current_season_year(code: str, now: datetime | None = None) -> int:
    now = aware(now) or utcnow()
    if code == "MLS":
        return now.year
    if code in {"PL", "PD", "SA"}:
        return now.year if now.month >= 8 else now.year - 1
    if code == "MX":
        return now.year if now.month >= 7 else now.year - 1
    return now.year


def upcoming_window(now: datetime | None = None) -> tuple[datetime, datetime]:
    now = aware(now) or utcnow()
    start = now - timedelta(hours=GRACE_HOURS)
    end = now + timedelta(days=HORIZON_DAYS)
    return start, end


def kickoff_iso(dt: datetime | None) -> str | None:
    kick = aware(dt)
    if kick is None:
        return None
    return kick.isoformat()


def is_visible_upcoming(kickoff: datetime, status: str, now: datetime | None = None) -> bool:
    now = aware(now) or utcnow()
    kick = aware(kickoff)
    if kick is None:
        return False
    horizon = now + timedelta(days=HORIZON_DAYS)
    if status == "LIVE":
        return now - timedelta(hours=GRACE_HOURS) <= kick <= horizon
    if status != "SCHEDULED":
        return False
    return kick > now and kick <= horizon


def kickoff_is_upcoming(kickoff: datetime, now: datetime | None = None) -> bool:
    return is_visible_upcoming(kickoff, "SCHEDULED", now)


def roll_kickoff(iso: str, now: datetime | None = None) -> datetime:
    """Mueve una fecha plantilla al próximo mismo día de la semana, en el futuro."""
    now = aware(now) or utcnow()
    original = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    original = aware(original) or now
    candidate = now.replace(
        hour=original.hour,
        minute=original.minute,
        second=0,
        microsecond=0,
    )
    days_ahead = (original.weekday() - candidate.weekday()) % 7
    candidate += timedelta(days=days_ahead)
    if candidate < now + timedelta(hours=2):
        candidate += timedelta(days=7)
    return candidate


def parse_iso(value: str | None, fallback: datetime | None = None) -> datetime:
    if not value:
        return fallback or utcnow()
    raw = value.replace("Z", "+00:00")
    if len(raw) == 10:
        raw = f"{raw}T00:00:00+00:00"
    dt = datetime.fromisoformat(raw)
    return aware(dt) or utcnow()

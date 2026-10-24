"""Refresco periódico de la jornada (torneos activos)."""

from __future__ import annotations

import logging
import threading

from apscheduler.schedulers.background import BackgroundScheduler

from app.etl.calendar import REFRESH_CHECK_MINUTES
from app.infrastructure.db.session import SessionLocal

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None
_refresh_lock = threading.Lock()


def _tick() -> None:
    from app.services.live_feed import sync_feed

    db = SessionLocal()
    try:
        result = sync_feed(db)
        if result.get("status") not in {"fresh", "busy"}:
            logger.info("calendar tick %s", result.get("status"))
    except Exception:
        logger.exception("calendar tick failed")
    finally:
        db.close()


def request_refresh() -> None:
    """Lanza un sync en segundo plano para no bloquear el GET de la jornada."""
    if not _refresh_lock.acquire(blocking=False):
        return

    def _run() -> None:
        try:
            _tick()
        finally:
            _refresh_lock.release()

    threading.Thread(target=_run, name="forma-refresh", daemon=True).start()


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        _tick,
        "interval",
        seconds=60,
        id="forma-calendar",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    _scheduler.add_job(_rosters, "interval", hours=24, id="velar-rosters", max_instances=1, coalesce=True)
    _scheduler.add_job(_specialists, "interval", hours=6, id="velar-specialists", max_instances=1, coalesce=True)
    _scheduler.add_job(_odds, "interval", hours=24, id="velar-odds", max_instances=1, coalesce=True)
    _scheduler.start()
    logger.info("Scheduler de resultados cada 60 segundos; calendario cada 3 horas")


def _rosters():
    from app.services.roster_feed import sync_rosters
    with SessionLocal() as db:
        try:
            sync_rosters(db)
        except Exception:
            db.rollback()
            logger.exception("No se pudieron actualizar plantillas")


def _specialists():
    from app.services.market_pipeline import train_specialists
    from app.services.feed_lock import feed_lock
    if not feed_lock.acquire(blocking=False):
        return
    try:
        with SessionLocal() as db:
            train_specialists(db)
            from app.services.odds_feed import fit_combiner
            fit_combiner(db)
    except Exception:
        logger.exception("No se completó el entrenamiento especializado; se conservan modelos vigentes")
    finally:
        feed_lock.release()


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is None:
        return
    try:
        _scheduler.shutdown(wait=False)
    except Exception:
        logger.exception("No se pudo detener el scheduler")
    _scheduler = None


def _odds():
    from app.services.odds_feed import sync_odds
    with SessionLocal() as db:
        try:
            sync_odds(db)
        except Exception:
            db.rollback()
            logger.error("Momios temporalmente no disponibles; se conserva el modelo estadístico")

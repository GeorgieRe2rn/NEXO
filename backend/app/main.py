from contextlib import asynccontextmanager
import logging
import threading

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.api.v1.auth import router as auth_router
from app.api.v1.router import router as v1
from app.api.v1.forecasts import router as forecast_router
from app.core.bootstrap import bootstrap_admin
from app.core.config import get_settings
from app.infrastructure.db.session import Base, SessionLocal, engine, migrate_schema

logger = logging.getLogger(__name__)


def _boot_data() -> None:
    db = SessionLocal()
    try:
        bootstrap_admin(db)
        from app.core.scheduler import _specialists
        _specialists()
        from app.core.scheduler import _odds
        _odds()
        from app.services.live_feed import sync_feed

        try:
            sync_feed(db)
        except Exception:
            logger.exception("ETL inicial falló; el API sigue en pie")
        from app.services.roster_feed import sync_rosters
        try:
            sync_rosters(db)
        except Exception:
            db.rollback()
            logger.exception("Plantillas iniciales no disponibles")
    except Exception:
        logger.exception("Bootstrap falló")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    migrate_schema()
    from app.infrastructure.db.session import migrate_selection_lines
    migrate_selection_lines()
    from app.services.forecasts import enforce_observed_data
    with SessionLocal() as db:
        enforce_observed_data(db)
    from app.core.scheduler import start_scheduler, stop_scheduler

    start_scheduler()
    threading.Thread(target=_boot_data, name="forma-boot", daemon=True).start()
    yield
    stop_scheduler()


settings = get_settings()
app = FastAPI(
    title="Nexo",
    description="Análisis de forma reciente. Últimos cinco partidos.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs" if settings.app_env != "production" else None,
    redoc_url=None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.include_router(v1, prefix="/api/v1")
app.include_router(forecast_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["X-DNS-Prefetch-Control"] = "off"
    if settings.app_env == "production":
        response.headers["Strict-Transport-Security"] = "max-age=15552000; includeSubDomains"
    return response


@app.get("/")
def root():
    return {"name": "Velar", "health": "/api/v1/health"}

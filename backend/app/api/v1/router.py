from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.api.v1.auth import require_admin
from app.etl.enrich import run_enrich
from app.etl.fotmob_stats import run_fotmob_stats
from app.etl.pipeline import run_etl
from app.etl.rosters import run_roster_ingest
from app.infrastructure.db.models import User
from app.infrastructure.db.models import ApiCache, EtlRun, League, Match, Player, PlayerFormSnapshot, Prediction, TeamFormSnapshot
from app.infrastructure.db.session import ACTIVE_DATABASE_URL, get_db
from app.services.match_service import (
    admin_overview,
    get_match_detail,
    get_team_detail,
    league_leaders,
    list_league_players,
    list_league_teams,
    list_leagues,
    list_upcoming,
)

router = APIRouter()


@router.get("/models/audit")
def model_audit(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    from app.services.training_history import audit_history
    return audit_history(db)


@router.get("/metrics")
def metrics(league: str = Query("ALL",max_length=8), db: Session = Depends(get_db), _: User = Depends(require_admin)):
    from app.services.metrics import knowledge_metrics

    return knowledge_metrics(db,league.upper())


@router.get("/health")
def health():
    settings = get_settings()
    dialect = "postgresql" if "postgresql" in ACTIVE_DATABASE_URL else "sqlite"
    return {
        "status": "ok",
        "source": settings.data_source,
        "dialect": dialect,
        "api_football": settings.has_api_football,
        "football_data": settings.has_football_data,
        "time": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/leagues")
def leagues(db: Session = Depends(get_db)):
    return {"items": list_leagues(db)}


@router.get("/leagues/{code}/standings")
def standings(code: str, db: Session = Depends(get_db)):
    from app.services.standings import league_standings
    return league_standings(db, code.upper())


@router.get("/matches")
def matches(league: str | None = Query(default="ALL"), db: Session = Depends(get_db)):
    items = list_upcoming(db, league)
    if not items:
        from app.core.scheduler import request_refresh

        request_refresh()
    return {"items": items}


@router.get("/feed")
def feed(league: str = Query(default="ALL", max_length=8), db: Session = Depends(get_db)):
    from app.services.live_feed import feed_metadata
    from app.services.match_service import list_feed_matches
    return {"items":list_feed_matches(db, league.upper()), "meta":feed_metadata(db)}


@router.post("/feed/refresh")
def refresh_feed(_: User = Depends(require_admin)):
    from app.core.scheduler import request_refresh
    request_refresh()
    return {"status":"queued"}


@router.get("/matches/{match_id}")
def match_detail(match_id: int, db: Session = Depends(get_db)):
    detail = get_match_detail(db, match_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Partido no encontrado")
    return detail


@router.post("/etl/run")
def etl_run(
    source: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return run_etl(db, source=source)


@router.post("/etl/rosters")
def etl_rosters(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    from app.services.roster_feed import sync_rosters
    return sync_rosters(db)


@router.post("/etl/enrich")
def etl_enrich(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return run_enrich(db)


@router.post("/etl/fotmob")
def etl_fotmob(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return run_fotmob_stats(db)


@router.get("/leagues/{code}/teams")
def league_teams(code: str, db: Session = Depends(get_db)):
    items = list_league_teams(db, code.upper())
    if not items and not db.query(League).filter(League.code == code.upper()).first():
        raise HTTPException(status_code=404, detail="Liga no encontrada")
    return {"items": items}


@router.get("/leagues/{code}/players")
def league_players(code: str, db: Session = Depends(get_db)):
    if not db.query(League).filter(League.code == code.upper()).first():
        raise HTTPException(status_code=404, detail="Liga no encontrada")
    return {"items": list_league_players(db, code.upper())}


@router.get("/leagues/{code}/leaders")
def league_leaders_view(code: str, db: Session = Depends(get_db)):
    if not db.query(League).filter(League.code == code.upper()).first():
        raise HTTPException(status_code=404, detail="Liga no encontrada")
    return league_leaders(db, code.upper())


@router.get("/admin/overview")
def overview(league: str = Query("ALL",max_length=8),db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return admin_overview(db,league.upper())


@router.get("/teams/{team_id}")
def team_detail(team_id: int, db: Session = Depends(get_db)):
    detail = get_team_detail(db, team_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")
    return detail


@router.get("/pipeline")
def pipeline(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    last = db.query(EtlRun).order_by(EtlRun.id.desc()).limit(8).all()
    cache_count = db.query(func.count(ApiCache.cache_key)).scalar() or 0
    cache_hits = db.query(func.coalesce(func.sum(ApiCache.hit_count), 0)).scalar() or 0
    return {
        "constraint": "Las predicciones usan exclusivamente los últimos 5 partidos de cada equipo. La jornada solo incluye torneos activos y se actualiza sola.",
        "knowledge_tables": {
            "team_form_snapshots": db.query(func.count(TeamFormSnapshot.id)).scalar() or 0,
            "player_form_snapshots": db.query(func.count(PlayerFormSnapshot.id)).scalar() or 0,
            "predictions": db.query(func.count(Prediction.id)).scalar() or 0,
        },
        "cache": {"entries": cache_count, "cumulative_hits": int(cache_hits)},
        "runs": [
            {
                "id": r.id,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "status": r.status,
                "source": r.source,
                "requests_made": r.requests_made,
                "cache_hits": r.cache_hits,
                "rows_upserted": r.rows_upserted,
                "notes": r.notes,
            }
            for r in last
        ],
        "features": [
            "Puntos de forma (W=3, D=1, L=0) en 5 partidos",
            "Media de goles a favor / en contra",
            "xG y xGA (o proxy 0.07·tiros + 0.21·tiros a puerta)",
            "Tiros, tiros a puerta, posesión, córners, tarjetas",
            "Poisson × Dixon-Coles + logística multinomial last-5",
            "Over/Under 2.5 por convolución de goles esperados",
            "Jugador clave = máximo form_score en los últimos 5",
        ],
    }


@router.get("/odds/status")
def get_odds_status(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    from app.services.odds_feed import odds_status
    return odds_status(db)


@router.post("/odds/sync")
def refresh_odds(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    from app.services.odds_feed import sync_odds
    return sync_odds(db)


@router.get("/matches/{match_id}/odds")
def match_odds(match_id: int, db: Session = Depends(get_db)):
    from app.services.odds_feed import latest_odds
    match=db.get(Match,match_id)
    if match is None: raise HTTPException(status_code=404, detail="Partido no encontrado")
    return {"odds":latest_odds(db,match)}

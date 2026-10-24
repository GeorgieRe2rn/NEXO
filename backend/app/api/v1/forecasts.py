from typing import Literal
from datetime import date, timedelta, timezone

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.v1.auth import require_user
from app.infrastructure.db.models import User
from app.infrastructure.db.session import get_db
from app.services.forecasts import learning_status, selections_report

router=APIRouter(tags=["Pronósticos académicos"])


class SelectionBody(BaseModel):
    snapshot_id: int = Field(gt=0)
    market: Literal["result","goals","corners","yellows"]
    pick: Literal["LOCAL","EMPATE","VISITANTE","OVER","UNDER"]
    line: float | None = None


@router.post("/selections",status_code=201)
def save_selection(body: SelectionBody, db: Session=Depends(get_db), user: User=Depends(require_user)):
    raise HTTPException(410,"El registro ahora es automático y utiliza exclusivamente pronósticos previos.")


@router.get("/selections")
def selections(league: str=Query("ALL",max_length=8),page: int=Query(1,ge=1),status: Literal["ALL","PENDING","WON","LOST","VOID"]="ALL",db: Session=Depends(get_db),user: User=Depends(require_user)):
    return selections_report(db,user.id,league.upper(),automatic_only=True,page=page,status=status)


@router.get("/learning")
def learning(db: Session=Depends(get_db)):
    return learning_status(db)


@router.get("/selections/diagnostics")
def diagnostics(league: str=Query("ALL",max_length=8),db: Session=Depends(get_db),user: User=Depends(require_user)):
    from app.services.error_analysis import error_analysis
    return error_analysis(db,user.id,league.upper())


@router.get("/catalog")
def event_catalog(day: date | None=None,sport: Literal["ALL","soccer","basketball","football","baseball","hockey"]="soccer",db: Session=Depends(get_db),user: User=Depends(require_user)):
    from app.etl.calendar import utcnow
    from app.services.event_catalog import catalog
    result=catalog(db,day or utcnow().astimezone(timezone(timedelta(hours=-7))).date(),sport)
    from app.infrastructure.db.models import AutomaticForecastLink, ForecastSelection
    from sqlalchemy import func
    counts=dict(db.query(AutomaticForecastLink.match_id,func.count(AutomaticForecastLink.id)).join(ForecastSelection,ForecastSelection.id==AutomaticForecastLink.selection_id).filter(AutomaticForecastLink.user_id==user.id,ForecastSelection.status!="VOID").group_by(AutomaticForecastLink.match_id).all())
    for event in result["items"]:
        event["automatic_count"]=counts.get(event.get("match_id"),0)
    return result

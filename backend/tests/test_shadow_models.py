from datetime import timedelta
from test_market_pipeline import db,setup_match,synthetic
from app.etl.calendar import utcnow
from app.services.market_pipeline import train_one,capture_shadow,settle_shadow,shadow_status
from app.services.forecasts import capture_forecasts
from app.infrastructure.db.models import ShadowForecast,ForecastSnapshot,ForecastSelection


def test_shadow_is_frozen_separate_and_settles_without_a_bet(db):
    m=setup_match(db)
    train_one(db,'result','PRE',synthetic('result'))
    capture_forecasts(db,[m])
    row=db.query(ShadowForecast).one()
    original=dict(row.payload)
    assert db.query(ForecastSelection).count()==0
    assert capture_shadow(db,[m])==0
    m.status='FINISHED';m.home_goals=2;m.away_goals=1
    m.live_data={'period':2,'final_details':True}
    settle_shadow(db)
    assert row.outcomes=={'target':0}
    assert row.payload==original
    assert shadow_status(db,'result','PRE')['evaluated']==1
    assert db.query(ForecastSelection).count()==0


def test_shadow_never_backfills_a_prematch_after_kickoff(db):
    m=setup_match(db)
    train_one(db,'result','PRE',synthetic('result'))
    m.kickoff=utcnow()-timedelta(hours=1)
    assert capture_shadow(db,[m])==0
    assert db.query(ShadowForecast).count()==0

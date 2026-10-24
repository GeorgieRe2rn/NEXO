from datetime import timedelta
from types import SimpleNamespace
from app.etl.calendar import utcnow
from app.services.global_form import extract_history, build_prediction
from test_live_feed import db, event
from app.services.live_feed import persist_event
from app.infrastructure.db.models import League, Prediction
from app.services.forecasts import active_revision, build_payload


def history(match):
    groups=[]
    for team in (match.home_team,match.away_team):
        groups.append({"team":{"id":str(team.espn_id)},"events":[{"id":str(team.espn_id*100+i),"gameDate":(utcnow()-timedelta(days=i+1)).isoformat(),"homeTeamId":str(team.espn_id),"awayTeamId":"99","homeTeamScore":"2","awayTeamScore":"1","opponent":{"displayName":"Opponent"},"leagueName":"Published league"} for i in range(5)]})
    return {"lastFiveGames":groups}


def test_global_history_requires_five_and_never_uses_live_score(db):
    league=db.query(League).one()
    match=persist_event(db,league,event(status="pre",kickoff=utcnow()+timedelta(days=1)),utcnow())
    source=history(match)
    match.live_data={"global_history":extract_history(source,match)}
    assert build_prediction(db,match)
    before=db.query(Prediction).one().p_home
    payload=build_payload(db,match,"PRE",active_revision(db))
    assert set(payload["markets"])=={"result","goals","corners","yellows"}
    match.home_goals=10
    assert build_prediction(db,match)
    assert db.query(Prediction).one().p_home==before
    match.status="LIVE"
    assert not build_prediction(db,match)
    match.status="SCHEDULED"
    match.live_data={"global_history":{"home":[],"away":[]}}
    assert not build_prediction(db,match)


def test_history_deduplicates_and_excludes_current_future_invalid_and_old(db):
    match=persist_event(db,db.query(League).one(),event(status="pre",kickoff=utcnow()+timedelta(days=1)),utcnow())
    source=history(match)
    rows=source["lastFiveGames"][0]["events"]
    rows.extend([dict(rows[0]),dict(rows[0],id=match.provider_id),dict(rows[0],id="future",gameDate=(utcnow()+timedelta(days=2)).isoformat()),dict(rows[0],id="old",gameDate=(utcnow()-timedelta(days=400)).isoformat()),dict(rows[0],id="invalid",homeTeamScore="NaN")])
    result=extract_history(source,match)
    assert len(result["home"])==5
    assert all(r["goals"]==2 for r in result["home"])


def test_global_pre_registers_four_automatic_markets_once_and_settles(db):
    from app.infrastructure.db.models import User, ForecastSelection
    from app.services.forecasts import capture_forecasts, record_automatic_selections, settle_forecasts
    match=persist_event(db,db.query(League).one(),event(status="pre",kickoff=utcnow()+timedelta(days=1)),utcnow())
    match.live_data={"global_history":extract_history(history(match),match)}
    assert build_prediction(db,match)
    db.add(User(username="global-test",password_hash="unused",role="admin",created_at=utcnow()))
    db.commit()
    capture_forecasts(db,[match])
    record_automatic_selections(db,[match])
    record_automatic_selections(db,[match])
    rows=db.query(ForecastSelection).all()
    assert len(rows)==2 and {r.market for r in rows}=={"result","goals"}
    match.status="FINISHED";match.home_goals=2;match.away_goals=1
    match.live_data={**match.live_data,"period":2,"final_details":True,"stats":{"home":{"corners":6,"yellows":2},"away":{"corners":4,"yellows":3}}}
    settle_forecasts(db,[match])
    assert all(r.status in ("WON","LOST") for r in rows)
    assert {r.market:r.result_value for r in rows}=={"result":0,"goals":3}

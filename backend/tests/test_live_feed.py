from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.infrastructure.db.models import League, Match, MatchStat, Prediction, Team
from app.infrastructure.db.session import Base, get_db
from app.services.live_feed import apply_summary, feed_metadata, map_status, persist_event
from app.services.match_service import get_match_detail, list_feed_matches

NOW = datetime.now(timezone.utc)


def test_feed_keeps_evening_on_last_local_day_but_excludes_next_day(db,monkeypatch):
    from app.services import match_service
    frozen=datetime(2026,10,16,7,tzinfo=timezone.utc)
    monkeypatch.setattr(match_service,"utcnow",lambda:frozen)
    league=db.query(League).one()
    inside=event(status="pre",kickoff=datetime(2026,10,26,3,tzinfo=timezone.utc))
    outside=event(status="pre",kickoff=datetime(2026,10,26,7,tzinfo=timezone.utc))
    outside["id"]="556"
    visible=persist_event(db,league,inside,frozen)
    persist_event(db,league,outside,frozen)
    db.commit()
    assert [m["id"] for m in list_feed_matches(db)]==[visible.id]


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread":False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(League(code="MLS",name="MLS",country="USA",season=NOW.year))
        session.commit()
        yield session
    engine.dispose()


def event(status="in", score="1", kickoff=None):
    return {"id":"555","date":(kickoff or NOW-timedelta(minutes=30)).isoformat(),"competitions":[{
        "date":(kickoff or NOW-timedelta(minutes=30)).isoformat(),"timeValid":True,
        "status":{"displayClock":"30'","type":{"state":status,"completed":status=="post"}},
        "competitors":[{"homeAway":"home","score":score,"team":{"id":"12","displayName":"Example Home","abbreviation":"HOM"}},
                       {"homeAway":"away","score":"0","team":{"id":"13","displayName":"Example Away","abbreviation":"AWY"}}]}]}


def test_status_cannot_invent_live_and_preserves_cancellation():
    assert map_status({"type":{"name":"STATUS_POSTPONED","state":"pre"}})=="POSTPONED"
    assert map_status({"type":{"name":"STATUS_CANCELED","state":"post"}})=="CANCELLED"
    assert map_status({"type":{"state":"pre"}})=="SCHEDULED"
    assert map_status({"type":{"state":"in"}})=="LIVE"


def test_live_fouls_keep_the_confirmed_team_identity(db):
    m=persist_event(db,db.query(League).one(),event(),NOW)
    data={"header":event(),"keyEvents":[{"id":"foul-1","type":{"type":"foul-committed"},"team":{"id":"12"},"clock":{"displayValue":"30'","value":1800},"text":"Foul committed."}]}
    apply_summary(db,m,data,NOW)
    action=m.live_data['events'][0]
    assert action['type']=='foul-committed'
    assert action['team_id']=='12' and action['team']=='Example Home'


def test_clock_anchor_changes_only_with_source_clock_and_pauses_at_halftime(db):
    league=db.query(League).one()
    m=persist_event(db,league,event(),NOW)
    anchor=m.live_data['clock_reported_at']
    persist_event(db,league,event(),NOW+timedelta(seconds=15))
    assert m.live_data['clock_reported_at']==anchor
    assert m.live_data['clock_running'] is True
    data=event();data['competitions'][0]['status']['displayClock']="31'"
    persist_event(db,league,data,NOW+timedelta(seconds=30))
    assert m.live_data['clock_reported_at']!=anchor
    data['competitions'][0]['status'].update(displayClock='HT',type={'state':'in','name':'STATUS_HALFTIME'})
    persist_event(db,league,data,NOW+timedelta(seconds=45))
    assert m.live_data['clock_running'] is False


def test_idempotent_scores_and_corner_updates_keep_prediction(db):
    league = db.query(League).one()
    match = persist_event(db,league,event(),NOW)
    ident = match.id
    db.add(Prediction(match_id=ident,p_home=.6,p_draw=.2,p_away=.2,p_over_25=.5,p_under_25=.5,
        lambda_home=1,lambda_away=1,confidence=.5,confidence_label="MEDIA",pick="LOCAL",explanation={},computed_at=NOW-timedelta(hours=2)))
    db.commit()
    summary = {"header":event(score="2"),"boxscore":{"teams":[
        {"team":{"id":"12"},"statistics":[{"name":"wonCorners","displayValue":"5"}]},
        {"team":{"id":"13"},"statistics":[{"name":"wonCorners","displayValue":"0"}]}]},
        "keyEvents":[{"id":"goal","type":{"type":"goal"},"clock":{"displayValue":"29'","value":1740},"text":"Goal"}],
        "commentary":[{"play":{"id":"goal","type":{"type":"goal"},"clock":{"displayValue":"29'","value":1740},"text":"Goal"}}]}
    apply_summary(db,match,summary,NOW)
    db.commit()
    assert db.query(Match).count()==1
    assert match.id==ident and match.home_goals==2
    assert match.live_data["stats"]["home"]["corners"]==5
    assert match.live_data["stats"]["away"]["corners"]==0
    assert len(match.live_data["events"])==1
    assert db.query(Prediction).one().p_home==.6
    persist_event(db,league,event(status="post",score="3"),NOW)
    db.commit()
    assert match.status=="FINISHED"
    assert db.query(Prediction).count()==1
    summary["header"] = event(status="post",score="3")
    apply_summary(db,match,summary,NOW)
    db.commit()
    assert db.query(MatchStat).count()==2
    assert db.query(MatchStat).filter_by(team_id=match.home_team_id).one().corners==5


def test_summary_wrong_identity_rejected(db):
    m=persist_event(db,db.query(League).one(),event(),NOW)
    with pytest.raises(ValueError): apply_summary(db,m,{"header":{"id":"999"}},NOW)


def test_stale_live_not_labeled_as_current_and_scheduled_not_scored(db):
    m=persist_event(db,db.query(League).one(),event(),NOW-timedelta(minutes=8))
    db.commit()
    row=list_feed_matches(db)[0]
    assert row["stale"] is True
    assert row["status_label"]=="Estado por confirmar"
    assert get_match_detail(db,m.id)["status_label"]=="Estado por confirmar"
    persist_event(db,m.league,event(status="pre"),NOW)
    db.commit()
    row=list_feed_matches(db)[0]
    assert row["status"]=="SCHEDULED" and row["home_goals"] is None
    assert row["status_label"]=="Esperando confirmación"


def test_api_feed_utc_dates_and_refresh_protected(db):
    from app.api.v1.router import router
    persist_event(db,db.query(League).one(),event(),NOW)
    db.commit()
    app=FastAPI()
    app.include_router(router,prefix="/api/v1")
    app.dependency_overrides[get_db]=lambda:db
    with TestClient(app) as client:
        r=client.get("/api/v1/feed")
        assert r.status_code==200
        assert r.json()["items"][0]["kickoff"].endswith("+00:00")
        assert r.json()["meta"]["timezone"]=="America/Hermosillo"
        assert client.post("/api/v1/feed/refresh").status_code==401
        assert client.get("/api/v1/feed?league=PL").json()["items"]==[]


def test_no_unverified_or_demonstration_events_in_feed(db):
    m=persist_event(db,db.query(League).one(),event(),NOW)
    m.verified_at=None
    db.commit()
    assert list_feed_matches(db)==[]
    assert all(l["stale"] for l in feed_metadata(db)["leagues"])


def test_no_predictions_without_five_prior_games(db):
    from app.services.knowledge import rebuild_knowledge
    match=persist_event(db,db.query(League).one(),event(status="pre",kickoff=NOW+timedelta(days=1)),NOW)
    db.commit()
    rebuild_knowledge(db)
    assert db.query(Prediction).count()==0
    assert get_match_detail(db,match.id)["home"]["form"]["matches_used"]==0


def test_admin_coverage_excludes_legacy_teams(db):
    from app.services.match_service import admin_overview
    league = db.query(League).one()
    persist_event(db,league,event(status="pre",kickoff=NOW+timedelta(days=1)),NOW)
    db.add(Team(league_id=league.id,name="Legacy",short_name="Legacy",tla="LEG"))
    db.commit()
    result = admin_overview(db)
    assert result["equipos"]==2
    assert result["jugadores"]==0
    assert result["pronosticos"]=={"LOCAL":0,"EMPATE":0,"VISITANTE":0}


def test_history_completes_league_window_without_cup_or_future_leakage(db, monkeypatch):
    from app.services.live_feed import fill_history
    league = db.query(League).one()
    upcoming = persist_event(db,league,event(status="pre",kickoff=NOW+timedelta(days=1)),NOW)
    db.commit()
    history=[]
    for i in range(7):
        past=event(status="post",kickoff=NOW-timedelta(days=i+1))
        past["id"]=str(600+i)
        past["league"]={"slug":"usa.1" if i<5 else "concacaf.leagues.cup"}
        history.append(past)
    future=event(status="post",kickoff=NOW+timedelta(days=2))
    future["id"]="700"
    future["league"]={"slug":"usa.1"}
    history.append(future)
    monkeypatch.setattr("app.services.live_feed.get_json",lambda *a,**k:{"events":history})
    fill_history(db,[upcoming],NOW)
    assert db.query(Match).filter(Match.status=="FINISHED").count()==5
    assert db.query(MatchStat).count()==10
    assert db.query(Match).filter(Match.provider_id=="700").count()==0

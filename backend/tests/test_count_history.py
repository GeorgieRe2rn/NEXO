from copy import deepcopy
from datetime import timedelta
import pytest
from test_live_feed import db, event, NOW
from app.infrastructure.db.models import CountObservation, League, MatchStat
from app.services.live_feed import persist_event
from app.services.count_history import counter, store_summary, history_rows, backfill_count_history


def summary(match, corners="0", yellows="2"):
    e=event(status="post",kickoff=match.kickoff)
    e["id"]=match.provider_id
    return {"header":{**e,"league":{"slug":"usa.1"}},"boxscore":{"teams":[
        {"team":{"id":"12"},"statistics":[{"name":"wonCorners","displayValue":corners},{"name":"yellowCards","displayValue":yellows}]},
        {"team":{"id":"13"},"statistics":[{"name":"wonCorners","displayValue":"3"},{"name":"yellowCards","displayValue":"1"}]}]}}


def test_published_counts_are_isolated_and_keep_real_zero(db):
    m=persist_event(db,db.query(League).one(),event(status="post"),NOW)
    before=deepcopy(m.live_data);score=(m.home_goals,m.away_goals)
    row=store_summary(db,m,summary(m),NOW)
    assert row.home_corners==0 and row.away_corners==3
    assert row.home_yellows==2 and row.away_yellows==1
    assert m.live_data==before and (m.home_goals,m.away_goals)==score
    assert db.query(MatchStat).count()==0
    store_summary(db,m,summary(m),NOW)
    assert db.query(CountObservation).count()==1


def test_absent_and_invalid_counts_never_become_zero(db):
    m=persist_event(db,db.query(League).one(),event(status="post"),NOW)
    row=store_summary(db,m,summary(m,corners="--",yellows=None),NOW)
    assert row.home_corners is None and row.home_yellows is None
    for value in (None,"--",float("nan"),-1,2.5,True):assert counter(value) is None


@pytest.mark.parametrize("change",["id","league","teams","date","unfinished"])
def test_wrong_or_unconfirmed_summary_is_rejected(db,change):
    m=persist_event(db,db.query(League).one(),event(status="post"),NOW)
    data=summary(m)
    if change=="id":data["header"]["id"]="wrong"
    if change=="league":data["header"]["league"]["slug"]="eng.1"
    if change=="teams":data["header"]["competitions"][0]["competitors"][0]["team"]["id"]="99"
    if change=="date":data["header"]["competitions"][0]["date"]=(NOW+timedelta(days=1)).isoformat()
    if change=="unfinished":data["header"]["competitions"][0]["status"]["type"]["completed"]=False
    with pytest.raises(ValueError):store_summary(db,m,data,NOW)
    assert db.query(CountObservation).count()==0


def test_backfill_reads_historical_summary_then_uses_cache(db,monkeypatch):
    league=db.query(League).one()
    past=persist_event(db,league,event(status="post",kickoff=NOW-timedelta(days=1)),NOW)
    future_event=event(status="pre",kickoff=NOW+timedelta(days=1));future_event["id"]="556"
    future=persist_event(db,league,future_event,NOW)
    calls=[]
    def fetch(*args):calls.append(args);return summary(past)
    monkeypatch.setattr("app.services.live_feed.get_json",fetch)
    assert backfill_count_history(db,[future],NOW)["stored"]==1
    assert backfill_count_history(db,[future],NOW)["requested"]==0
    assert len(calls)==1
    rows,coverage=history_rows(db,future,"corners")
    assert len(rows)==1 and rows[0]["total"]==3
    assert coverage=={"home":1,"away":1}

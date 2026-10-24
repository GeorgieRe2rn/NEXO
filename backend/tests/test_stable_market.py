from datetime import timedelta
from types import SimpleNamespace
from copy import deepcopy
import pytest
from test_market_pipeline import db, setup_match
from app.etl.calendar import utcnow, kickoff_iso
from app.infrastructure.db.models import OddsObservation
from app.services.stable_market import reference, select_references, POLICY
from app.services.odds_feed import apply_odds


def payload(at, probabilities=(.5,.28,.22)):
    books=[]
    for key in ("a","b","c"):
        books.append({"key":key,"name":key.upper(),"markets":{"result":{"prices":[1/v for v in probabilities],"probabilities":list(probabilities),"updated_at":kickoff_iso(at-timedelta(minutes=2))},"goals":{"prices":[2.,2.],"probabilities":[.5,.5],"line":2.5,"updated_at":kickoff_iso(at-timedelta(minutes=2))}}})
    return {"bookmakers":books,"result":list(probabilities),"goals_mean":2.67,"captured_at":kickoff_iso(at),"provider":"test"}


def test_one_capture_means_concordance_not_measured_temporal_stability():
    now=utcnow();s=select_references(payload(now),[],now,now)
    assert s["result"]["initial_weight"]==.1
    assert s["result"]["state"]=="cross_source_only"
    assert s["result"]["movement"] is None


def test_regional_duplicates_cannot_supply_three_independent_confirmations():
    now=utcnow();p=payload(now)
    for b,key in zip(p["bookmakers"],("unibet_nl","unibet_se","third")):b["key"]=key
    assert not reference(p["bookmakers"],"result",now)["available"]


def test_outlier_never_drags_consensus_to_largest_payout():
    now=utcnow();p=payload(now);bad=deepcopy(p["bookmakers"][0]);bad["key"]="outlier";bad["markets"]["result"]["probabilities"]=[.1,.1,.8];bad["markets"]["result"]["prices"]=[10,10,1.25];p["bookmakers"].append(bad)
    s=reference(p["bookmakers"],"result",now)
    assert s["value"]==pytest.approx([.5,.28,.22]) and s["sources"]==3
    assert s["selected_book"]["key"]!="outlier"


def test_temporal_observations_control_weight_and_suspend_moving_market():
    now=utcnow();before=now-timedelta(hours=1)
    previous=SimpleNamespace(captured_at=before,payload=payload(before))
    s=select_references(payload(now),[previous],now,now)["result"]
    assert s["initial_weight"]==.2 and s["state"]=="stable_observed"
    moved=select_references(payload(now,(.7,.2,.1)),[previous],now,now)["result"]
    assert moved["state"]=="moving" and moved["initial_weight"]==0


def test_stale_quotes_and_mixed_lines_cannot_create_stable_reference():
    now=utcnow();p=payload(now-timedelta(days=2))
    assert not reference(p["bookmakers"],"result",now)["available"]
    p=payload(now)
    for i,b in enumerate(p["bookmakers"]):b["markets"]["goals"]["line"]=i+1.5
    assert not reference(p["bookmakers"],"goals",now)["available"]


def test_experimental_consensus_actually_enters_prediction_and_never_live(db):
    m=setup_match(db);now=utcnow()
    db.add(OddsObservation(match_id=m.id,captured_at=now,payload=payload(now)));db.commit()
    base=[.2,.3,.5]
    value,meta=apply_odds(db,m,"PRE",base)
    assert value==pytest.approx([.23,.298,.472])
    assert sum(value)==pytest.approx(1)
    assert meta["weight"]==.1 and meta["state"]=="experimental_rule" and meta["reference_policy"]==POLICY
    assert apply_odds(db,m,"LIVE",base)==(base,None)
    m.status="LIVE"
    assert apply_odds(db,m,"PRE",base)==(base,None)

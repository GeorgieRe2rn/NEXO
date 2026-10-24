from datetime import timedelta
import math
import pytest
from test_market_pipeline import db, setup_match
from app.etl.calendar import utcnow, kickoff_iso
from app.infrastructure.db.models import OddsObservation, Match, ForecastSnapshot
from app.services.odds_feed import devig, match_event, normalize_event, latest_odds, apply_odds, fit_combiner
from app.services.forecasts import active_revision
from app.services.market_pipeline import deployment


def event_for(m):
    return {"id":"external", "commence_time":kickoff_iso(m.kickoff),"home_team":"Home","away_team":"Away","bookmakers":[{"key":"test","title":"Test","last_update":kickoff_iso(utcnow()-timedelta(minutes=2)),"markets":[{"key":"h2h","outcomes":[{"name":"Home","price":2.0},{"name":"Draw","price":3.0},{"name":"Away","price":4.0}]},{"key":"totals","outcomes":[{"name":"Over","price":2.,"point":2.5},{"name":"Under","price":2.,"point":2.5}]}]}]}


def test_margin_removed_and_invalid_quotes_rejected():
    p=devig([2,3,4]);assert sum(p)==pytest.approx(1)
    assert p==pytest.approx([6/13,4/13,3/13])
    for prices in ([0,2],[1,3],[math.nan,2],[True,2],[math.inf,2],[]):assert devig(prices) is None


def test_matching_requires_both_teams_same_order_time_and_unique(db):
    m=setup_match(db);event=event_for(m)
    assert match_event(event,[m]) is m
    assert match_event(event,[m,m]) is None
    assert match_event({**event,"away_team":"Other"},[m]) is None
    assert match_event({**event,"commence_time":kickoff_iso(m.kickoff+timedelta(hours=2))},[m]) is None


def test_real_quotes_derive_probabilities_without_fake_missing_markets(db):
    m=setup_match(db);p=normalize_event(event_for(m),utcnow())
    assert sum(p["result"])==pytest.approx(1)
    assert 2<p["goals_mean"]<3
    assert "corners" not in p and "yellows" not in p
    event=event_for(m);event["bookmakers"][0]["last_update"]=kickoff_iso(utcnow()+timedelta(hours=1))
    assert normalize_event(event,utcnow())["result"] is None


def test_stale_and_post_kickoff_quotes_never_affect_model(db):
    m=setup_match(db);now=utcnow()
    db.add(OddsObservation(match_id=m.id,captured_at=now-timedelta(days=2),payload=normalize_event(event_for(m),now)))
    db.flush();base=[.4,.3,.3]
    value,meta=apply_odds(db,m,"PRE",base)
    assert value==base and meta["stale"]
    assert apply_odds(db,m,"LIVE",base)==(base,None)
    m.kickoff=now-timedelta(days=3)
    assert latest_odds(db,m) is None


def test_only_frozen_distinct_prematch_examples_train_combiner(db):
    m=setup_match(db);revision=active_revision(db)
    for i in range(220):
        kickoff=utcnow()-timedelta(days=230-i)
        game=Match(provider="espn",provider_id=f"odds-{i}",league_id=m.league_id,home_team_id=m.home_team_id,away_team_id=m.away_team_id,kickoff=kickoff,status="FINISHED",verified_at=utcnow(),home_goals=1,away_goals=0)
        db.add(game);db.flush()
        target=i%3;p=[.01]*3;p[target]=.98
        odds={"reference_policy":"stable-market-v1","result":p,"goals_mean":2.,"stale":False,"captured_at":kickoff_iso(kickoff-timedelta(hours=2)),"model_deployment":deployment(db)}
        payload={"specialists":{"result":{"without_odds":[1/3]*3,"odds":odds},"goals":{"without_odds":3.,"odds":odds}}}
        for j in range(2):
            db.add(ForecastSnapshot(match_id=game.id,phase="PRE",fingerprint=f"o-{i}-{j}",revision_id=revision.id,created_at=kickoff-timedelta(hours=1),source_at=kickoff-timedelta(hours=1),payload=payload,outcomes={"result":target,"goals":2},evaluated_at=utcnow()))
    db.commit();reports=fit_combiner(db)
    assert reports["result"]["samples"]==220
    assert reports["result"]["weight"]>0
    assert reports["goals"]["weight"]>0
    # Repetir no reutiliza el mismo bloque para ajustar o volver a adoptar.
    assert fit_combiner(db)==reports


def test_adding_odds_creates_frozen_snapshot_even_when_weight_is_zero(db):
    from app.services.forecasts import capture_forecasts
    m=setup_match(db)
    capture_forecasts(db,[m])
    first=db.query(ForecastSnapshot).filter_by(match_id=m.id,phase="PRE").order_by(ForecastSnapshot.id.desc()).first()
    assert not first.payload["specialists"]["result"]["odds"]
    base=first.payload["base"]["result"]
    db.add(OddsObservation(match_id=m.id,captured_at=utcnow(),payload=normalize_event(event_for(m),utcnow())))
    db.commit()
    assert capture_forecasts(db,[m])==1
    latest=db.query(ForecastSnapshot).filter_by(match_id=m.id,phase="PRE").order_by(ForecastSnapshot.id.desc()).first()
    assert latest.id!=first.id and latest.payload["base"]["result"]==base
    assert latest.payload["specialists"]["result"]["odds"]["weight"]==0
    assert capture_forecasts(db,[m])==0

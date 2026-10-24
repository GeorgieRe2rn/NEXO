from datetime import timedelta
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.infrastructure.db.session import Base
from app.infrastructure.db.models import League,Team,Match,ForecastRevision,ForecastSnapshot,MarketLearner
from app.etl.calendar import utcnow
from app.services.market_pipeline import SCHEMA,FEATURES,Evidence,temporal_split,train_one,specialist,deployment
from app.services.forecasts import active_revision,learning_samples,capture_forecasts
from app.ml.markets import DEFAULT_PARAMETERS

@pytest.fixture
def db():
    engine=create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as session:yield session


def setup_match(db):
    league=League(code='PL',name='Premier',country='GB',season=2026)
    db.add(league);db.flush()
    h=Team(league_id=league.id,name='Home',short_name='H',tla='H',espn_id=1)
    a=Team(league_id=league.id,name='Away',short_name='A',tla='A',espn_id=2)
    db.add_all([h,a]);db.flush()
    now=utcnow()
    for i in range(7):
        m=Match(provider='espn',provider_id=str(100+i),league_id=league.id,home_team_id=h.id,away_team_id=a.id,kickoff=now-timedelta(days=10-i),status='FINISHED',verified_at=now,home_goals=2,away_goals=1,live_data={'final_details':True,'stats':{'home':{'corners':0},'away':{'corners':0}}})
        db.add(m)
    target=Match(provider='espn',provider_id='999',league_id=league.id,home_team_id=h.id,away_team_id=a.id,kickoff=now+timedelta(days=1),status='SCHEDULED',verified_at=now,home_goals=0,away_goals=0,live_data={})
    db.add(target);db.flush();return target


def test_features_exclude_future_self_and_imputed_counts(db):
    m=setup_match(db)
    before=Evidence(db).features(m,'goals')
    assert before and len(before['x'])==len(FEATURES)
    future=Match(provider='espn',provider_id='future',league_id=m.league_id,home_team_id=m.home_team_id,away_team_id=m.away_team_id,kickoff=m.kickoff+timedelta(hours=2),status='FINISHED',verified_at=utcnow(),home_goals=99,away_goals=99)
    db.add(future);db.flush()
    assert Evidence(db).features(m,'goals')==before
    assert Evidence(db).features(m,'yellows') is None
    assert Evidence(db).features(m,'corners')['baseline']==.05
    assert before['x'][11:]==[None]*4


def test_temporal_split_keeps_simultaneous_matches_and_gap():
    at=utcnow()-timedelta(days=400)
    rows=[{'id':i,'at':at+timedelta(days=i//3)} for i in range(300)]
    train,val,test=temporal_split(rows)
    assert max(r['at'] for r in train)+timedelta(hours=3)<min(r['at'] for r in val)
    assert max(r['at'] for r in val)+timedelta(hours=3)<min(r['at'] for r in test)
    assert not ({r['id'] for r in train}&{r['id'] for r in test})


def test_legacy_calibration_is_not_reused_and_samples_are_isolated(db):
    m=setup_match(db)
    legacy=ForecastRevision(created_at=utcnow(),adopted=True,parameters={p:{**DEFAULT_PARAMETERS,'temperature':2} for p in ('PRE','LIVE')},report={'status':'adopted'})
    db.add(legacy);db.flush()
    new=active_revision(db)
    assert new.id!=legacy.id and new.parameters['PRE']['temperature']==1
    assert active_revision(db).id==new.id
    db.add(ForecastSnapshot(match_id=m.id,revision_id=legacy.id,phase='PRE',fingerprint='legacy',created_at=utcnow(),source_at=utcnow(),evaluated_at=utcnow(),payload={'base':{}},outcomes={'result':0}))
    db.flush()
    assert learning_samples(db)==[]
    assert capture_forecasts(db,[m])==1
    payload=db.query(ForecastSnapshot).filter(ForecastSnapshot.fingerprint!='legacy').one().payload
    assert payload['architecture']==SCHEMA
    assert payload['markets']['yellows']['available'] is False
    assert payload['markets']['corners']['available'] is True
    assert sum(payload['markets']['result']['choices'].values())==pytest.approx(1)
    assert payload['specialists']['result']['family']=='Poisson observado'
    assert legacy.parameters['PRE']['temperature']==2


def synthetic(market):
    now=utcnow()-timedelta(days=400)
    rows=[]
    for i in range(240):
        signal=i%3
        x=['PL',float(signal),1.,1.,1.,1.,1.,3.,3.,.4,.6,None,None,None,None]
        rows.append({'id':i,'at':now+timedelta(days=i),'x':x,'y':signal if market=='result' else 1+signal*4,'baseline':[1/3]*3 if market=='result' else 5.})
    return rows


@pytest.mark.parametrize('market',['result','goals'])
def test_catboost_training_roundtrip_and_independent_registry(db,market):
    report=train_one(db,market,'PRE',synthetic(market))
    assert report['status']=='adopted'
    assert report['candidate']['log_loss']<report['baseline']['log_loss']
    assert report['train_end']<report['validation_start']<report['test_start']
    row=db.query(MarketLearner).one()
    assert row.model_json and row.adopted
    example=synthetic(market)[0]
    value,meta=specialist(db,market,'PRE',example['x'],example['baseline'])
    assert meta['state']=='adopted'
    if market=='result':assert sum(value)==pytest.approx(1)
    else:assert value>0
    _,live_meta=specialist(db,market,'LIVE',example['x'],example['baseline'])
    assert live_meta['state']=='baseline'
    train_one(db,market,'PRE',synthetic(market))
    assert db.query(MarketLearner).count()==1


def test_not_enough_samples_never_claims_trained(db):
    report=train_one(db,'goals','PRE',synthetic('goals')[:20])
    assert report['status']=='awaiting_evidence'
    assert db.query(MarketLearner).one().model_json is None

def test_future_selection_migrates_but_started_selection_stays_frozen(db):
    from app.infrastructure.db.models import User,ForecastSelection,AutomaticForecastLink
    m=setup_match(db)
    old=ForecastRevision(created_at=utcnow(),adopted=True,parameters={p:dict(DEFAULT_PARAMETERS) for p in ('PRE','LIVE')},report={'status':'initial'})
    user=User(username='audit',password_hash='unused',role='admin',created_at=utcnow())
    db.add_all([old,user]);db.flush()
    q=ForecastSnapshot(match_id=m.id,revision_id=old.id,phase='PRE',fingerprint='old_future',created_at=utcnow(),source_at=utcnow(),payload={'model_version':'mercados-v1','base':{},'markets':{}})
    db.add(q);db.flush()
    s=ForecastSelection(user_id=user.id,snapshot_id=q.id,market='yellows',line_key=3.5,pick='OVER',probability=.7,status='PENDING',created_at=utcnow())
    db.add(s);db.flush();db.add(AutomaticForecastLink(user_id=user.id,match_id=m.id,market='yellows',selection_id=s.id));db.commit()
    capture_forecasts(db,[m])
    assert s.status=='VOID' and s.snapshot_id==q.id
    assert s.settlement_history[-1]['reason_code']==SCHEMA
    assert q.payload['model_version']=='mercados-v1'
    assert old.parameters['PRE']['temperature']==1


def test_new_attempt_cannot_reuse_the_previous_test_block(db):
    rows=synthetic('result')
    assert train_one(db,'result','PRE',rows)['status']=='adopted'
    extra=dict(rows[-1],id=999,at=rows[-1]['at']+timedelta(days=1))
    report=train_one(db,'result','PRE',rows+[extra])
    assert report['status']=='awaiting_fresh_test'
    assert db.query(MarketLearner).filter_by(adopted=True).count()==1

def test_explicit_espn_cross_competition_history_does_not_use_current_score(db):
    m=setup_match(db)
    db.query(Match).filter(Match.id!=m.id).delete(synchronize_session=False);db.flush()
    histories={side:[{'id':str(10000+i+offset),'kickoff':(utcnow()-timedelta(days=i+1)).isoformat(),'goals':2,'goals_against':1,'source_url':f'https://www.espn.com/soccer/match/_/gameId/{10000+i+offset}'} for i in range(5)] for side,offset in [('home',0),('away',10)]}
    m.live_data={'global_history':histories};db.flush()
    e=Evidence(db).features(m,'result')
    assert e is not None and e['x'][9:11]==[None,None]
    m.home_goals=99;m.away_goals=88
    assert Evidence(db).features(m,'result')==e
    assert Evidence(db).features(m,'corners') is None


def test_calibration_never_trades_a_worse_market_for_another():
    from types import SimpleNamespace
    from copy import deepcopy
    from app.services.forecasts import independent_calibration_gate
    initial={p:dict(DEFAULT_PARAMETERS) for p in ('PRE','LIVE')}
    candidate=deepcopy(initial);candidate['PRE'].update(temperature=.5,goals_scale=1.6)
    validation=[(SimpleNamespace(phase='PRE',payload={'base':{'result':{'market':'result','probabilities':[.6,.2,.2]},'goals':{'market':'goals','current':0,'remaining_mean':3.,'line':2.5}}},outcomes={'result':0,'goals':1}),None) for _ in range(10)]
    selected,checks=independent_calibration_gate(validation,candidate,initial)
    assert selected['PRE']['temperature']==.5
    assert selected['PRE']['goals_scale']==1
    assert checks['PRE:result']['adopted']
    assert not checks['PRE:goals']['adopted']

def test_v2_metrics_do_not_mix_old_predictions(db):
    from app.services.metrics import knowledge_metrics
    m=setup_match(db)
    capture_forecasts(db,[m])
    q=db.query(ForecastSnapshot).one()
    m.status='FINISHED';m.kickoff=utcnow()-timedelta(hours=3);m.home_goals=2;m.away_goals=1
    q.created_at=m.kickoff-timedelta(hours=1);q.outcomes={'result':0};q.evaluated_at=utcnow();db.flush()
    metrics=knowledge_metrics(db)
    assert metrics['evaluation']['samples']==1
    assert metrics['evaluation']['architecture']==SCHEMA
    assert metrics['legacy_evaluation']['samples']==0

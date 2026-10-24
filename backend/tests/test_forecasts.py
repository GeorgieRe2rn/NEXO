from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.etl.calendar import utcnow, kickoff_iso
from app.infrastructure.db.models import League, Team, Match, Prediction, User, ForecastSnapshot, ForecastSelection, ForecastRevision
from app.infrastructure.db.session import Base
from app.ml.markets import result_probabilities, over_probability, minute_from_clock
from app.services.forecasts import capture_forecasts, create_selection, settle_forecasts, selections_report, update_learning, learning_samples


@pytest.fixture
def sample():
    engine=create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        league=League(code='PL',name='Test',country='Test',season=2026)
        db.add(league); db.flush()
        teams=[Team(league_id=league.id,name=n,short_name=n,tla=n) for n in ('A','B')]
        db.add_all(teams); db.flush()
        user=User(username='tester',password_hash='unused',role='admin',created_at=utcnow())
        match=Match(external_id=123,provider='espn',league_id=league.id,home_team_id=teams[0].id,away_team_id=teams[1].id,kickoff=utcnow()+timedelta(hours=1),status='SCHEDULED',verified_at=utcnow(),live_data={})
        db.add_all([user,match]);db.flush()
        db.add(Prediction(match_id=match.id,p_home=.6,p_draw=.25,p_away=.15,p_over_25=.5,p_under_25=.5,lambda_home=1.8,lambda_away=.8,confidence=.6,confidence_label='MEDIA',pick='LOCAL',model_version='test',explanation={},computed_at=utcnow()))
        for i in range(5):
            db.add(Match(external_id=70000+i,provider='espn',provider_id=str(70000+i),league_id=league.id,home_team_id=teams[0].id,away_team_id=teams[1].id,kickoff=utcnow()-timedelta(days=i+1),status='FINISHED',home_goals=1,away_goals=0,verified_at=utcnow(),live_data={'final_details':True,'stats':{'home':{'corners':5,'yellows':2},'away':{'corners':4,'yellows':2}}}))
        db.commit()
        yield db,match,user


def test_conditional_distribution_and_zero_counts():
    assert result_probabilities(2,1,0,0)==[1,0,0]
    assert sum(result_probabilities(0,0,2,1))==pytest.approx(1)
    assert over_probability(0,0,2.5)==0
    assert over_probability(3,0,2.5)==1
    assert minute_from_clock('45+3')==48
    assert minute_from_clock('HT')==45
    assert minute_from_clock('Unknown') is None


def test_quote_freezes_settlement_and_corrections(sample):
    db,m,u=sample
    assert capture_forecasts(db,[m])==1
    assert capture_forecasts(db,[m])==0
    quote=db.query(ForecastSnapshot).one()
    create_selection(db,u,quote.id,'result','LOCAL')
    create_selection(db,u,quote.id,'corners','UNDER')
    with pytest.raises(HTTPException) as e: create_selection(db,u,quote.id,'result','VISITANTE')
    assert e.value.status_code==409
    m.status='FINISHED';m.home_goals=2;m.away_goals=0
    m.live_data={'period':2,'final_details':True,'stats':{'home':{'corners':None},'away':{'corners':0}}}
    settle_forecasts(db,[m])
    rows=db.query(ForecastSelection).order_by(ForecastSelection.id).all()
    assert [s.status for s in rows]==['WON','PENDING']
    assert selections_report(db,u.id)['accuracy']==1
    assert selections_report(db,u.id+1)['total']==0
    assert rows[0].probability==.6
    settle_forecasts(db,[m]);assert len(rows[0].settlement_history)==1
    m.home_goals=0;m.away_goals=2
    m.live_data={'period':2,'final_details':True,'stats':{'home':{'corners':0},'away':{'corners':0}}}
    settle_forecasts(db,[m])
    assert [s.status for s in rows]==['LOST','WON']
    assert len(rows[0].settlement_history)==2
    assert len(learning_samples(db))==1
    update_learning(db)
    assert db.query(ForecastRevision).count()==1


def test_stale_and_post_kickoff_are_rejected(sample):
    db,m,u=sample;capture_forecasts(db,[m]);q=db.query(ForecastSnapshot).one()
    m.verified_at=utcnow()-timedelta(hours=4)
    with pytest.raises(HTTPException):create_selection(db,u,q.id,'result','LOCAL')
    m.verified_at=utcnow();m.kickoff=utcnow()-timedelta(seconds=1)
    with pytest.raises(HTTPException):create_selection(db,u,q.id,'result','LOCAL')


def test_live_counter_change_invalidates_quote(sample):
    db,m,u=sample;m.status='LIVE';m.home_goals=0;m.away_goals=0
    m.live_data={'period':1,'clock':"20'",'details_at':kickoff_iso(utcnow()),'stats':{'home':{'corners':1,'yellows':0},'away':{'corners':0,'yellows':0}}}
    capture_forecasts(db,[m]);q=db.query(ForecastSnapshot).one()
    m.live_data={**m.live_data,'stats':{'home':{'corners':2,'yellows':0},'away':{'corners':0,'yellows':0}}}
    with pytest.raises(HTTPException) as e:create_selection(db,u,q.id,'corners','OVER')
    assert e.value.status_code==409
    capture_forecasts(db,[m]);assert db.query(ForecastSnapshot).count()==2
    latest=db.query(ForecastSnapshot).order_by(ForecastSnapshot.id.desc()).first()
    create_selection(db,u,latest.id,'corners','OVER')
    m.status='FINISHED';m.live_data={**m.live_data,'period':3}
    settle_forecasts(db,[m]);assert db.query(ForecastSelection).one().status=='VOID'


def test_calibration_uses_distinct_chronological_matches(sample):
    db,original,_=sample
    capture_forecasts(db,[original])
    initial=db.query(ForecastRevision).one()
    for i in range(40):
        match=Match(external_id=1000+i,provider='espn',league_id=original.league_id,home_team_id=original.home_team_id,away_team_id=original.away_team_id,kickoff=utcnow()-timedelta(days=50-i),status='FINISHED',home_goals=1,away_goals=0)
        db.add(match);db.flush()
        for minute in (0,1):
            db.add(ForecastSnapshot(match_id=match.id,phase='PRE',revision_id=initial.id,fingerprint=f'test-{i}-{minute}',created_at=match.kickoff-timedelta(hours=1,minutes=-minute),source_at=match.kickoff-timedelta(hours=1),evaluated_at=utcnow(),outcomes={'result':0},payload={'base':{'result':{'market':'result','probabilities':[.6,.25,.15]}}}))
    db.commit()
    assert len(learning_samples(db))==40
    update_learning(db)
    candidate=db.query(ForecastRevision).order_by(ForecastRevision.id.desc()).first()
    assert candidate.adopted
    assert candidate.report['train_matches']==28
    assert candidate.report['validation_matches']==12
    assert candidate.report['train_end']<candidate.report['validation_start']
    assert candidate.report['candidate_log_loss']<candidate.report['champion_log_loss']
    update_learning(db)
    assert db.query(ForecastRevision).count()==2


def test_multiple_lines_are_frozen_and_settled_independently(sample):
    from copy import deepcopy
    from app.services.forecasts import snapshot_payload
    db,m,u=sample;capture_forecasts(db,[m]);q=db.query(ForecastSnapshot).one()
    before=deepcopy(q.payload)
    public=snapshot_payload(q)
    assert list(public['markets']['goals']['lines'])==['0.5','1.5','2.5','3.5','4.5','5.5']
    assert list(public['markets']['corners']['lines'])==['6.5','7.5','8.5','9.5','10.5','11.5']
    assert list(public['markets']['yellows']['lines'])==['1.5','2.5','3.5','4.5','5.5','6.5']
    create_selection(db,u,q.id,'goals','OVER',1.5)
    create_selection(db,u,q.id,'goals','OVER',5.5)
    assert q.payload==before
    with pytest.raises(HTTPException): create_selection(db,u,q.id,'goals','UNDER',1.5)
    with pytest.raises(HTTPException): create_selection(db,u,q.id,'goals','OVER',6.5)
    m.status='FINISHED';m.home_goals=2;m.away_goals=0
    settle_forecasts(db,[m])
    rows=db.query(ForecastSelection).order_by(ForecastSelection.line_key).all()
    assert [(r.line_key,r.status) for r in rows]==[(1.5,'WON'),(5.5,'LOST')]
    report=selections_report(db,u.id)
    assert {r['line'] for r in report['items']}=={1.5,5.5}
    assert report['accuracy']==.5


def test_crossed_live_lines_are_visible_but_cannot_be_selected(sample):
    from app.services.forecasts import snapshot_payload
    db,m,u=sample;m.status='LIVE';m.home_goals=2;m.away_goals=0
    m.live_data={'period':1,'clock':"20'",'details_at':kickoff_iso(utcnow()),'stats':{'home':{'corners':4,'yellows':0},'away':{'corners':3,'yellows':0}}}
    capture_forecasts(db,[m]);q=db.query(ForecastSnapshot).one()
    assert snapshot_payload(q)['markets']['goals']['lines']['1.5']['closed']
    assert snapshot_payload(q)['markets']['corners']['lines']['6.5']['closed']
    with pytest.raises(HTTPException):create_selection(db,u,q.id,'goals','OVER',1.5)
    create_selection(db,u,q.id,'goals','OVER',5.5)


def test_existing_selections_migrate_with_original_line(sample,monkeypatch):
    from sqlalchemy import Table, Column, MetaData, select, func
    import app.infrastructure.db.session as session_module
    db,m,u=sample;capture_forecasts(db,[m]);q=db.query(ForecastSnapshot).one()
    engine=db.get_bind()
    legacy=Table('forecast_selections',MetaData(),*[Column(c.name,c.type,primary_key=c.primary_key,nullable=c.nullable) for c in ForecastSelection.__table__.columns if c.name!='line_key'])
    legacy.create(engine)
    with engine.begin() as conn:
        conn.execute(legacy.insert().values(id=1,user_id=u.id,snapshot_id=q.id,market='corners',pick='OVER',probability=.4,created_at=utcnow(),status='PENDING',settlement_history=[]))
    monkeypatch.setattr(session_module,'engine',engine)
    session_module.migrate_selection_lines()
    session_module.migrate_selection_lines()
    row=db.query(ForecastSelection).one()
    assert row.line_key==q.payload['markets']['corners']['line']
    assert row.probability==.4
    with engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(legacy))==1


def test_automatic_four_markets_are_frozen_once_and_settle(sample):
    from app.services.forecasts import record_automatic_selections
    from app.infrastructure.db.models import AutomaticForecastLink
    db,m,u=sample;capture_forecasts(db,[m])
    record_automatic_selections(db,[m])
    rows=db.query(ForecastSelection).order_by(ForecastSelection.id).all()
    assert len(rows)==db.query(AutomaticForecastLink).count()==4
    assert {s.market for s in rows}=={'result','goals','corners','yellows'}
    original=[(s.id,s.pick,s.probability,s.line_key,s.snapshot_id) for s in rows]
    assert next(s for s in rows if s.market=='result').pick=='LOCAL'
    # Nuevas revisiones y nuevas sincronizaciones no cambian la selección inicial.
    prediction=db.query(Prediction).one();prediction.p_home=.1;prediction.p_away=.8
    capture_forecasts(db,[m]);record_automatic_selections(db,[m])
    assert [(s.id,s.pick,s.probability,s.line_key,s.snapshot_id) for s in db.query(ForecastSelection).order_by(ForecastSelection.id)]==original
    report=selections_report(db,u.id,automatic_only=True)
    assert report['total']==4
    assert report['by_market']['goals']['pending']==1
    assert selections_report(db,u.id+1,automatic_only=True)['total']==0
    m.status='FINISHED';m.home_goals=2;m.away_goals=0
    m.live_data={'period':2,'final_details':True,'stats':{'home':{'corners':5},'away':{'corners':4}}}
    settle_forecasts(db,[m]);record_automatic_selections(db,[m])
    assert db.query(ForecastSelection).count()==4
    states={s.market:s.status for s in db.query(ForecastSelection)}
    assert states['result']=='WON'
    assert states['yellows']=='PENDING'
    assert states['corners'] in {'WON','LOST'}


def test_automatic_never_backfills_started_or_finished_matches(sample):
    from app.services.forecasts import record_automatic_selections
    db,m,u=sample;capture_forecasts(db,[m])
    m.kickoff=utcnow()-timedelta(minutes=1)
    record_automatic_selections(db,[m]);assert db.query(ForecastSelection).count()==0
    m.status='LIVE';record_automatic_selections(db,[m])
    m.status='FINISHED';record_automatic_selections(db,[m])
    assert db.query(ForecastSelection).count()==0


def test_automatic_history_pages_keep_entire_matches(sample):
    from copy import deepcopy
    from app.services.forecasts import record_automatic_selections
    db,m,u=sample;capture_forecasts(db,[m]);q=db.query(ForecastSnapshot).one()
    matches=[m]
    for i in range(20):
        next_match=Match(external_id=3000+i,provider='espn',league_id=m.league_id,home_team_id=m.home_team_id,away_team_id=m.away_team_id,kickoff=utcnow()+timedelta(hours=i+2),status='SCHEDULED',verified_at=utcnow())
        db.add(next_match);db.flush()
        db.add(ForecastSnapshot(match_id=next_match.id,phase='PRE',revision_id=q.revision_id,fingerprint=f'page-{i}',created_at=utcnow(),source_at=utcnow(),payload=deepcopy(q.payload)))
        matches.append(next_match)
    db.commit();record_automatic_selections(db,matches)
    first=selections_report(db,u.id,automatic_only=True,page=1)
    second=selections_report(db,u.id,automatic_only=True,page=2)
    assert first['total']==second['total']==84
    assert first['pages']==2
    assert len(first['items'])==80 and len(second['items'])==4
    assert not {r['match_id'] for r in first['items']} & {r['match_id'] for r in second['items']}
    empty=selections_report(db,u.id,automatic_only=True,status='WON')
    assert empty['items']==[] and empty['counts']['PENDING']==84


def test_live_import_uses_archived_prior_not_current_score(sample):
    from app.services.forecasts import record_automatic_selections
    db,m,u=sample
    # Un previo realmente anterior al inicio, conservado en la base.
    capture_forecasts(db,[m]);prior=db.query(ForecastSnapshot).one()
    m.kickoff=utcnow()-timedelta(minutes=20)
    prior.created_at=m.kickoff-timedelta(hours=1)
    m.status='LIVE';m.home_goals=0;m.away_goals=5
    m.live_data={'clock':"20'",'stats':{'home':{'corners':30,'yellows':10},'away':{'corners':25,'yellows':20}}}
    db.commit();record_automatic_selections(db,[m])
    rows=db.query(ForecastSelection).all()
    assert len(rows)==4
    assert next(s for s in rows if s.market=='result').pick=='LOCAL'
    imported=db.query(ForecastSnapshot).filter_by(phase='RETRO').one()
    assert imported.payload['markets']==prior.payload['markets']
    m.home_goals=10;record_automatic_selections(db,[m])
    assert db.query(ForecastSelection).count()==4
    m.status='FINISHED';settle_forecasts(db,[m])
    report=selections_report(db,u.id,automatic_only=True)
    assert report['retro_total']==4
    assert report['accuracy'] is None
    assert report['retro_accuracy'] is not None
    assert all(r.phase!='RETRO' for r,_ in learning_samples(db))


def test_legacy_prior_import_labels_reconstructed_count_markets(sample):
    from app.services.forecasts import record_automatic_selections
    db,m,u=sample
    m.kickoff=utcnow()-timedelta(minutes=10)
    prediction=db.query(Prediction).one();prediction.computed_at=m.kickoff-timedelta(hours=1)
    m.status='LIVE';m.home_goals=0;m.away_goals=8
    db.commit();record_automatic_selections(db,[m])
    q=db.query(ForecastSnapshot).filter_by(phase='RETRO').one()
    assert not q.payload['markets']['corners']['available']
    assert not q.payload['markets']['yellows']['available']
    assert q.payload['markets']['goals']['expected_total']==pytest.approx(2.6)
    assert q.payload['reconstructed_markets']==['goals']
    assert db.query(ForecastSelection).count()==2


@pytest.mark.parametrize('choices,pick,probability',[
    ({'LOCAL':.40,'EMPATE':.38,'VISITANTE':.22},'1X',.78),
    ({'LOCAL':.20,'EMPATE':.38,'VISITANTE':.42},'X2',.80),
    ({'LOCAL':.40,'EMPATE':.41,'VISITANTE':.19},'1X',.81),
    ({'LOCAL':.425,'EMPATE':.375,'VISITANTE':.20},'1X',.80),
    ({'LOCAL':.42501,'EMPATE':.375,'VISITANTE':.19999},'LOCAL',.42501),
    ({'LOCAL':.44,'EMPATE':.13,'VISITANTE':.43},'LOCAL',.44),
    ({'LOCAL':.63,'EMPATE':.25,'VISITANTE':.12},'LOCAL',.63),
])
def test_double_chance_only_when_team_and_draw_are_close_top_two(choices,pick,probability):
    from app.ml.markets import result_suggestion
    suggestion=result_suggestion(choices)
    assert suggestion['pick']==pick
    assert suggestion['probability']==pytest.approx(probability)


@pytest.mark.parametrize('pick,goals,won',[
    ('1X',(2,0),True),('1X',(1,1),True),('1X',(0,2),False),
    ('X2',(2,0),False),('X2',(1,1),True),('X2',(0,2),True),
])
def test_automatic_double_chance_probability_and_settlement(sample,pick,goals,won):
    from app.services.forecasts import record_automatic_selections
    from app.services.error_analysis import error_analysis
    db,m,u=sample;p=db.query(Prediction).one()
    p.p_home,p.p_draw,p.p_away=(.4,.38,.22) if pick=='1X' else (.2,.38,.42)
    capture_forecasts(db,[m]);record_automatic_selections(db,[m])
    selection=db.query(ForecastSelection).filter_by(market='result').one()
    assert selection.pick==pick
    assert selection.probability==pytest.approx(.78 if pick=='1X' else .8)
    assert selection.policy_version=='doble-oportunidad-v1-5pp'
    assert selection.selection_reason
    m.status='FINISHED';m.home_goals,m.away_goals=goals
    settle_forecasts(db,[m])
    assert selection.status==('WON' if won else 'LOST')
    audit=error_analysis(db,u.id)
    assert audit['settlement_discrepancies']==[]
    assert error_analysis(db,u.id+1)['settled']==0
    assert audit['policy']['sample']==1
    assert audit['policy']['candidate_wins']==int(won)
    # Una liquidación corrupta se detecta; el diagnóstico no la modifica.
    selection.status='LOST' if won else 'WON';db.commit()
    assert len(error_analysis(db,u.id)['settlement_discrepancies'])==1
    assert selection.status==('LOST' if won else 'WON')


def test_learning_revision_updates_all_four_future_markets_with_history(sample):
    from copy import deepcopy
    from app.services.forecasts import record_automatic_selections, revise_automatic_selections
    from app.infrastructure.db.models import AutomaticSelectionRevision
    db,m,u=sample;capture_forecasts(db,[m]);record_automatic_selections(db,[m])
    old=db.query(ForecastSnapshot).one();original=deepcopy(old.payload)
    revision=db.query(ForecastRevision).one()
    parameters=deepcopy(revision.parameters)
    parameters['PRE'].update(temperature=1.3,goals_scale=1.2,corners_scale=1.1,yellows_scale=.9)
    new=ForecastRevision(created_at=utcnow(),adopted=True,parameters=parameters,report={'status':'adopted'})
    db.add(new);db.commit()
    capture_forecasts(db,[m])
    rows=db.query(ForecastSelection).all()
    assert len(rows)==4 and all(db.get(ForecastSnapshot,s.snapshot_id).revision_id==new.id for s in rows)
    assert db.query(AutomaticSelectionRevision).count()==4
    assert old.payload==original
    revise_automatic_selections(db);assert db.query(AutomaticSelectionRevision).count()==4
    # Se conservan registro e historial cuando el encuentro empieza.
    m.status='LIVE';m.kickoff=utcnow()-timedelta(seconds=1)
    db.add(ForecastRevision(created_at=utcnow(),adopted=True,parameters=parameters,report={'status':'adopted'}));db.commit()
    revise_automatic_selections(db)
    assert db.query(AutomaticSelectionRevision).count()==4
    assert all(db.get(ForecastSnapshot,s.snapshot_id).revision_id==new.id for s in rows)



def test_missing_team_history_never_falls_back_to_initial_counts(sample):
    from app.services.forecasts import count_prior, record_automatic_selections
    db,m,u=sample
    db.query(Match).filter(Match.id!=m.id).delete(synchronize_session=False)
    db.commit()
    assert count_prior(db,m,'corners')==(None,0)
    capture_forecasts(db,[m]);q=db.query(ForecastSnapshot).one()
    for key in ('corners','yellows'):
        assert q.payload['markets'][key]['available'] is False
        assert 'expected_total' not in q.payload['markets'][key]
        assert key not in q.payload['base']
    record_automatic_selections(db,[m])
    assert {r.market for r in db.query(ForecastSelection)}=={'result','goals'}


def test_real_zero_history_remains_zero(sample):
    from app.services.forecasts import count_prior
    db,m,_=sample
    for row in db.query(Match).filter(Match.id!=m.id):
        row.live_data={'final_details':True,'stats':{'home':{'corners':0},'away':{'corners':0}}}
    db.commit()
    assert count_prior(db,m,'corners')==(0,5)


def test_old_count_bets_are_withdrawn_and_cannot_be_resettled(sample):
    from copy import deepcopy
    from app.services.forecasts import enforce_observed_data, record_automatic_selections
    db,m,u=sample;capture_forecasts(db,[m]);record_automatic_selections(db,[m])
    q=db.query(ForecastSnapshot).one()
    payload=deepcopy(q.payload)
    for key in ('corners','yellows'):payload['base'][key].pop('data_policy')
    q.payload=payload;db.commit()
    assert enforce_observed_data(db)['selections_withdrawn']==2
    assert enforce_observed_data(db)['snapshots_corrected']==0
    report=selections_report(db,u.id,automatic_only=True)
    retired=[s for s in report['items'] if s['market'] in ('corners','yellows')]
    assert all(s['status']=='VOID' and s['probability'] is None and s['pick'] is None for s in retired)
    m.status='FINISHED';m.home_goals=2;m.away_goals=0
    m.live_data={'final_details':True,'stats':{'home':{'corners':5,'yellows':2},'away':{'corners':4,'yellows':2}}}
    settle_forecasts(db,[m])
    assert all(s.status=='VOID' for s in db.query(ForecastSelection).filter(ForecastSelection.market.in_(['corners','yellows'])))


def test_real_count_history_recovers_only_future_count_bets(sample):
    from copy import deepcopy
    from app.services.forecasts import enforce_observed_data,record_automatic_selections
    from app.infrastructure.db.models import AutomaticSelectionRevision
    db,m,u=sample;capture_forecasts(db,[m]);record_automatic_selections(db,[m])
    unchanged=lambda:{s.id:(s.snapshot_id,s.pick,s.probability,s.line_key,s.created_at) for s in db.query(ForecastSelection).filter(ForecastSelection.market.in_(['result','goals']))}
    before=unchanged()
    quote=db.query(ForecastSnapshot).one();payload=deepcopy(quote.payload)
    for key in ('corners','yellows'):payload['base'][key].pop('data_policy')
    quote.payload=payload;quote.fingerprint='legacy-count-prior';db.commit()
    enforce_observed_data(db)
    capture_forecasts(db,[m]);record_automatic_selections(db,[m],only_markets={'corners','yellows'})
    assert unchanged()==before
    assert db.query(ForecastSelection).count()==4
    assert all(s.status=='PENDING' for s in db.query(ForecastSelection))
    assert db.query(AutomaticSelectionRevision).count()==2
    report=selections_report(db,u.id,automatic_only=True)
    for row in report['items']:
        if row['market'] in ('corners','yellows'):
            assert row['history_coverage']=={'home':5,'away':5}
            assert len(row['history'])==5 and row['withdrawal_reason'] is None
    record_automatic_selections(db,[m],only_markets={'corners','yellows'})
    assert db.query(AutomaticSelectionRevision).count()==2


def test_count_bets_are_not_recovered_after_kickoff(sample):
    from copy import deepcopy
    from app.services.forecasts import enforce_observed_data,record_automatic_selections
    db,m,u=sample;capture_forecasts(db,[m]);record_automatic_selections(db,[m])
    q=db.query(ForecastSnapshot).one();payload=deepcopy(q.payload)
    for key in ('corners','yellows'):payload['base'][key].pop('data_policy')
    q.payload=payload;db.commit();enforce_observed_data(db)
    m.status='LIVE';m.kickoff=utcnow()-timedelta(minutes=10)
    record_automatic_selections(db,[m],only_markets={'corners','yellows'})
    assert all(s.status=='VOID' for s in db.query(ForecastSelection).filter(ForecastSelection.market.in_(['corners','yellows'])))

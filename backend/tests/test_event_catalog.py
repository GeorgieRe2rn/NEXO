from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.infrastructure.db.session import Base
from app.services import event_catalog as service


def event(identifier,when):
    return {'id':identifier,'uid':'s:600~l:776~e:'+identifier,'date':when,'status':{'type':{'state':'pre'}},'competitions':[{'competitors':[{'homeAway':'home','team':{'displayName':'Home'}},{'homeAway':'away','team':{'displayName':'Away'}}]}]}


def test_calendar_has_independent_coverage_and_correct_hermosillo_day(monkeypatch):
    engine=create_engine('sqlite:///:memory:');Base.metadata.create_all(engine)
    calls=[]
    def fake(url,params):
        calls.append((url,params))
        if url.endswith('/summary'):return {'header':{'league':{'name':'Premier League','slug':'eng.1'}}}
        if params['dates']=='20261015':return {'events':[event('1','2026-10-15T03:00:00Z'),event('2','2026-10-15T16:45:00Z')]}
        return {'events':[event('3','2026-10-16T02:00:00Z'),event('4','2026-10-16T12:00:00Z')]}
    monkeypatch.setattr(service,'get_json',fake)
    with Session(engine) as db:
        result=service.catalog(db,date(2026,10,15))
        assert {e['provider_id'] for e in result['items']}=={'2','3'}
        assert all(e['competition']['name']=='Premier League' for e in result['items'])
        assert all(e['match_id'] is None and not e['draftea_verified'] for e in result['items'])
        assert result['draftea']['verified'] is False
        count=len(calls);assert service.catalog(db,date(2026,10,15))==result
        assert len(calls)==count


def test_catalog_provider_failure_is_explicit(monkeypatch):
    engine=create_engine('sqlite:///:memory:');Base.metadata.create_all(engine)
    def fail(*args):raise RuntimeError('offline')
    monkeypatch.setattr(service,'get_json',fail)
    with Session(engine) as db:
        result=service.catalog(db,date(2026,10,15))
        assert result['total']==0 and len(result['errors'])==2


def test_draftea_screenshot_reference_matching_and_ranking():
    import pytest
    from app.services.draftea_reference import REFERENCES,implied_probability
    assert len(REFERENCES)==41
    assert implied_probability(-476)==pytest.approx(476/576)
    assert implied_probability(100)==.5
    assert implied_probability(234)==pytest.approx(100/334)
    for invalid in (0,99,float('inf'),float('nan')):
        with pytest.raises(ValueError):implied_probability(invalid)
    data={'date':'2026-10-15','draftea':{'verified':False},'items':[{'provider_id':identifier,'sport':'soccer'} for identifier in REFERENCES]}
    result=service.attach_references(data)
    assert result['screenshot_matches']==41
    assert [e['draftea_reference']['pick'] for e in result['favorites']]==['Rennes','Sunderland','Atalanta','Monaco','Midtjylland','Bayer Leverkusen']
    assert not result['draftea']['verified']
    assert all(not e['draftea_reference']['live_verified'] for e in result['items'])
    assert all('draftea_reference' not in e for e in data['items'])
    data['date']='2026-10-16'
    assert service.attach_references(data)['screenshot_matches']==0

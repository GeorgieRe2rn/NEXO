from datetime import timedelta
from test_market_pipeline import db,setup_match
from test_live_feed import event
from app.services import training_history
from app.services.forecasts import active_revision
from app.infrastructure.db.models import ForecastSnapshot,Match
from app.etl.calendar import utcnow


def processed(db):
 m=setup_match(db);m.status='FINISHED';m.home_goals=2;m.away_goals=1
 rev=active_revision(db)
 db.add(ForecastSnapshot(match_id=m.id,revision_id=rev.id,phase='PRE',fingerprint='processed',created_at=utcnow(),source_at=utcnow(),evaluated_at=utcnow(),payload={},outcomes={'result':0,'goals':3}))
 db.commit();return m


def test_audit_reuses_processed_matches_without_counting_selections(db):
 m=processed(db)
 report=training_history.audit_history(db)
 assert report['processed_matches']==1
 assert report['markets']['result']['usable_processed']==1
 assert report['markets']['yellows']['usable_processed']==0
 assert report['matches'][0]['markets']['yellows']=='missing_final_counter'


def test_recovery_is_cached_and_does_not_overwrite_processed_matches(db,monkeypatch):
 m=processed(db)
 prior=event(status='post',kickoff=utcnow()-timedelta(days=120))
 prior['id']='88000001';prior['league']={'slug':'eng.1'}
 calls=[]
 def source(url,params):
  calls.append(url);return {'events':[prior]}
 monkeypatch.setattr(training_history,'get_json',source)
 before=(m.home_goals,m.away_goals,m.verified_at)
 report=training_history.recover_history(db,schedule_budget=1,summary_budget=0)
 assert report['matches_added']==1
 assert report['errors']==0
 imported=db.query(Match).filter_by(provider_id='88000001').one()
 assert imported.is_h2h_only
 assert (m.home_goals,m.away_goals,m.verified_at)==before
 second=training_history.recover_history(db,schedule_budget=1,summary_budget=0)
 assert second['schedule_requests']==0
 assert second['matches_added']==0
 assert len(calls)==1

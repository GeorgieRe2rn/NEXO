"""Auditoría y recuperación acotada de antecedentes publicados para entrenamiento."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from collections import Counter
from app.etl.calendar import utcnow,aware,parse_iso,kickoff_iso
from app.infrastructure.db.models import Match,League,ForecastSnapshot,ApiCache,CountObservation
from app.infrastructure.cache import cache_get,cache_put
from app.services.live_feed import BASE,get_json,persist_event,map_status
from app.services.competition_registry import LEAGUES
from app.services.market_pipeline import Evidence,MARKETS


def audit_history(db):
    evidence=Evidence(db)
    processed={s.match_id for s in db.query(ForecastSnapshot).filter(ForecastSnapshot.evaluated_at.isnot(None)).all() if s.outcomes and 'void' not in s.outcomes}
    samples={k:{str(r['id']) for r in evidence.samples(k)} for k in MARKETS}
    details=[]
    for m,counts in evidence.valid:
        if m.id not in processed:continue
        eligibility={}
        for key in MARKETS:
            eligibility[key]='usable' if str(m.provider_id) in samples[key] else 'missing_final_counter' if key in ('corners','yellows') and key not in counts else 'missing_prior_history'
        details.append({'id':m.id,'match':f'{m.home_team.name} vs {m.away_team.name}','league':m.league.code,'kickoff':kickoff_iso(m.kickoff),'markets':eligibility})
    return {'processed_matches':len(processed),'audited_matches':len(details),'markets':{k:{'usable_processed':sum(d['markets'][k]=='usable' for d in details),'total_training':len(samples[k]),'exclusions':dict(Counter(d['markets'][k] for d in details if d['markets'][k]!='usable'))} for k in MARKETS},'matches':details,'notice':'Un partido puede aportar un ejemplo a cada mercado, pero sus selecciones no se cuentan como partidos independientes. Los resultados antiguos son reutilizables; los parámetros de v1 no se heredan.'}


def recover_history(db, schedule_budget=90, summary_budget=280):
    now=utcnow()
    processed={s.match_id for s in db.query(ForecastSnapshot).filter(ForecastSnapshot.evaluated_at.isnot(None)).all() if s.outcomes and 'void' not in s.outcomes}
    targets=db.query(Match).filter(Match.id.in_(processed)).order_by(Match.kickoff).all()
    jobs={}
    for m in targets:
        if m.league.code not in LEAGUES:continue
        for team in (m.home_team,m.away_team):
            if team.espn_id:
                year=int((m.live_data or {}).get('season') or m.league.season)
                jobs[(m.league.code,team.espn_id,year-1)]=(m.league.code,team.espn_id,year-1)
    jobs=list(jobs.values())[:schedule_budget]
    def fetch(job):
        code,tid,year=job
        key=f'training:schedule:{code}:{tid}:{year}'
        try:return job,key,get_json(f'{BASE}/{LEAGUES[code]}/teams/{tid}/schedule',{'season':year}),None
        except Exception as e:return job,key,None,type(e).__name__
    pending=[];responses=[]
    for job in jobs:
        key=f'training:schedule:{job[0]}:{job[1]}:{job[2]}'
        cached=cache_get(db,key)
        if cached:responses.append((job,key,cached,None))
        else:pending.append(job)
    with ThreadPoolExecutor(max_workers=4) as pool:responses.extend(pool.map(fetch,pending))
    added=errors=0
    existing={str(r[0]) for r in db.query(Match.provider_id).filter(Match.provider=='espn',Match.provider_id.isnot(None)).all()}
    for (code,_,year),key,data,error in responses:
        if error or not isinstance((data or {}).get('events'),list):errors+=1;continue
        league=db.query(League).filter_by(code=code).one()
        for event in data['events']:
            try:
                comp=(event.get('competitions') or [{}])[0]
                if (event.get('league') or {}).get('slug')!=LEAGUES[code] or str(event.get('id')) in existing:continue
                at=parse_iso(event['date'])
                if not now-timedelta(days=450)<at<now or map_status(comp.get('status') or {})!='FINISHED':continue
                if int((comp.get('status') or {}).get('period') or 2)>2:continue
                with db.begin_nested():
                    match=persist_event(db,league,event,now)
                    if match and match.home_goals is not None and match.away_goals is not None:
                        match.is_h2h_only=True
                        existing.add(str(event['id']));added+=1
            except (ValueError,KeyError,TypeError):errors+=1
        db.commit();cache_put(db,key,'espn','training-history',data,ttl_hours=168)
    # Recupera contadores en partidos existentes y antecedentes; no usa MatchStat.
    candidates=db.query(Match).filter(Match.provider=='espn',Match.provider_id.isnot(None),Match.status=='FINISHED').order_by(Match.kickoff.desc()).all() if summary_budget>0 else []
    chosen=[]
    for m in candidates:
        o=db.get(CountObservation,m.id)
        if o and all(getattr(o,f'{s}_{k}') is not None for s in ('home','away') for k in ('corners','yellows')):continue
        if cache_get(db,f'training:summary-retry:{m.provider_id}'):continue
        chosen.append((m.id,m.league.code,m.provider_id))
        if len(chosen)>=summary_budget:break
    def summary(job):
        mid,code,pid=job
        try:return mid,get_json(f'{BASE}/{LEAGUES[code]}/summary',{'event':pid}),None
        except Exception as e:return mid,None,type(e).__name__
    from app.services.count_history import store_summary
    stored=0
    with ThreadPoolExecutor(max_workers=4) as pool:
        for mid,data,error in pool.map(summary,chosen):
            m=db.get(Match,mid)
            try:
                if error:raise ValueError(error)
                with db.begin_nested():store_summary(db,m,data,now)
                stored+=1
            except (ValueError,KeyError,TypeError):
                cache_put(db,f'training:summary-retry:{m.provider_id}','espn','summary',{'unavailable':True},ttl_hours=24)
                errors+=1
    db.commit()
    report={'at':kickoff_iso(now),'schedule_requests':len(pending),'matches_added':added,'summary_requests':len(chosen),'summaries_stored':stored,'errors':errors}
    cache_put(db,'training:last-recovery','espn','training-history',report,ttl_hours=168)
    return report

"""Modelos por mercado/fase, datos observados y evaluación temporal sin mezclar épocas."""
import hashlib
import json
import math
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy.orm import joinedload
from app.etl.calendar import aware, utcnow, kickoff_iso, parse_iso
from app.infrastructure.db.models import Match, CountObservation, ForecastSnapshot, MarketLearner
from app.ml.markets import result_probabilities

SCHEMA = 'specialists-v2.0'
MARKETS = ('result', 'goals', 'corners', 'yellows')
MIN_SAMPLES = 200
FEATURES = ['league', 'home_gf', 'home_ga', 'away_gf', 'away_ga', 'home_points', 'away_points', 'home_rest', 'away_rest', 'home_home_share', 'away_home_share', 'home_count_for', 'home_count_against', 'away_count_for', 'away_count_against']
LIVE_FEATURES = FEATURES + ['minute', 'home_score', 'away_score', 'observed_count']


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


class Evidence:
    """Solo marcadores ESPN y contadores explícitos. No lee xG ni MatchStat imputados."""
    def __init__(self, db):
        self.matches = db.query(Match).options(joinedload(Match.home_team), joinedload(Match.away_team), joinedload(Match.league)).filter(Match.provider == 'espn', Match.provider_id.isnot(None), Match.status == 'FINISHED', Match.verified_at.isnot(None)).order_by(Match.kickoff, Match.id).all()
        observations = {r.match_id: r for r in db.query(CountObservation).all()}
        self.by_team = defaultdict(list)
        self.valid = []
        seen = set()
        for m in self.matches:
            # Un mismo evento puede aparecer como antecedente en distintas competiciones.
            if m.provider_id in seen or not all(number(v) and float(v).is_integer() for v in (m.home_goals, m.away_goals)):
                continue
            if int((m.live_data or {}).get('period') or 2) > 2:
                continue
            seen.add(m.provider_id)
            counters = {}
            for market in ('corners', 'yellows'):
                obs = observations.get(m.id)
                if obs:
                    values = [getattr(obs, f'{side}_{market}') for side in ('home', 'away')]
                elif (m.live_data or {}).get('final_details'):
                    stats = (m.live_data or {}).get('stats') or {}
                    values = [(stats.get(side) or {}).get(market) for side in ('home', 'away')]
                else:
                    values = [None, None]
                if all(number(v) and float(v).is_integer() for v in values):
                    counters[market] = values
            self.valid.append((m, counters))
            for side, team in enumerate((m.home_team, m.away_team)):
                if team.espn_id:
                    gf, ga = (m.home_goals, m.away_goals) if side == 0 else (m.away_goals, m.home_goals)
                    self.by_team[str(team.espn_id)].append({'at': aware(m.kickoff), 'event': m.provider_id, 'gf': gf, 'ga': ga, 'home': int(side == 0), 'counts': {k: (v[side], v[1-side]) for k,v in counters.items()}})

    def features(self, match, market):
        cutoff = aware(match.kickoff)
        histories = []
        count_histories = []
        for side,team in zip(('home','away'),(match.home_team, match.away_team)):
            previous = [r for r in self.by_team.get(str(team.espn_id), []) if r['event'] != match.provider_id and 10800 < (cutoff-r['at']).total_seconds() <= 365*86400]
            # Resúmenes ESPN de Champions incluyen antecedentes de otras ligas
            # que pueden no existir como partidos completos en la base local.
            explicit=((match.live_data or {}).get('global_history') or {}).get(side,[])
            by_id={r['event']:r for r in previous}
            for row in explicit:
                try:
                    at=parse_iso(row['kickoff']);event=str(row['id'])
                    if event==str(match.provider_id) or not 10800<(cutoff-at).total_seconds()<=365*86400:continue
                    if not str(row.get('source_url','')).startswith('https://www.espn.com/soccer/match/'):continue
                    if not all(number(row.get(k)) and float(row[k]).is_integer() for k in ('goals','goals_against')):continue
                    by_id.setdefault(event,{'at':at,'event':event,'gf':row['goals'],'ga':row['goals_against'],'home':int(row['is_home']) if isinstance(row.get('is_home'),bool) else None,'counts':{}})
                except (ValueError,KeyError,TypeError):continue
            previous=sorted(by_id.values(),key=lambda r:r['at'])
            rows = previous[-5:]
            if len(rows) < 5:
                return None
            histories.append(rows)
            counts = [r['counts'][market] for r in previous if market in r['counts']][-5:] if market in ('corners', 'yellows') else []
            if market in ('corners', 'yellows') and len(counts) < 5:
                return None
            count_histories.append(counts)
        mean = lambda rows,k: sum(r[k] for r in rows)/len(rows) if all(r[k] is not None for r in rows) else None
        h,a = histories
        x = [match.league.code, mean(h,'gf'), mean(h,'ga'), mean(a,'gf'), mean(a,'ga'), sum(3 if r['gf']>r['ga'] else 1 if r['gf']==r['ga'] else 0 for r in h)/5, sum(3 if r['gf']>r['ga'] else 1 if r['gf']==r['ga'] else 0 for r in a)/5, min(60,(cutoff-h[-1]['at']).total_seconds()/86400), min(60,(cutoff-a[-1]['at']).total_seconds()/86400), mean(h,'home'),mean(a,'home')]
        for counts in count_histories:
            x.extend([sum(r[0] for r in counts)/5, sum(r[1] for r in counts)/5] if counts else [None,None])
        lh=max(.05,(x[1]+x[4])/2)
        la=max(.05,(x[3]+x[2])/2)
        if market == 'result': baseline=result_probabilities(0,0,lh,la)
        elif market == 'goals': baseline=lh+la
        else: baseline=max(.05,sum(sum(r) for rows in count_histories for r in rows)/10)
        return {'x': x, 'baseline': baseline, 'lambdas': [lh,la], 'history_end': kickoff_iso(max(h[-1]['at'],a[-1]['at']))}

    def samples(self, market):
        rows=[]
        for m,counts in self.valid:
            if market in ('corners','yellows') and market not in counts: continue
            evidence=self.features(m,market)
            if not evidence: continue
            target=(0 if m.home_goals>m.away_goals else 1 if m.home_goals==m.away_goals else 2) if market=='result' else m.home_goals+m.away_goals if market=='goals' else sum(counts[market])
            rows.append({'id':m.provider_id,'at':aware(m.kickoff),'x':evidence['x'],'baseline':evidence['baseline'],'y':target})
        return rows


def temporal_split(rows):
    ordered=sorted(rows,key=lambda r:(r['at'],str(r['id'])))
    if len(ordered)<MIN_SAMPLES: return None
    first=ordered[int(len(ordered)*.6)]['at']
    second=ordered[int(len(ordered)*.8)]['at']
    # Evita que un resultado de un partido todavía en curso llegue al siguiente bloque.
    train=[r for r in ordered if (first-r['at']).total_seconds()>10800]
    validation=[r for r in ordered if first<=r['at'] and (second-r['at']).total_seconds()>10800]
    test=[r for r in ordered if r['at']>=second]
    if min(len(train),len(validation),len(test))<30 or len(train)<100: return None
    return train,validation,test


def blend(base, pred, weight):
    if isinstance(base,list): return [(1-weight)*a+weight*b for a,b in zip(base,pred)]
    return max(.01,(1-weight)*base+weight*float(pred))


def score(rows, predictions, market):
    if market=='result':
        loss=sum(-math.log(max(1e-12,p[int(r['y'])])) for r,p in zip(rows,predictions))/len(rows)
        return {'log_loss':loss, 'accuracy':sum(max(range(3),key=lambda i:p[i])==r['y'] for r,p in zip(rows,predictions))/len(rows), 'brier':sum(sum((v-int(i==r['y']))**2 for i,v in enumerate(p)) for r,p in zip(rows,predictions))/len(rows)}
    # NLL de la distribución Poisson completa, no solo aciertos en una línea elegida.
    return {'log_loss':sum(max(.01,float(p))-r['y']*math.log(max(.01,float(p)))+math.lgamma(r['y']+1) for r,p in zip(rows,predictions))/len(rows), 'mae':sum(abs(r['y']-p) for r,p in zip(rows,predictions))/len(rows)}


def current_model(db,market,phase):
    return db.query(MarketLearner).filter_by(schema_version=SCHEMA,market=market,phase=phase,adopted=True).order_by(MarketLearner.id.desc()).first()


@lru_cache(maxsize=32)
def load_model(model_json, classification):
    from catboost import CatBoostClassifier, CatBoostRegressor, Pool
    model=CatBoostClassifier() if classification else CatBoostRegressor()
    with TemporaryDirectory() as folder:
        path=Path(folder)/'model.json';path.write_text(model_json,encoding='utf-8');model.load_model(str(path),format='json')
    return model


def predict_model(model,xs,market):
    xs=[[v if i==0 or v is not None else float('nan') for i,v in enumerate(x)] for x in xs]
    if market=='result': return model.predict_proba(xs,thread_count=2).tolist()
    return model.predict(xs,prediction_type='Exponent',thread_count=2).tolist()


def specialist(db,market,phase,x,baseline):
    row=current_model(db,market,phase)
    if not row: return baseline, {'family':'Poisson observado', 'state':'baseline', 'schema':SCHEMA}
    model=load_model(row.model_json,market=='result')
    pred=predict_model(model,[x],market)[0]
    return blend(baseline,pred,row.report['weight']), {'family':'CatBoost + Poisson','state':'adopted','schema':SCHEMA,'revision':row.id,'weight':row.report['weight']}


def live_samples(db,market):
    rows=[];seen=set()
    snapshots=db.query(ForecastSnapshot).join(Match).filter(ForecastSnapshot.phase=='LIVE',ForecastSnapshot.evaluated_at.isnot(None)).order_by(Match.kickoff,ForecastSnapshot.id).all()
    for s in snapshots:
        e=s.payload.get('specialists',{}).get(market,{})
        if s.payload.get('architecture')!=SCHEMA or not e.get('x') or not s.outcomes or 'void' in s.outcomes or s.match_id in seen: continue
        y=s.outcomes.get(market)
        if y is None: continue
        base=s.payload['base'].get(market)
        if not base: continue
        seen.add(s.match_id)
        rows.append({'id':s.match_id,'at':aware(db.get(Match,s.match_id).kickoff),'x':e['x'],'baseline':e['baseline'],'y':y if market=='result' else y-base['current']})
    return [r for r in rows if r['y']>=0]


def train_one(db,market,phase,rows):
    from catboost import CatBoostClassifier, CatBoostRegressor, Pool
    signature=fingerprint([(r['id'],r['y'],r['x'],r['baseline']) for r in rows])
    previous=db.query(MarketLearner).filter_by(schema_version=SCHEMA,market=market,phase=phase,dataset_digest=signature).first()
    if previous:return previous.report
    split=temporal_split(rows)
    report={'samples':len(rows),'minimum':MIN_SAMPLES,'status':'awaiting_evidence','schema':SCHEMA,'market':market,'phase':phase}
    blob=None;adopted=False
    if split:
        train,validation,test=split
        if market=='result' and set(r['y'] for r in train)!={0,1,2}:
            report['reason']='Faltan clases en entrenamiento'
        else:
            params=dict(iterations=160,depth=4,learning_rate=.04,l2_leaf_reg=8,random_seed=42,thread_count=2,verbose=False,allow_writing_files=False,has_time=True)
            model=CatBoostClassifier(loss_function='MultiClass',**params) if market=='result' else CatBoostRegressor(loss_function='Poisson',**params)
            model.fit(Pool([[v if i==0 or v is not None else float('nan') for i,v in enumerate(r['x'])] for r in train],[r['y'] for r in train],cat_features=[0],feature_names=LIVE_FEATURES if phase=='LIVE' else FEATURES))
            vp=predict_model(model,[r['x'] for r in validation],market)
            weight=min([0,.25,.5,.75,1],key=lambda w:score(validation,[blend(r['baseline'],p,w) for r,p in zip(validation,vp)],market)['log_loss'])
            tp=predict_model(model,[r['x'] for r in test],market)
            candidate=score(test,[blend(r['baseline'],p,weight) for r,p in zip(test,tp)],market)
            baseline=score(test,[r['baseline'] for r in test],market)
            champion=current_model(db,market,phase)
            # No reutiliza una prueba anterior como prueba "nueva" de un sucesor.
            last_test=next((r for r in db.query(MarketLearner).filter_by(schema_version=SCHEMA,market=market,phase=phase).order_by(MarketLearner.id.desc()).all() if r.report.get('status') in ('adopted','not_improved') and r.report.get('test_end')),None)
            fresh=not last_test or min(r['at'] for r in test)>parse_iso(last_test.report['test_end'])
            champion_score=baseline
            if champion:
                cp=predict_model(load_model(champion.model_json,market=='result'),[r['x'] for r in test],market)
                champion_score=score(test,[blend(r['baseline'],p,champion.report['weight']) for r,p in zip(test,cp)],market)
            adopted=fresh and weight>0 and candidate['log_loss']<min(baseline['log_loss'],champion_score['log_loss'])-.002
            report.update(status='adopted' if adopted else 'not_improved' if fresh else 'awaiting_fresh_test',weight=weight,train_matches=len(train),validation_matches=len(validation),test_matches=len(test),train_end=kickoff_iso(max(r['at'] for r in train)),validation_start=kickoff_iso(min(r['at'] for r in validation)),test_start=kickoff_iso(min(r['at'] for r in test)),test_end=kickoff_iso(max(r['at'] for r in test)),candidate=candidate,baseline=baseline,champion=champion_score,feature_importance=dict(zip(LIVE_FEATURES if phase=='LIVE' else FEATURES,model.get_feature_importance().tolist())))
            with TemporaryDirectory() as folder:
                path=Path(folder)/'model.json';model.save_model(str(path),format='json');blob=path.read_text(encoding='utf-8')
    db.add(MarketLearner(schema_version=SCHEMA,market=market,phase=phase,created_at=utcnow(),dataset_digest=signature,adopted=adopted,model_json=blob,report=report));db.commit()
    return report


def train_specialists(db):
    evidence=Evidence(db)
    reports=[]
    for market in MARKETS:
        reports.append(train_one(db,market,'PRE',evidence.samples(market)))
        reports.append(train_one(db,market,'LIVE',live_samples(db,market)))
    return reports


def model_status(db):
    result=[]
    for phase in ('PRE','LIVE'):
        for market in MARKETS:
            latest=db.query(MarketLearner).filter_by(schema_version=SCHEMA,market=market,phase=phase).order_by(MarketLearner.id.desc()).first()
            champion=current_model(db,market,phase)
            result.append({'market':market,'phase':phase,'active':'CatBoost + Poisson' if champion else 'Poisson observado','active_revision':champion.id if champion else None,'shadow':shadow_status(db,market,phase),'report':latest.report if latest else {'status':'pending','samples':0,'minimum':MIN_SAMPLES}})
    return result


def deployment(db):
    return fingerprint([(p,k,(r.id if (r:=current_model(db,k,p)) else None)) for p in ('PRE','LIVE') for k in MARKETS])

def build_specialized_payload(db, match, phase, revision):
    from datetime import timedelta
    from app.services.forecasts import observed_total, OBSERVED_POLICY, MISSING_HISTORY
    from app.services.count_history import history_rows
    from app.ml.markets import minute_from_clock, count_base, project_market, DEFAULT_PARAMETERS
    now=utcnow();live=match.live_data or {}
    if not match.verified_at or now-aware(match.verified_at)> (timedelta(minutes=3) if phase=='LIVE' else timedelta(hours=3,minutes=15)):return None
    minute=None
    if phase=='LIVE':
        if match.status!='LIVE' or live.get('score_pending_confirmation') or int(live.get('period') or 2)>2:return None
        minute=minute_from_clock(live.get('clock'))
        if minute is None or observed_total(match,'goals') is None:return None
    elif match.status!='SCHEDULED' or aware(match.kickoff)<=now:return None
    evidence=db.info.get('pipeline_evidence') or Evidence(db)
    base={};models={};markets={}
    goal_evidence=evidence.features(match,'goals')
    # Marcadores anteriores en resúmenes ESPN; excluye datos del propio encuentro.
    if goal_evidence:
        lh,la=goal_evidence['lambdas']
        if phase=='LIVE':
            fraction=max(0,95-minute)/90
            lh=max(.0,lh*fraction);la=max(.0,la*fraction)
        for market in ('result','goals'):
            e=evidence.features(match,market)
            baseline=result_probabilities(match.home_goals,match.away_goals,lh,la) if phase=='LIVE' and market=='result' else lh+la if market=='goals' else e['baseline']
            current=observed_total(match,'goals') if phase=='LIVE' else 0
            x=e['x']+([minute,match.home_goals,match.away_goals,current] if phase=='LIVE' else [])
            value,model=specialist(db,market,phase,x,baseline)
            if phase=='PRE':
                from app.services.odds_feed import apply_odds
                without_odds=value[:] if market=='result' else value
                value,odds=apply_odds(db,match,phase,value,market)
                model={**model,'odds':odds,'without_odds':without_odds}
                if odds and odds.get('weight',0)>0:model['family']+=' + mercado'
            models[market]={**model,'x':x,'baseline':baseline,'history_end':e['history_end']}
            if market=='result':base[market]={'market':market,'probabilities':value}
            else:
                base[market]=count_base(market,value,current,None,10)
                base[market]['basis']='Modelo de goles independiente; cinco marcadores observados por equipo, sin estadísticas imputadas.'+(' Consenso de cuotas incorporado con peso explícito; tasa implícita estimada.' if model.get('odds') and model['odds'].get('weight',0)>0 else '')
    for market in ('corners','yellows'):
        e=evidence.features(match,market)
        records,coverage=history_rows(db,match,market)
        details=live.get('details_at')
        observed=observed_total(match,market) if phase=='LIVE' else 0
        if not e or min(coverage.values())<5:
            markets[market]={'market':market,'available':False,'reason':MISSING_HISTORY,'history_coverage':coverage};continue
        if phase=='LIVE' and (observed is None or not details or now-parse_iso(details)>timedelta(minutes=3)):
            markets[market]={'market':market,'available':False,'reason':'Sin contadores recientes confirmados.'};continue
        # La misma media y el mismo alcance se usan al entrenar y al pronosticar.
        statistical=count_base(market,e['baseline'],observed,minute,len(records))
        baseline=statistical['remaining_mean']
        x=e['x']+([minute,match.home_goals,match.away_goals,observed] if phase=='LIVE' else [])
        value,model=specialist(db,market,phase,x,baseline)
        models[market]={**model,'x':x,'baseline':baseline,'history_end':e['history_end']}
        base[market]=count_base(market,value,observed,None,len(records))
        base[market].update(data_policy=OBSERVED_POLICY,basis=f"{model['family']}; historial publicado de ambos equipos, modelo independiente de {market}.",history=records,history_coverage=coverage)
    for market in MARKETS:
        if market not in base and market not in markets:markets[market]={'market':market,'available':False,'reason':MISSING_HISTORY}
    parameters=revision.parameters.get(phase,DEFAULT_PARAMETERS)
    odds_versions={k:{"id":v["odds"].get("id"),"weight":v["odds"]["weight"],"revision":v["odds"].get("combiner_revision")} for k,v in models.items() if v.get("odds",{} ) and v["odds"].get("weight",0)>0}
    odds_revision=fingerprint(odds_versions)[:12] if odds_versions else None
    # La calibración deportiva anterior no se aplica a un nuevo ensemble de cuotas.
    markets.update({k:project_market(v,DEFAULT_PARAMETERS if k in odds_versions else parameters) for k,v in base.items()})
    if not base:return None
    return {'odds_revision':odds_revision,'architecture':SCHEMA,'specialists':models,'phase':phase,'minute':minute,'clock':live.get('clock') if phase=='LIVE' else None,'score':[match.home_goals,match.away_goals] if phase=='LIVE' else [0,0],'markets':markets,'base':base,'model_version':f'{SCHEMA}-r{revision.id}'+(f'-o{odds_revision}' if odds_revision else ''),'prediction_family':SCHEMA,'history_notice':'Modelos independientes por mercado y fase. CatBoost solo se adopta tras validación y prueba temporal posteriores. Historial observado; sin rellenar estadísticas ausentes. Ganador y goles pueden diferir por ser objetivos independientes.','rules':'Resultado a 90 minutos más añadido. Sin prórroga ni penales. Sin dinero.','assumptions':'Bases Poisson de datos observados; los parámetros de distribución son estimaciones. Horizonte en vivo de 95 minutos.','observed_details_at':live.get('details_at') if phase=='LIVE' else None}


def sync_prediction_view(db,match,payload):
    """Proyección de compatibilidad para paneles; no es otro motor de predicción."""
    from app.infrastructure.db.models import Prediction
    result=payload['markets'].get('result',{})
    goals=payload['markets'].get('goals',{})
    if not result.get('available') or not goals.get('available'):return
    p=db.query(Prediction).filter_by(match_id=match.id).first()
    if p is None:p=Prediction(match_id=match.id);db.add(p)
    choices=result['choices']
    p.p_home,p.p_draw,p.p_away=choices['LOCAL'],choices['EMPATE'],choices['VISITANTE']
    from app.ml.markets import over_probability
    p.p_over_25=over_probability(0,goals['expected_total'],2.5);p.p_under_25=1-p.p_over_25
    x=payload['specialists']['goals']['x']
    home=max(.05,(x[1]+x[4])/2);away=max(.05,(x[3]+x[2])/2)
    p.lambda_home=goals['expected_total']*home/(home+away);p.lambda_away=goals['expected_total']*away/(home+away)
    p.confidence=.35;p.confidence_label='EXPERIMENTAL';p.pick=max(choices,key=choices.get)
    p.model_version=payload['model_version'];p.computed_at=utcnow()
    p.explanation={'notice':payload['history_notice'],'architecture':SCHEMA,'specialists':{k:{key:value for key,value in v.items() if key not in ('x','baseline')} for k,v in payload['specialists'].items()}}
    db.flush()


def latest_candidate(db,market,phase):
    return db.query(MarketLearner).filter(MarketLearner.schema_version==SCHEMA,MarketLearner.market==market,MarketLearner.phase==phase,MarketLearner.model_json.isnot(None)).order_by(MarketLearner.id.desc()).first()


def capture_shadow(db,matches):
    from app.infrastructure.db.models import ShadowForecast
    from datetime import timedelta
    candidates={(k,p):latest_candidate(db,k,p) for k in MARKETS for p in ('PRE','LIVE')}
    created=0
    for match in matches:
        phase='LIVE' if match.status=='LIVE' else 'PRE'
        if match.status not in ('SCHEDULED','LIVE') or phase=='PRE' and aware(match.kickoff)<=utcnow():continue
        if not match.verified_at or utcnow()-aware(match.verified_at)>timedelta(minutes=3 if phase=='LIVE' else 195):continue
        snap=db.query(ForecastSnapshot).filter_by(match_id=match.id,phase=phase).order_by(ForecastSnapshot.id.desc()).first()
        if not snap or snap.payload.get('architecture')!=SCHEMA:continue
        if phase=='LIVE' and (snap.payload.get('clock')!=(match.live_data or {}).get('clock') or snap.payload.get('score')!=[match.home_goals,match.away_goals]):continue
        for market in MARKETS:
            candidate=candidates[(market,phase)]
            e=snap.payload.get('specialists',{}).get(market)
            if not candidate or not e or not e.get('x'):continue
            if db.query(ShadowForecast.id).filter_by(match_id=match.id,model_id=candidate.id,phase=phase).first():continue
            value=predict_model(load_model(candidate.model_json,market=='result'),[e['x']],market)[0]
            db.add(ShadowForecast(match_id=match.id,model_id=candidate.id,snapshot_id=snap.id,phase=phase,market=market,created_at=utcnow(),payload={'prediction':value,'baseline':e['baseline'],'current':snap.payload['base'][market].get('current',0),'model':candidate.id,'notice':'CatBoost experimental. No modifica apuestas ni el modelo activo.'}))
            created+=1
    db.commit();return created


def settle_shadow(db):
    from app.infrastructure.db.models import ShadowForecast
    from app.services.forecasts import actual_outcomes
    for row in db.query(ShadowForecast).filter(ShadowForecast.evaluated_at.is_(None)).all():
        m=db.get(Match,row.match_id);outcome=actual_outcomes(m)
        if not outcome:continue
        if 'void' in outcome:row.outcomes={'void':outcome['void']}
        elif outcome.get(row.market) is None:continue
        else:
            target=outcome[row.market] if row.market=='result' else outcome[row.market]-row.payload['current']
            if target<0:row.outcomes={'void':'Contador final menor que el observado al capturar.'}
            else:row.outcomes={'target':target}
        row.evaluated_at=utcnow()
    db.commit()


def shadow_status(db,market,phase):
    from app.infrastructure.db.models import ShadowForecast
    candidate=latest_candidate(db,market,phase)
    if not candidate:return {'state':'awaiting_training','predictions':0,'evaluated':0}
    rows=db.query(ShadowForecast).filter_by(model_id=candidate.id).all()
    evaluated=[r for r in rows if r.outcomes and 'target' in r.outcomes]
    report={'state':'running','revision':candidate.id,'predictions':len(rows),'evaluated':len(evaluated),'training_status':candidate.report.get('status'),'notice':'Pronósticos experimentales separados de las apuestas automáticas.'}
    if evaluated:
        targets=[{'y':r.outcomes['target']} for r in evaluated]
        report['metrics']=score(targets,[r.payload['prediction'] for r in evaluated],market)
        report['baseline']=score(targets,[r.payload['baseline'] for r in evaluated],market)
    return report

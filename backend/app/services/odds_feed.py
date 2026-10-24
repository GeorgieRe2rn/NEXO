"""Cuotas observadas: captura previa, consenso sin margen y combinación validada."""
import math
import threading
import unicodedata
from datetime import timedelta
import httpx
from app.core.config import get_settings
from app.etl.calendar import utcnow, aware, parse_iso, kickoff_iso
from app.infrastructure.db.models import ApiCache, Match, OddsObservation, ForecastSnapshot

SPORTS = {"MX":"soccer_mexico_ligamx", "PL":"soccer_epl", "PD":"soccer_spain_la_liga", "SA":"soccer_italy_serie_a", "MLS":"soccer_usa_mls", "CL":"soccer_uefa_champs_league", "BL1":"soccer_germany_bundesliga"}
_lock = threading.Lock()


def name(value):
    return "".join(c for c in unicodedata.normalize("NFKD", value.casefold()) if c.isalnum() and not unicodedata.combining(c))


def devig(prices):
    if not prices or any(isinstance(p, bool) or not isinstance(p, (int,float)) or not math.isfinite(p) or p <= 1 for p in prices):
        return None
    inverse = [1/p for p in prices]
    return [p/sum(inverse) for p in inverse]


def put_cache(db, key, payload, hours=24):
    row = db.get(ApiCache, key)
    if row is None:
        row = ApiCache(cache_key=key, provider="odds-api", endpoint="/v4/sports/odds", hit_count=0)
        db.add(row)
    row.payload=payload; row.fetched_at=utcnow(); row.expires_at=utcnow()+timedelta(hours=hours)
    db.commit()


def match_event(event, matches):
    # Coincidencia exacta normalizada y hora compatible. No fuzzy matching silencioso.
    try:
        start=parse_iso(event["commence_time"])
        hits=[m for m in matches if abs((aware(m.kickoff)-start).total_seconds()) <= 600 and name(m.home_team.name)==name(event["home_team"]) and name(m.away_team.name)==name(event["away_team"])]
        return hits[0] if len(hits)==1 else None
    except (KeyError,TypeError,ValueError):
        return None


def normalize_event(event, captured):
    books=[]
    for book in event.get("bookmakers", []):
        markets={}
        for market in book.get("markets", []):
            try:
                updated=parse_iso(market.get("last_update") or book["last_update"])
                if not 0 <= (captured-updated).total_seconds() <= 86400:
                    continue
                outcomes=market["outcomes"]
                if market["key"]=="h2h":
                    by_name={o["name"]:o["price"] for o in outcomes}
                    prices=[by_name[event["home_team"]],by_name["Draw"],by_name[event["away_team"]]]
                    probabilities=devig(prices)
                    if probabilities: markets["result"]={"prices":prices,"probabilities":probabilities,"updated_at":kickoff_iso(updated)}
                elif market["key"]=="totals":
                    over=next(o for o in outcomes if o["name"]=="Over")
                    under=next(o for o in outcomes if o["name"]=="Under" and o["point"]==over["point"])
                    line=float(over["point"])
                    probs=devig([over["price"],under["price"]])
                    if probs and 0<line<15 and line%1==.5:
                        markets["goals"]={"prices":[over["price"],under["price"]],"line":line,"probabilities":probs,"updated_at":kickoff_iso(updated)}
            except (KeyError,ValueError,TypeError,StopIteration):
                continue
        if markets: books.append({"key":book.get("key"),"name":book.get("title"),"markets":markets})
    result=[b["markets"]["result"]["probabilities"] for b in books if "result" in b["markets"]]
    means=implied_goal_means(books)
    return {"goals_mean":sum(means)/len(means) if means else None,"provider":"The Odds API", "event_id":event["id"], "captured_at":kickoff_iso(captured), "bookmakers":books, "result": [sum(p[i] for p in result)/len(result) for i in range(3)] if result else None, "notice":"Cuotas de las casas indicadas; no son cuotas de Draftea. Córners y amarillas sin cobertura confirmada."}


def implied_goal_means(books):
    # La tasa implícita es una estimación Poisson de las cuotas, no un conteo observado.
    from app.ml.markets import over_probability
    means=[]
    for book in books:
        total=book["markets"].get("goals")
        if not total: continue
        low,high=.001,30.
        for _ in range(60):
            mid=(low+high)/2
            if over_probability(0,mid,total["line"])<total["probabilities"][0]:low=mid
            else:high=mid
        means.append((low+high)/2)
    return means


def sync_odds(db):
    if not get_settings().odds_api_key:
        return {"status":"missing_key","message":"Configura ODDS_API_KEY en .env y reinicia el backend."}
    if not _lock.acquire(blocking=False): return {"status":"busy"}
    try:
        now=utcnow(); imported=0; unmatched=0; errors=[]
        # 7 ligas x 2 mercados x 1 región, una vez al día: hasta 420 créditos / 30 días.
        with httpx.Client(timeout=20) as client:
            for code,sport in SPORTS.items():
                key=f"odds:sync:{code}"; cached=db.get(ApiCache,key)
                if cached and aware(cached.expires_at)>now: continue
                matches=db.query(Match).filter(Match.status=="SCHEDULED",Match.kickoff>now,Match.kickoff<now+timedelta(days=8)).all()
                matches=[m for m in matches if m.league.code==code]
                if not matches: continue
                try:
                    response=client.get(f"https://api.the-odds-api.com/v4/sports/{sport}/odds",params={"apiKey":get_settings().odds_api_key,"regions":"eu","markets":"h2h,totals","oddsFormat":"decimal"})
                    if response.status_code!=200:
                        errors.append({"league":code,"http_status":response.status_code})
                        put_cache(db,key,{"status":"error","http_status":response.status_code},hours=24)
                        if response.status_code in (401,403,429): break
                        continue
                    events=response.json()
                    if not isinstance(events,list): raise ValueError("unexpected response")
                    for event in events:
                        match=match_event(event,matches)
                        captured=utcnow()
                        if match is None: unmatched+=1;continue
                        if captured>=aware(match.kickoff): continue
                        payload=normalize_event(event,captured)
                        if payload["bookmakers"]:
                            db.add(OddsObservation(match_id=match.id,captured_at=captured,payload=payload));imported+=1
                    db.commit()
                    put_cache(db,key,{"status":"ok","remaining":response.headers.get("x-requests-remaining")})
                except (httpx.HTTPError,ValueError,TypeError,KeyError):
                    db.rollback(); errors.append({"league":code,"status":"unavailable"})
                    put_cache(db,key,{"status":"unavailable"},hours=24)
        report={"status":"ok" if not errors else "partial","imported":imported,"unmatched":unmatched,"errors":errors,"at":kickoff_iso(now)}
        put_cache(db,"odds:last-sync",report)
        fit_combiner(db)
        return report
    finally: _lock.release()


def latest_odds(db, match):
    now=utcnow()
    row=db.query(OddsObservation).filter(OddsObservation.match_id==match.id,OddsObservation.captured_at<match.kickoff,OddsObservation.captured_at<=now).order_by(OddsObservation.captured_at.desc()).first()
    if row is None: return None
    from app.services.stable_market import select_references
    earlier=db.query(OddsObservation).filter(OddsObservation.match_id==match.id,OddsObservation.captured_at<row.captured_at).order_by(OddsObservation.captured_at.desc()).limit(12).all()
    signals=select_references(row.payload,earlier,now,aware(row.captured_at))
    means=implied_goal_means(row.payload["bookmakers"])
    return {**row.payload,"market_signals":signals,"goals_mean":sum(means)/len(means) if means else None,"id":row.id,"stale": (now-aware(row.captured_at)).total_seconds()>86400}


def apply_odds(db, match, phase, value, market="result"):
    if phase!="PRE" or match.status!="SCHEDULED" or aware(match.kickoff)<=utcnow(): return value,None
    observed=latest_odds(db,match)
    if not observed or observed["stale"] or observed.get("result" if market=="result" else "goals_mean") is None: return value,observed
    from app.services.stable_market import POLICY
    signal=observed["market_signals"][market]
    if not signal["available"] or not signal["initial_weight"]:
        return value,{**observed,"weight":0,"state":signal["state"],"reference_policy":POLICY,"selection":signal}
    report=db.get(ApiCache,"odds:combiner" if market=="result" else "odds:combiner:goals")
    from app.services.market_pipeline import deployment, blend
    valid=report and report.payload.get("deployment")==deployment(db) and report.payload.get("reference_policy")==POLICY and report.payload.get("test_end")
    weight=report.payload["weight"] if valid else signal["initial_weight"]
    reference=signal["value"]
    return blend(value,reference,weight), {**observed,"result":reference if market=="result" else observed["result"],"goals_mean":reference if market=="goals" else observed["goals_mean"],"weight":weight,"state":"validated" if valid else "experimental_rule","selection":signal,"reference_policy":POLICY,"model_deployment":deployment(db),"combiner_revision":report.payload.get("test_end") if valid else POLICY}



def fit_combiner(db):
    return {market:fit_market_combiner(db,market) for market in ("result","goals")}


def fit_market_combiner(db,market):
    from app.services.market_pipeline import temporal_split, score, blend, deployment
    rows=[]; seen=set()
    from app.services.stable_market import POLICY
    current_deployment=deployment(db)
    cache_key="odds:combiner" if market=="result" else "odds:combiner:goals"
    reference_key="result" if market=="result" else "goals_mean"
    for snap in db.query(ForecastSnapshot).filter(ForecastSnapshot.phase=="PRE",ForecastSnapshot.evaluated_at.isnot(None)).order_by(ForecastSnapshot.created_at).all():
        e=snap.payload.get("specialists",{}).get(market,{}); odds=e.get("odds")
        if snap.match_id in seen or not odds or odds.get("reference_policy")!=POLICY or odds.get("model_deployment")!=current_deployment or odds.get(reference_key) is None or odds.get("stale") or not snap.outcomes or "void" in snap.outcomes or snap.outcomes.get(market) is None:continue
        match=db.get(Match,snap.match_id)
        if not match or aware(snap.created_at)>=aware(match.kickoff) or parse_iso(odds["captured_at"])>=aware(match.kickoff) or parse_iso(odds["captured_at"])>aware(snap.created_at):continue
        base=e.get("without_odds")
        if not base:continue
        seen.add(snap.match_id)
        rows.append({"id":snap.match_id,"at":aware(match.kickoff),"y":snap.outcomes[market],"x":odds[reference_key],"baseline":base})
    report={"samples":len(rows),"minimum":200,"weight":0,"status":"collecting","deployment":deployment(db),"reference_policy":POLICY}
    split=temporal_split(rows)
    previous=db.get(ApiCache,cache_key)
    if split:
        train,validation,test=split
        # El peso solo se elige en validación. El bloque final solo acepta/rechaza.
        if previous and previous.payload.get("reference_policy")==POLICY and previous.payload.get("deployment")==current_deployment and previous.payload.get("test_end") and min(r["at"] for r in test)<=parse_iso(previous.payload["test_end"]):
            return previous.payload
        weight=min([0,.25,.5,.75,1],key=lambda w:score(validation,[blend(r["baseline"],r["x"],w) for r in validation],market)["log_loss"])
        baseline=score(test,[r["baseline"] for r in test],market)
        candidate=score(test,[blend(r["baseline"],r["x"],weight) for r in test],market)
        prior_weight=previous.payload.get("weight",0) if previous and previous.payload.get("reference_policy")==POLICY and previous.payload.get("deployment")==current_deployment else 0
        champion=score(test,[blend(r["baseline"],r["x"],prior_weight) for r in test],market)
        accepted=weight>0 and candidate["log_loss"]<min(baseline["log_loss"],champion["log_loss"])-.002
        report.update(weight=weight if accepted else prior_weight,status="validated" if accepted or prior_weight else "not_improved",candidate=candidate,baseline=baseline,test_end=kickoff_iso(max(r["at"] for r in test)),validation_matches=len(validation),test_matches=len(test))
    put_cache(db,cache_key,report,hours=24*365)
    return report


def odds_status(db):
    goals=db.get(ApiCache,"odds:combiner:goals")
    report=db.get(ApiCache,"odds:combiner"); last=db.get(ApiCache,"odds:last-sync")
    return {"policy":"stable-market-v1","experimental_weights":{"cross_source_only":.10,"stable_observed":.20},"configured":bool(get_settings().odds_api_key),"provider":"The Odds API","observations":db.query(OddsObservation).count(),"combiner":report.payload if report else {"status":"collecting","samples":0,"minimum":200,"weight":0},"goals_combiner":goals.payload if goals else {"samples":0,"minimum":200,"weight":0,"status":"collecting"},"last_sync":last.payload if last else None,"refresh":"Cada 24 horas; no es un feed de momios en vivo.","coverage":{"result":True,"goals":"Combinación previa con tasa implícita Poisson; requiere validación temporal.","corners":False,"yellows":False}}

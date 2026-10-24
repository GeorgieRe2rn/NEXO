"""Cartelera independiente: calendarios públicos, sin atribuir mercados a Draftea."""
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta, timezone
from app.etl.calendar import utcnow, aware, parse_iso, kickoff_iso
from app.infrastructure.cache import cache_get, cache_put
from app.infrastructure.db.models import Match
from app.services.live_feed import get_json, map_status
from app.services.draftea_reference import REFERENCES, REFERENCE_DATE

SPORTS={"soccer":("Fútbol","soccer/all"),"basketball":("Básquetbol NBA","basketball/nba"),"football":("Fútbol americano NFL","football/nfl"),"baseball":("Béisbol MLB","baseball/mlb"),"hockey":("Hockey NHL","hockey/nhl")}
LOCAL=timezone(timedelta(hours=-7))
ROOT="https://site.api.espn.com/apis/site/v2/sports"


def local_event_day(value):
    return parse_iso(value).astimezone(LOCAL).date()


def catalog(db,day,sport="soccer"):
    key=f"catalog:v1:{day}:{sport}"
    cached=cache_get(db,key)
    if cached: return hydrate_local(db, attach_references(cached))
    selected=list(SPORTS) if sport=="ALL" else [sport]
    jobs=[(s,(day+timedelta(days=offset)).strftime("%Y%m%d")) for s in selected for offset in (0,1)]
    def fetch(job):
        s,date=job
        try: return s,get_json(f"{ROOT}/{SPORTS[s][1]}/scoreboard",{"dates":date,"limit":1000}),None
        except Exception as exc:return s,{},type(exc).__name__
    events={};errors=[];labels={};missing={}
    with ThreadPoolExecutor(max_workers=6) as pool:
        responses=list(pool.map(fetch,jobs))
    for s,data,error in responses:
        if error:errors.append({"sport":s,"error":error});continue
        for event in data.get("events",[]):
            try:
                if not event.get("date") or local_event_day(event["date"])!=day:continue
            except (ValueError,TypeError):
                errors.append({"sport":s,"error":"Fecha inválida omitida"});continue
            uid=re.search(r"~l:(\d+)",event.get("uid",""))
            league_id=uid.group(1) if uid else "unknown"
            league_key=f"{s}:{league_id}"
            known=labels.get(league_key) or (cache_get(db,f"catalog:league:{league_key}") if league_key not in missing else None)
            if known:labels[league_key]=known
            elif s=="soccer":missing.setdefault(league_key,(s,str(event["id"])))
            else: labels[league_key]={"name":(data.get("leagues") or [{}])[0].get("name") or SPORTS[s][0]}
            events[(s,str(event["id"]))]=(event,league_key)
    def league_info(job):
        league_key,(s,event_id)=job
        try:
            league=get_json(f"{ROOT}/{SPORTS[s][1]}/summary",{"event":event_id}).get("header",{}).get("league",{})
            return league_key,{"name":league.get("name") or "Competición sin identificar","slug":league.get("slug")}
        except Exception:return league_key,{"name":"Competición sin identificar"}
    with ThreadPoolExecutor(max_workers=6) as pool:
        for league_key,info in pool.map(league_info,missing.items()):
            labels[league_key]=info
            if info.get("slug"):cache_put(db,f"catalog:league:{league_key}","espn","summary",info,ttl_hours=720)
    tracked={str(m.provider_id):m for m in db.query(Match).filter(Match.provider=="espn",Match.provider_id.in_([i for _,i in events])).all()}
    items=[]
    for (s,event_id),(event,league_key) in events.items():
        comp=(event.get("competitions") or [{}])[0]
        competitors=comp.get("competitors") or []
        home=next((c for c in competitors if c.get("homeAway")=="home"),None)
        away=next((c for c in competitors if c.get("homeAway")=="away"),None)
        if not home or not away:continue
        match=tracked.get(event_id) if s=="soccer" else None
        source=next((l.get("href") for l in event.get("links",[]) if str(l.get("href","")).startswith("https://www.espn.com/")),None)
        items.append({"id":f"{s}:{event_id}","provider_id":event_id,"sport":s,"sport_name":SPORTS[s][0],"competition":labels.get(league_key,{"name":"Competición sin identificar"}),
            "kickoff":event["date"],"status":map_status(comp.get("status") or event.get("status") or {}),
            "home":home.get("team",{}).get("displayName") or home.get("athlete",{}).get("displayName"),"away":away.get("team",{}).get("displayName") or away.get("athlete",{}).get("displayName"),
            "match_id":match.id if match else None,"forecast_available":bool(match and match.prediction),"source_url":source,"draftea_verified":False})
    items.sort(key=lambda e:(parse_iso(e["kickoff"]),e["id"]))
    result={"date":str(day),"timezone":"America/Hermosillo","fetched_at":kickoff_iso(utcnow()),"items":items,"total":len(items),"errors":errors,
        "draftea":{"verified":False,"url":"https://www.draftea.mx/","notice":"Calendario obtenido de ESPN. La oferta y los mercados de Draftea no están verificados: su sitio público consultado no expone la cartelera. No se muestran cuotas ni se envían apuestas."},
        "coverage":"Fútbol internacional y NBA, NFL, MLB, NHL según la fuente. Calendario ampliado con análisis en competiciones compatibles; los encuentros sin datos suficientes no reciben pronósticos inventados."}
    cache_put(db,key,"espn","global-scoreboard",result,ttl_hours=1/12 if not errors else 1/60)
    return hydrate_local(db, attach_references(result))


def attach_references(result):
    from copy import deepcopy
    result=deepcopy(result)
    for event in result["items"]:
        event["draftea_reference"]=REFERENCES.get(event["provider_id"]) if event["sport"]=="soccer" and result["date"]==REFERENCE_DATE else None
    matched=[e for e in result["items"] if e["draftea_reference"]]
    favorites=sorted([e for e in matched if e["draftea_reference"]["american_odds"]<0],key=lambda e:e["draftea_reference"]["implied_probability"],reverse=True)
    result["screenshot_matches"]=len(matched)
    result["favorites"]=favorites[:6]
    result["draftea"]["notice"]="Se cruzan nombres, rivales y horarios con las capturas aportadas. Los momios son los de esas imágenes, no precios actuales ni probabilidades calibradas del modelo. La disponibilidad actual en Draftea sigue sin verificar."
    return result


def hydrate_local(db, result):
    from app.services.competition_registry import LEAGUES
    result["items"]=[e for e in result["items"] if e["sport"]=="soccer" and e["competition"].get("slug") in LEAGUES.values()]
    result["total"]=len(result["items"])
    ids=[e["provider_id"] for e in result["items"] if e["sport"]=="soccer"]
    matches={str(m.provider_id):m for m in db.query(Match).filter(Match.provider=="espn",Match.provider_id.in_(ids)).all()}
    from app.infrastructure.db.models import ForecastSnapshot
    for event in result["items"]:
        match=matches.get(event["provider_id"]) if event["sport"]=="soccer" else None
        event["match_id"]=match.id if match else None
        snapshot=db.query(ForecastSnapshot).filter_by(match_id=match.id,phase="PRE").order_by(ForecastSnapshot.id.desc()).first() if match else None
        event["forecast_available"]=bool(snapshot)
        event["forecast_reason"]="Previo y registro automático disponibles" if snapshot else "Historial insuficiente o competición sin modelo compatible"
        event["forecast_markets"]=[k for k,v in snapshot.payload["markets"].items() if v.get("available")] if snapshot else []
    return result

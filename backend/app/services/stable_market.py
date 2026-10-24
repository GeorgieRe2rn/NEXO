"""Selección automática por concordancia entre fuentes y movimiento observado.
Los umbrales y pesos iniciales son reglas experimentales, no precisión validada.
"""
import math
from statistics import median
from app.etl.calendar import parse_iso, aware

POLICY = "stable-market-v1"
MAX_AGE = 86400
MAX_SPREAD = .08
MAX_MOVEMENT = .04
MIN_SOURCES = 3
# Evita contar ediciones regionales conocidas como confirmaciones independientes.
FAMILIES = {"unibet":"unibet", "leovegas":"leovegas", "betsson":"betsson-nordic", "nordicbet":"betsson-nordic"}


def family(key):
    for prefix, group in FAMILIES.items():
        if key.startswith(prefix): return group
    return key


def reference(books, market, now):
    groups={}
    for book in books:
        quote=book.get("markets",{}).get(market)
        if not quote: continue
        try:
            age=(now-parse_iso(quote["updated_at"])).total_seconds()
            p=quote["probabilities"]
            prices=quote["prices"]
            size=3 if market=="result" else 2
            if not 0<=age<=MAX_AGE or len(p)!=size or len(prices)!=size:continue
            if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not 0<v<1 for v in p):continue
            if abs(sum(p)-1)>.00001:continue
            if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<=1 for v in prices):continue
            line=quote.get("line")
            if market=="goals" and (not isinstance(line,(int,float)) or not 0<line<15 or line%1!=.5):continue
            key=family(book["key"])
            candidate={"book":book,"quote":quote,"p":p,"age":age,"margin":abs(sum(1/v for v in prices)-1)}
            if key not in groups or (age,candidate["margin"],book["key"]) < (groups[key]["age"],groups[key]["margin"],groups[key]["book"]["key"]):groups[key]=candidate
        except (KeyError,TypeError,ValueError):continue
    rows=list(groups.values())
    if market=="goals" and rows:
        # Compara el mismo mercado/línea. Nunca mezcla Over 2.5 con Over 3.5.
        lines={r["quote"]["line"] for r in rows}
        chosen=min(lines,key=lambda line:(-sum(r["quote"]["line"]==line for r in rows),line))
        rows=[r for r in rows if r["quote"]["line"]==chosen]
    if len(rows)<MIN_SOURCES:return {"available":False,"reason":"Menos de tres fuentes distintas con cuotas vigentes.","sources":len(rows)}
    center=[median(r["p"][i] for r in rows) for i in range(len(rows[0]["p"]))]
    retained=[r for r in rows if max(abs(a-b) for a,b in zip(r["p"],center))<=MAX_SPREAD]
    if len(retained)<MIN_SOURCES:return {"available":False,"reason":"Sin consenso suficiente entre las casas.","sources":len(retained)}
    spread=max(max(r["p"][i] for r in retained)-min(r["p"][i] for r in retained) for i in range(len(center)))
    if spread>MAX_SPREAD:return {"available":False,"reason":"Cuotas demasiado dispersas entre casas.","spread":spread,"sources":len(retained)}
    center=[median(r["p"][i] for r in retained) for i in range(len(center))]
    center=[v/sum(center) for v in center]
    selected=min(retained,key=lambda r:(sum(abs(a-b) for a,b in zip(r["p"],center)),r["margin"],r["age"],r["book"]["key"]))
    result={"available":True,"sources":len(retained),"spread":spread,"probabilities":center,"selected_book":{"key":selected["book"]["key"],"name":selected["book"]["name"],**selected["quote"]},"oldest_age_seconds":max(r["age"] for r in retained)}
    if market=="result":result["value"]=center
    else:
        from app.services.odds_feed import implied_goal_means
        line=selected["quote"]["line"]
        result.update(line=line,value=implied_goal_means([{"markets":{"goals":{"line":line,"probabilities":center}}}])[0])
    return result


def select_references(payload, earlier, now, captured):
    output={}
    for market in ("result","goals"):
        current=reference(payload.get("bookmakers",[]),market,now)
        current.update(policy=POLICY,temporal_observations=1,movement=None,initial_weight=0,state="unavailable")
        if current["available"]:
            past=[]
            for old in earlier:
                if not 1800 <= (captured-aware(old.captured_at)).total_seconds() <= 48*3600:continue
                prior=reference(old.payload.get("bookmakers",[]),market,aware(old.captured_at))
                if prior["available"] and prior.get("line")==current.get("line"):past.append(prior)
            current["temporal_observations"]=1+len(past)
            if past:
                vectors=[current["probabilities"]]+[p["probabilities"] for p in past]
                movement=max(max(v[i] for v in vectors)-min(v[i] for v in vectors) for i in range(len(current["probabilities"])))
                current["movement"]=movement
                if movement<=MAX_MOVEMENT:
                    current.update(state="stable_observed",initial_weight=.20)
                else:current.update(state="moving",reason="Cambios entre capturas superiores a cuatro puntos porcentuales.")
            else:current.update(state="cross_source_only",initial_weight=.10,reason="Concordancia entre casas; todavía sin historial temporal suficiente.")
        output[market]=current
    return output

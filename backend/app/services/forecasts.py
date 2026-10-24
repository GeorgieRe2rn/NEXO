"""Pronósticos congelados, selecciones académicas y calibración temporal supervisada."""
import hashlib
import json
import math
from collections import defaultdict
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.etl.calendar import aware, kickoff_iso, parse_iso, utcnow
from app.infrastructure.db.models import AutomaticSelectionRevision, AutomaticForecastLink, User, ForecastRevision, ForecastSelection, ForecastSnapshot, Match, Prediction
from app.ml.engine import lambdas
from app.ml.form import compute_team_form
from app.ml.markets import SELECTION_POLICY, result_suggestion, result_wins, DEFAULT_PARAMETERS, MARKETS, MARKET_LINES, market_lines, calibrated_probs, count_base, minute_from_clock, project_market, result_probabilities

MIN_LEARNING_MATCHES = 40
OBSERVED_POLICY = "observed-team-history-v1"
MISSING_HISTORY = "Sin historial real suficiente de ambos equipos. No se genera pronóstico ni apuesta automática."


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def active_revision(db):
    from app.services.market_pipeline import SCHEMA, deployment
    from app.core.config import get_settings
    if get_settings().forecast_architecture == "legacy-v1":
        row = next((r for r in db.query(ForecastRevision).filter(ForecastRevision.adopted.is_(True)).order_by(ForecastRevision.id.desc()).all() if r.report.get("architecture") != SCHEMA), None)
        if row is None:
            row=ForecastRevision(created_at=utcnow(),adopted=True,parameters={p:dict(DEFAULT_PARAMETERS) for p in ("PRE","LIVE")},report={"status":"initial","reason":"Modelo inicial legado"})
            db.add(row);db.flush()
        return row
    signature = deployment(db)
    row = next((r for r in db.query(ForecastRevision).filter(ForecastRevision.adopted.is_(True)).order_by(ForecastRevision.id.desc()).all() if r.report.get("architecture") == SCHEMA and r.report.get("deployment") == signature), None)
    if row is None:
        row = ForecastRevision(created_at=utcnow(), adopted=True,
            parameters={p:dict(DEFAULT_PARAMETERS) for p in ("PRE", "LIVE")},
            report={"status":"initial", "architecture":SCHEMA,"deployment":signature,"reason":"Nueva arquitectura por mercado: calibración reiniciada. Historial anterior conservado y excluido de esta calibración."})
        db.add(row)
        db.flush()
    return row


def enforce_observed_data(db):
    """Retira mercados antiguos con relleno; conserva selección anulada y auditoría."""
    changed = withdrawn = 0
    from copy import deepcopy
    now = kickoff_iso(utcnow())
    for row in db.query(ForecastSnapshot).all():
        payload = deepcopy(row.payload)
        invalid = [key for key in ("corners","yellows") if payload.get("markets",{}).get(key,{}).get("available") and payload.get("base",{}).get(key,{}).get("data_policy") != OBSERVED_POLICY]
        if not invalid: continue
        payload.setdefault("data_quality_exclusions",{})
        for key in invalid:
            payload.get("base",{}).pop(key,None)
            payload["markets"][key] = {"market":key,"available":False,"reason":MISSING_HISTORY}
            payload["data_quality_exclusions"][key] = {"at":now,"reason":"Retirado por usar valores iniciales o suavizado sin respaldo de historial real de ambos equipos."}
            for selection in db.query(ForecastSelection).filter_by(snapshot_id=row.id,market=key).all():
                selection.settlement_history = [*(selection.settlement_history or []),{"from":selection.status,"to":"VOID","at":now,"reason":payload["data_quality_exclusions"][key]["reason"]}]
                selection.status = "VOID"
                selection.settled_at = utcnow()
                withdrawn += 1
        if payload.get("history_notice"):
            payload["history_notice"] = payload["history_notice"].replace("córners y amarillas usan priors cuando faltan observaciones", "los mercados sin historial real suficiente no están disponibles")
        row.payload = payload
        changed += 1
    db.commit()
    return {"snapshots_corrected":changed,"selections_withdrawn":withdrawn}


def observed_total(match, market):
    if market == "goals":
        if match.home_goals is None or match.away_goals is None:
            return None
        return match.home_goals + match.away_goals
    stats = (match.live_data or {}).get("stats") or {}
    field = "corners" if market == "corners" else "yellows"
    values = [(stats.get(side) or {}).get(field) for side in ("home","away")]
    if any(v is None or not isinstance(v,(int,float)) or not math.isfinite(v) or v < 0 for v in values):
        return None
    return sum(values)


def count_prior(db, match, market):
    from app.services.count_history import history_rows
    rows,coverage=history_rows(db,match,market)
    if min(coverage.values())<5:return None,0
    return sum(r["total"] for r in rows)/len(rows),len(rows)


def build_payload(db, match, phase, revision):
    from app.services.market_pipeline import SCHEMA, build_specialized_payload
    if revision.report.get("architecture") == SCHEMA:
        return build_specialized_payload(db, match, phase, revision)
    live = match.live_data or {}
    now = utcnow()
    max_age = timedelta(minutes=3) if phase == "LIVE" else timedelta(hours=3, minutes=15)
    if not match.verified_at or now - aware(match.verified_at) > max_age:
        return None
    if phase == "LIVE":
        if match.status != "LIVE" or live.get("score_pending_confirmation") or int(live.get("period") or 2) > 2:
            return None
        minute = minute_from_clock(live.get("clock"))
        if minute is None or observed_total(match,"goals") is None:
            return None
    else:
        if match.status != "SCHEDULED" or aware(match.kickoff) <= now:
            return None
        minute = None
    prediction = db.query(Prediction).filter_by(match_id=match.id).first()
    if prediction:
        lh, la = prediction.lambda_home, prediction.lambda_away
    else:
        from app.services.knowledge import _team_slices
        h = compute_team_form(match.home_team_id,_team_slices(db,match.home_team_id,match.kickoff))
        a = compute_team_form(match.away_team_id,_team_slices(db,match.away_team_id,match.kickoff))
        if min(h.matches_used,a.matches_used) < 5:
            return None
        lh, la = lambdas(h,a)
    base = {}
    if phase == "LIVE":
        remaining_time = max(1.0,95-minute)
        h_remaining = (lh*60 + match.home_goals*90)/(60+minute)*remaining_time/90
        a_remaining = (la*60 + match.away_goals*90)/(60+minute)*remaining_time/90
        stats = live.get("stats") or {}
        # Tiros a puerta observados ajustan la intensidad con un efecto acotado.
        for side in ("home","away"):
            sot = (stats.get(side) or {}).get("shots_on_target")
            if sot is not None and minute >= 10:
                factor = max(.75,min(1.3,(sot*90/max(minute,1)+4.4)/8.8))
                if side == "home": h_remaining *= factor
                else: a_remaining *= factor
        result = result_probabilities(match.home_goals,match.away_goals,h_remaining,a_remaining)
        goals = {"market":"goals","current":observed_total(match,"goals"),"remaining_mean":h_remaining+a_remaining,
            "line":max(observed_total(match,"goals")+.5,math.floor(observed_total(match,"goals")+h_remaining+a_remaining)+.5),
            "basis":"marcador, minuto, intensidad previa y tiros a puerta observados", "prior_samples":10}
    else:
        result = [prediction.p_home,prediction.p_draw,prediction.p_away] if prediction else result_probabilities(0,0,lh,la)
        goals = count_base("goals",lh+la,0,None,10)
        goals["basis"] = "cinco marcadores disponibles entre competiciones; cobertura limitada" if prediction and prediction.model_version.startswith("global-") else "últimos cinco partidos verificados por equipo"
    base["result"] = {"market":"result","probabilities":result}
    base["goals"] = goals
    markets = {}
    for market in ("corners","yellows"):
        observed = 0 if phase == "PRE" else observed_total(match,market)
        details_at = live.get("details_at")
        fresh_details = details_at and now - parse_iso(details_at) <= timedelta(minutes=3)
        if phase == "LIVE" and (observed is None or not fresh_details):
            markets[market] = {"market":market,"available":False,"reason":"La fuente no proporciona ambos contadores recientes."}
            continue
        from app.services.count_history import history_rows
        records,coverage=history_rows(db,match,market)
        if min(coverage.values())<5:
            markets[market] = {"market":market,"available":False,"history_coverage":coverage,"reason":f"Historial real: local {coverage['home']}/5, visitante {coverage['away']}/5. Sin datos suficientes para pronosticar este mercado."}
            continue
        prior=sum(r["total"] for r in records)/len(records)
        base[market] = count_base(market,prior,observed,minute,len(records))
        base[market].update(data_policy=OBSERVED_POLICY,basis="Media de totales publicados en cinco partidos previos por equipo; sin valores de relleno.",history=records,history_coverage=coverage)
    parameters = revision.parameters[phase]
    markets.update({k:project_market(v,parameters) for k,v in base.items()})
    return {"phase":phase,"minute":minute,"clock":live.get("clock") if phase=="LIVE" else None,
        "score":[match.home_goals,match.away_goals] if phase=="LIVE" else [0,0],
        "markets":markets,"base":base,"model_version":f"mercados-v1-r{revision.id}",
        "rules":"Resultado final a 90 minutos más añadido. Prórroga/penales: selección anulada. Sin dinero.",
        "assumptions":"Poisson e intensidades heurísticas; horizonte en vivo de 95 min. Calibración separada por fase y mercado.",
        "prediction_family":prediction.model_version if prediction else "forma-l5",
        "history_notice":prediction.explanation.get("notice") if prediction else None,
        "observed_details_at":live.get("details_at") if phase=="LIVE" else None}


def capture_forecasts(db, matches):
    revision = active_revision(db)
    from app.services.market_pipeline import SCHEMA, Evidence
    if revision.report.get("architecture")==SCHEMA:
        db.info["pipeline_evidence"]=Evidence(db)
    created = 0
    for match in matches:
        phase = "LIVE" if match.status=="LIVE" else "PRE"
        payload = build_payload(db,match,phase,revision)
        if payload is None:
            continue
        if payload.get("architecture") and phase == "PRE":
            from app.services.market_pipeline import sync_prediction_view
            sync_prediction_view(db,match,payload)
        identity = {"match":match.id,"revision":revision.id,"phase":phase,"base":payload["base"],"clock":payload["clock"],"score":payload["score"]}
        odds_sources={k:{"id":v["odds"].get("id"),"weight":v["odds"].get("weight",0),"deployment":v["odds"].get("model_deployment")} for k,v in payload.get("specialists",{}).items() if v.get("odds")}
        if odds_sources: identity["odds_sources"]=odds_sources
        key = digest(identity)
        if db.query(ForecastSnapshot.id).filter_by(fingerprint=key).first():
            continue
        db.add(ForecastSnapshot(match_id=match.id,phase=phase,fingerprint=key,revision_id=revision.id,
            created_at=utcnow(),source_at=match.verified_at,payload=payload))
        created += 1
    db.commit()
    revise_automatic_selections(db)
    db.info.pop("pipeline_evidence",None)
    if revision.report.get("architecture")==SCHEMA:
        from app.services.market_pipeline import capture_shadow,settle_shadow
        capture_shadow(db,matches)
        settle_shadow(db)
    return created


def revise_automatic_selections(db):
    """Revisa los cuatro mercados antes del inicio, solo ante modelo/política nuevos."""
    revision=active_revision(db)
    now=utcnow()
    refreshed_by_match={}
    rows=db.query(ForecastSelection,Match).join(AutomaticForecastLink,AutomaticForecastLink.selection_id==ForecastSelection.id).join(Match,Match.id==AutomaticForecastLink.match_id).filter(ForecastSelection.status=="PENDING",Match.status=="SCHEDULED",Match.kickoff>now).all()
    for selection,match in rows:
        original=db.get(ForecastSnapshot,selection.snapshot_id)
        quote=db.query(ForecastSnapshot).filter_by(match_id=match.id,phase="PRE",revision_id=revision.id).order_by(ForecastSnapshot.id.desc()).first()
        if selection.policy_version==SELECTION_POLICY and original.revision_id==revision.id and (not quote or original.payload.get("odds_revision")==quote.payload.get("odds_revision")):
            continue
        from app.services.market_pipeline import SCHEMA
        new_market=quote.payload["markets"].get(selection.market) if quote else None
        if revision.report.get("architecture")==SCHEMA and original.payload.get("architecture")!=SCHEMA and (not new_market or not new_market.get("available")):
            selection.status="VOID";selection.settled_at=now
            selection.selection_reason="Retirada en la migración v2: falta evidencia suficiente para este mercado. El registro anterior se conserva."
            selection.settlement_history=[*(selection.settlement_history or []),{"from":"PENDING","to":"VOID","at":kickoff_iso(now),"reason":selection.selection_reason,"reason_code":SCHEMA}]
            continue
        if not quote or aware(quote.created_at)>=aware(match.kickoff): continue
        if match.id not in refreshed_by_match:
            refreshed_by_match[match.id]=build_payload(db,match,"PRE",revision)
        refreshed=refreshed_by_match[match.id]
        if refreshed is None or digest(refreshed["base"])!=digest(quote.payload["base"]): continue
        market=quote.payload["markets"].get(selection.market)
        if not market or not market.get("available"): continue
        line=-1.0
        choices=market["choices"]
        if selection.market!="result":
            line=min(MARKET_LINES[selection.market],key=lambda v:abs(v-market["line"]))
            choices=market_lines(market)[str(line)]["choices"]
        suggestion=result_suggestion(choices) if selection.market=="result" else None
        pick=suggestion["pick"] if suggestion else max(choices,key=choices.get)
        probability=suggestion["probability"] if suggestion else choices[pick]
        previous={"snapshot_id":selection.snapshot_id,"pick":selection.pick,"probability":selection.probability,"line":selection.line_key,"policy":selection.policy_version,"model":original.payload["model_version"]}
        current={"snapshot_id":quote.id,"pick":pick,"probability":probability,"line":line,"policy":SELECTION_POLICY,"model":quote.payload["model_version"]}
        db.add(AutomaticSelectionRevision(selection_id=selection.id,created_at=now,previous=previous,current=current,reason="Revisión automática previa al inicio por nueva versión del modelo, de la política o de los momios validados."))
        selection.snapshot_id=quote.id;selection.pick=pick;selection.probability=probability;selection.line_key=line
        selection.policy_version=SELECTION_POLICY;selection.selection_reason=suggestion["reason"] if suggestion else "Selección revisada con el modelo vigente antes del inicio."
    db.commit()


def record_automatic_selections(db,matches,only_markets=None):
    """Una elección previa inmutable por cuenta, partido y mercado, sin dinero."""
    now=utcnow()
    users=db.query(User).all()
    for match in matches:
        retrospective=match.status=="LIVE"
        if match.provider!="espn" or match.status not in {"SCHEDULED","LIVE"} or (not retrospective and aware(match.kickoff)<=now):
            continue
        max_age=timedelta(minutes=3) if retrospective else timedelta(hours=3,minutes=15)
        if not match.verified_at or now-aware(match.verified_at)>max_age:
            continue
        quote=retrospective_quote(db,match) if retrospective else db.query(ForecastSnapshot).filter_by(match_id=match.id,phase="PRE").order_by(ForecastSnapshot.id.desc()).first()
        from app.core.config import get_settings
        from app.services.market_pipeline import SCHEMA
        if not retrospective and get_settings().forecast_architecture==SCHEMA and quote and quote.payload.get("architecture")!=SCHEMA:
            continue
        if not quote or (not retrospective and aware(quote.created_at)>=aware(match.kickoff)):
            continue
        for user in users:
            for key in MARKETS:
                if only_markets is not None and key not in only_markets:continue
                link=db.query(AutomaticForecastLink).filter_by(user_id=user.id,match_id=match.id,market=key).first()
                retired=db.get(ForecastSelection,link.selection_id) if link else None
                if retired:
                    original=db.get(ForecastSnapshot,retired.snapshot_id)
                    from app.services.market_pipeline import SCHEMA
                    migration_recovery=any(r.get("reason_code")==SCHEMA for r in (retired.settlement_history or [])) and quote.payload.get("architecture")==SCHEMA
                    observed_recovery=key in {"corners","yellows"} and key in original.payload.get("data_quality_exclusions",{}) and quote.payload.get("base",{}).get(key,{}).get("data_policy")==OBSERVED_POLICY
                    recoverable=(not retrospective and retired.status=="VOID" and (migration_recovery or observed_recovery))
                    if not recoverable:continue
                market=quote.payload["markets"].get(key)
                if not market or not market.get("available"):
                    continue
                line=-1.0
                choices=market["choices"]
                if key!="result":
                    # Línea próxima al total esperado, no búsqueda de probabilidades triviales.
                    line=min(MARKET_LINES[key],key=lambda v:abs(v-market["line"]))
                    choices=market_lines(market)[str(line)]["choices"]
                recommendation=result_suggestion(choices) if key=="result" else None
                pick=recommendation["pick"] if recommendation else max(choices,key=choices.get)
                try:
                    with db.begin_nested():
                        if retired:
                            probability=recommendation["probability"] if recommendation else choices[pick]
                            reason="Pronóstico recuperado antes del inicio tras obtener cinco antecedentes reales por equipo."
                            db.add(AutomaticSelectionRevision(selection_id=retired.id,created_at=now,
                                previous={"snapshot_id":retired.snapshot_id,"pick":"RETIRADA","line":None,"probability":None,"model":original.payload["model_version"]},
                                current={"snapshot_id":quote.id,"pick":pick,"line":line,"probability":probability,"model":quote.payload["model_version"]},reason=reason))
                            retired.snapshot_id=quote.id;retired.pick=pick;retired.probability=probability;retired.line_key=line
                            retired.created_at=now;retired.status="PENDING";retired.result_value=None;retired.settled_at=None
                            retired.policy_version=SELECTION_POLICY;retired.selection_reason=reason
                            retired.settlement_history=[*(retired.settlement_history or []),{"from":"VOID","to":"PENDING","at":kickoff_iso(now),"reason":reason}]
                            db.flush()
                            continue
                        selection=ForecastSelection(user_id=user.id,snapshot_id=quote.id,market=key,line_key=line,pick=pick,
                            probability=recommendation["probability"] if recommendation else choices[pick],policy_version=SELECTION_POLICY,selection_reason=recommendation["reason"] if recommendation else "Linea cercana al total esperado; se elige la opcion con mayor probabilidad.",created_at=now,status="PENDING",settlement_history=[])
                        db.add(selection);db.flush()
                        db.add(AutomaticForecastLink(user_id=user.id,match_id=match.id,market=key,selection_id=selection.id))
                        db.flush()
                except IntegrityError:
                    continue
    db.commit()


def retrospective_quote(db,match):
    """Importa un previo real; nunca lee marcador, minuto ni contadores actuales."""
    from copy import deepcopy
    existing=db.query(ForecastSnapshot).filter_by(match_id=match.id,phase="RETRO").first()
    if existing: return existing
    original=db.query(ForecastSnapshot).filter(ForecastSnapshot.match_id==match.id,ForecastSnapshot.phase=="PRE",ForecastSnapshot.created_at<match.kickoff).order_by(ForecastSnapshot.id.desc()).first()
    if original:
        payload=deepcopy(original.payload)
        prior_at=original.created_at
        revision_id=original.revision_id
        reconstructed=[]
    else:
        prediction=db.query(Prediction).filter(Prediction.match_id==match.id,Prediction.computed_at<match.kickoff).first()
        if not prediction: return None
        prior_at=prediction.computed_at
        revision_id=active_revision(db).id
        base={"result":{"market":"result","probabilities":[prediction.p_home,prediction.p_draw,prediction.p_away]},
            "goals":count_base("goals",prediction.lambda_home+prediction.lambda_away,0,None)}
        markets={k:project_market(v,DEFAULT_PARAMETERS) for k,v in base.items()}
        markets["goals"]["basis"]="Reconstruido desde las intensidades de goles del previo archivado."
        for key in ("corners","yellows"):
            markets[key]={"market":key,"available":False,"reason":MISSING_HISTORY}
        payload={"base":base,"markets":markets,"model_version":prediction.model_version+"-retrospectivo",
            "rules":"90 minutos más añadido. Prórroga/penales: anulado. Sin dinero.","clock":None,"minute":None,"score":[0,0]}
        reconstructed=["goals"]
    payload.update(phase="RETRO",retrospective=True,prior_at=kickoff_iso(prior_at),reconstructed_markets=reconstructed)
    row=ForecastSnapshot(match_id=match.id,phase="RETRO",fingerprint=digest({"retro":match.id}),revision_id=revision_id,
        created_at=utcnow(),source_at=prior_at,payload=payload)
    db.add(row);db.flush()
    return row


def snapshot_payload(row):
    if not row:
        return None
    return {"id":row.id,"created_at":kickoff_iso(row.created_at),"source_at":kickoff_iso(row.source_at),
        **{k:v for k,v in row.payload.items() if k != "base"}, "markets":{k:{**m,**({"suggestion":result_suggestion(m["choices"])} if k=="result" and m.get("available") else {}),"lines":market_lines(m)} for k,m in row.payload["markets"].items()}, "outcomes":row.outcomes}


def match_forecasts(db, match):
    latest = {p:db.query(ForecastSnapshot).filter_by(match_id=match.id,phase=p).order_by(ForecastSnapshot.id.desc()).first() for p in ("PRE","LIVE")}
    from app.core.config import get_settings
    from app.services.market_pipeline import SCHEMA
    if get_settings().forecast_architecture==SCHEMA and match.status=="SCHEDULED" and aware(match.kickoff)>utcnow() and latest["PRE"] and latest["PRE"].payload.get("architecture")!=SCHEMA:
        latest["PRE"]=None
    fresh = bool(match.verified_at and utcnow()-aware(match.verified_at)<=timedelta(minutes=3))
    result = {p:snapshot_payload(latest.get(p)) for p in ("PRE","LIVE")}
    result["live_current"] = bool(fresh and match.status=="LIVE" and latest.get("LIVE") and
        latest["LIVE"].payload.get("clock")== (match.live_data or {}).get("clock") and
        latest["LIVE"].payload.get("score")==[match.home_goals,match.away_goals] and
        not (match.live_data or {}).get("score_pending_confirmation") and int((match.live_data or {}).get("period") or 2)<=2)
    return result


def forecast_summary(db, match):
    phase="LIVE" if match.status=="LIVE" else "PRE"
    row=db.query(ForecastSnapshot).filter_by(match_id=match.id,phase=phase).order_by(ForecastSnapshot.id.desc()).first()
    from app.core.config import get_settings
    from app.services.market_pipeline import SCHEMA
    if row and get_settings().forecast_architecture==SCHEMA and match.status=="SCHEDULED" and aware(match.kickoff)>utcnow() and row.payload.get("architecture")!=SCHEMA:
        return None
    return snapshot_payload(row)


def actual_outcomes(match):
    live = match.live_data or {}
    if match.status in {"CANCELLED","POSTPONED"}:
        return {"void":"Partido cancelado o pospuesto; registra una nueva selección cuando se reprograme."}
    if match.status != "FINISHED":
        return None
    if int(live.get("period") or 2)>2:
        return {"void":"Se disputó prórroga o penales, fuera de las reglas de la selección."}
    if observed_total(match,"goals") is None:
        return None
    result = 0 if match.home_goals>match.away_goals else 2 if match.home_goals<match.away_goals else 1
    outcomes = {"result":result,"goals":observed_total(match,"goals")}
    # No liquida córners/tarjetas a partir de valores de un resumen anterior al final.
    if live.get("final_details"):
        for market in ("corners","yellows"):
            value = observed_total(match,market)
            if value is not None: outcomes[market]=value
    return outcomes


def settle_forecasts(db, matches):
    for match in matches:
        outcomes = actual_outcomes(match)
        if outcomes is None: continue
        rows = db.query(ForecastSnapshot).filter_by(match_id=match.id).all()
        for row in rows:
            row.outcomes = outcomes
            row.evaluated_at = utcnow()
            selections = db.query(ForecastSelection).filter_by(snapshot_id=row.id).all()
            for selection in selections:
                if selection.market in row.payload.get("data_quality_exclusions",{}):
                    continue
                value = outcomes.get(selection.market)
                if "void" in outcomes:
                    status = "VOID"
                elif value is None:
                    status = "PENDING"
                elif selection.market == "result":
                    status = "WON" if result_wins(selection.pick,value) else "LOST"
                else:
                    market = row.payload["markets"][selection.market]
                    if value < market["current"]:
                        status = "VOID"
                    else:
                        over = value > (selection.line_key if selection.line_key >= 0 else market["line"])
                        status = "WON" if (selection.pick == "OVER")==over else "LOST"
                if selection.status != status or selection.result_value != value:
                    timestamp = utcnow()
                    selection.settlement_history = [*(selection.settlement_history or []),{"from":selection.status,"to":status,"value":value,"at":kickoff_iso(timestamp),"source_at":(match.live_data or {}).get("details_at"),"reason":outcomes.get("void")}]
                    selection.status,selection.result_value,selection.settled_at = status,value,None if status=="PENDING" else timestamp
    db.commit()


def create_selection(db, user, snapshot_id, market, pick, line=None):
    snapshot = db.get(ForecastSnapshot,snapshot_id)
    if not snapshot: raise HTTPException(404,"Pronóstico no encontrado")
    match = db.get(Match,snapshot.match_id)
    if match.status not in {"SCHEDULED","LIVE"} or (snapshot.phase=="PRE" and aware(match.kickoff)<=utcnow()):
        raise HTTPException(409,"El mercado ya no está abierto.")
    max_age = timedelta(minutes=3) if snapshot.phase == "LIVE" else timedelta(hours=3, minutes=15)
    if not match.verified_at or utcnow()-aware(match.verified_at)>max_age:
        raise HTTPException(409,"La fuente está desactualizada. Espera una nueva consulta.")
    latest = db.query(ForecastSnapshot).filter_by(match_id=match.id,phase=snapshot.phase).order_by(ForecastSnapshot.id.desc()).first()
    if latest.id != snapshot.id or (snapshot.phase=="PRE" and match.status!="SCHEDULED"):
        raise HTTPException(409,"El pronóstico cambió. Actualiza antes de registrar.")
    if snapshot.phase=="LIVE" and not match_forecasts(db,match)["live_current"]:
        raise HTTPException(409,"El reporte en vivo cambió o está pendiente de confirmación.")
    refreshed=build_payload(db,match,snapshot.phase,db.get(ForecastRevision,snapshot.revision_id))
    if refreshed is None or digest(refreshed["base"].get(market)) != digest(snapshot.payload["base"].get(market)):
        raise HTTPException(409,"Las estadísticas o el modelo cambiaron. Espera la siguiente actualización.")
    quoted = snapshot.payload["markets"].get(market)
    line_key = -1.0
    if market != "result" and quoted and quoted.get("available"):
        line_key = quoted["line"] if line is None else line
        # Las selecciones antiguas sin línea explícita conservan su línea original.
        if line is not None and line not in MARKET_LINES.get(market,[]):
            raise HTTPException(422,"Linea no disponible para este mercado.")
        from app.ml.markets import over_probability
        over=over_probability(quoted["current"],max(0,quoted["expected_total"]-quoted["current"]),line_key)
        quoted={**quoted,"line":line_key,"choices":{"OVER":over,"UNDER":1-over},"closed":quoted["current"]>line_key}
    elif line is not None:
        raise HTTPException(422,"El resultado 1X2 no utiliza linea.")
    if not quoted or not quoted.get("available") or quoted.get("closed") or pick not in quoted["choices"]:
        raise HTTPException(422,"Selección o mercado no disponible.")
    if db.query(ForecastSelection).filter_by(user_id=user.id,snapshot_id=snapshot.id,market=market,line_key=line_key).first():
        raise HTTPException(409,"Ya registraste una selección en este mercado y actualización.")
    row = ForecastSelection(user_id=user.id,snapshot_id=snapshot.id,market=market,line_key=line_key,pick=pick,
        probability=quoted["choices"][pick],created_at=utcnow(),status="PENDING",settlement_history=[])
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409,"Ya existe una selección para esta actualización y mercado.")
    return {"id":row.id,"status":row.status}


def selections_report(db,user_id,league="ALL",automatic_only=False,page=1,status="ALL"):
    q = db.query(ForecastSelection,ForecastSnapshot,Match).join(ForecastSnapshot,ForecastSnapshot.id==ForecastSelection.snapshot_id).join(Match,Match.id==ForecastSnapshot.match_id).filter(ForecastSelection.user_id==user_id)
    if automatic_only:
        q=q.join(AutomaticForecastLink,AutomaticForecastLink.selection_id==ForecastSelection.id)
    if league != "ALL":
        from app.infrastructure.db.models import League
        q=q.join(League,League.id==Match.league_id).filter(League.code==league)
    rows=q.order_by(ForecastSelection.created_at.desc()).all()
    counts={k:sum(s.status==k for s,_,_ in rows) for k in ("PENDING","WON","LOST","VOID")}
    prospective=[s for s,f,_ in rows if f.phase!="RETRO" and s.status in {"WON","LOST"}]
    retro=[s for s,f,_ in rows if f.phase=="RETRO" and s.status in {"WON","LOST"}]
    n=len(prospective)
    by_market={key:{"total":sum(s.market==key for s,_,_ in rows),
        "won":sum(s.market==key and s.status=="WON" for s,_,_ in rows),
        "lost":sum(s.market==key and s.status=="LOST" for s,_,_ in rows),
        "pending":sum(s.market==key and s.status=="PENDING" for s,_,_ in rows)} for key in MARKETS}
    filtered=[r for r in rows if status=="ALL" or r[0].status==status]
    grouped=defaultdict(list)
    for r in filtered: grouped[r[2].id].append(r)
    ordered=sorted(grouped,key=lambda mid:(not any(s.status=="PENDING" for s,_,_ in grouped[mid]),aware(grouped[mid][0][2].kickoff),mid))
    pages=max(1,math.ceil(len(ordered)/20))
    page=min(max(1,page),pages)
    ids=set(ordered[(page-1)*20:page*20])
    visible=[r for r in filtered if r[2].id in ids]
    return {"counts":counts,"accuracy":sum(s.status=="WON" for s in prospective)/n if n else None,"retro_accuracy":sum(s.status=="WON" for s in retro)/len(retro) if retro else None,"retro_total":sum(f.phase=="RETRO" for _,f,_ in rows),"total":len(rows),"by_market":by_market,"page":page,"pages":pages,"match_total":len(ordered),"items":[{
        "id":s.id,"snapshot_id":f.id,"match_id":m.id,"home":m.home_team.short_name,"away":m.away_team.short_name,
        "league":m.league.code,"phase":f.phase,"market":s.market,"pick":None if s.market in f.payload.get("data_quality_exclusions",{}) else s.pick,"kickoff":kickoff_iso(m.kickoff),"retrospective":f.phase=="RETRO","prior_at":f.payload.get("prior_at"),"reconstructed":s.market in f.payload.get("reconstructed_markets",[]),"basis":f.payload["markets"][s.market].get("basis"),
        "line":s.line_key if s.line_key>=0 and s.market not in f.payload.get("data_quality_exclusions",{}) else None,"probability":None if s.market in f.payload.get("data_quality_exclusions",{}) else s.probability,
        "withdrawal_reason":f.payload.get("data_quality_exclusions",{}).get(s.market,{}).get("reason"),
        "basis":f.payload["markets"].get(s.market,{}).get("basis"),"prior_samples":f.payload["markets"].get(s.market,{}).get("prior_samples"),"history_notice":f.payload.get("history_notice"),"prediction_family":f.payload.get("prediction_family"),
        **({"history":f.payload["markets"].get(s.market,{}).get("history",[]),"history_coverage":f.payload["markets"].get(s.market,{}).get("history_coverage")} if s.market in {"corners","yellows"} else {}),
        "model_recommendation":(s.pick if s.probability>=.5 else ("UNDER" if s.pick=="OVER" else "OVER")) if s.market!="result" else f.payload["markets"][s.market]["recommendation"],
        "model_version":f.payload["model_version"],"policy_version":s.policy_version,"selection_reason":s.selection_reason,"current_suggestion":result_suggestion(f.payload["markets"]["result"]["choices"]) if s.market=="result" else None,"status":s.status,"result_value":s.result_value,
        "created_at":kickoff_iso(s.created_at),"settled_at":kickoff_iso(s.settled_at),"audit":s.settlement_history,"revisions":[{"at":kickoff_iso(r.created_at),"previous":r.previous,"current":r.current,"reason":r.reason} for r in db.query(AutomaticSelectionRevision).filter_by(selection_id=s.id).order_by(AutomaticSelectionRevision.id)]} for s,f,m in visible]}


def learning_samples(db):
    from app.core.config import get_settings
    from app.services.market_pipeline import SCHEMA, deployment
    legacy = get_settings().forecast_architecture == "legacy-v1"
    signature = deployment(db) if not legacy else None
    rows = db.query(ForecastSnapshot,Match).join(Match,Match.id==ForecastSnapshot.match_id).filter(ForecastSnapshot.evaluated_at.isnot(None),ForecastSnapshot.phase.in_(["PRE","LIVE"])).order_by(Match.kickoff,Match.id,ForecastSnapshot.created_at,ForecastSnapshot.id).all()
    grouped={}
    for row,match in rows:
        compatible = not row.payload.get("odds_revision") and row.payload.get("architecture") == SCHEMA and db.get(ForecastRevision,row.revision_id).report.get("deployment") == signature
        if (compatible if not legacy else row.payload.get("architecture") != SCHEMA) and row.outcomes and "void" not in row.outcomes:
            grouped.setdefault((row.match_id,row.phase),(row,match))
    return list(grouped.values())


def loss_for(samples,parameters):
    losses=[]
    for row,_ in samples:
        pars=parameters[row.phase]
        per_match=[]
        for key,base in row.payload["base"].items():
            target=(row.outcomes or {}).get(key)
            if target is None: continue
            market=project_market(base,pars)
            if key=="result": probability=market["choices"][("LOCAL","EMPATE","VISITANTE")[int(target)]]
            else:
                if target < base["current"]: continue
                probability=market["choices"]["OVER" if target>base["line"] else "UNDER"]
            per_match.append(-math.log(max(probability,1e-12)))
        if per_match: losses.append(sum(per_match)/len(per_match))
    return sum(losses)/len(losses) if losses else None


def fit_parameters(samples, initial=None, validation=None):
    parameters={p:dict((initial or {}).get(p,DEFAULT_PARAMETERS)) for p in ("PRE","LIVE")}
    for phase in parameters:
        rows=[r for r,_ in samples if r.phase==phase]
        if len(rows)<25: continue
        if validation is not None and sum(r.phase==phase for r,_ in validation)<10: continue
        def result_loss(t):
            return sum(-math.log(max(calibrated_probs(r.payload["base"]["result"]["probabilities"],t)[int(r.outcomes["result"])],1e-12)) for r in rows)
        parameters[phase]["temperature"]=min([.6,.75,.9,1.0,1.15,1.3,1.5,1.8,2.0],key=result_loss)
        for key in ("goals","corners","yellows"):
            if sum(key in (r.outcomes or {}) and key in r.payload["base"] for r in rows)<25: continue
            if validation is not None and sum(r.phase==phase and key in (r.outcomes or {}) and key in r.payload["base"] for r,_ in validation)<10: continue
            targets=exposures=0.0
            for r in rows:
                base=r.payload["base"].get(key)
                target=r.outcomes.get(key)
                if base is not None and target is not None and target>=base["current"]:
                    targets+=target-base["current"]
                    exposures+=base["remaining_mean"]
            parameters[phase][f"{key}_scale"]=max(.6,min(1.6,(targets+20)/(exposures+20)))
    return parameters


def independent_calibration_gate(validation, candidate, champion):
    """Ningún mercado cambia porque otro mercado haya compensado su empeoramiento."""
    from copy import deepcopy
    selected=deepcopy(champion)
    checks={}
    for phase in ("PRE","LIVE"):
        for key in MARKETS:
            rows=[r for r,_ in validation if r.phase==phase and key in r.payload["base"] and (r.outcomes or {}).get(key) is not None]
            if len(rows)<10:continue
            def error(parameters):
                values=[]
                for row in rows:
                    base=row.payload["base"][key];target=row.outcomes[key]
                    if key!="result" and target<base["current"]:continue
                    market=project_market(base,parameters[phase])
                    choice=("LOCAL","EMPATE","VISITANTE")[int(target)] if key=="result" else "OVER" if target>base["line"] else "UNDER"
                    values.append(-math.log(max(market["choices"][choice],1e-12)))
                return sum(values)/len(values) if values else None
            old,new=error(champion),error(candidate)
            improved=old is not None and new is not None and new<old-.002
            parameter="temperature" if key=="result" else f"{key}_scale"
            if improved:selected[phase][parameter]=candidate[phase][parameter]
            checks[f"{phase}:{key}"]={"candidate":new,"champion":old,"adopted":improved,"samples":len(rows)}
    return selected,checks


def update_learning(db):
    from app.services.market_pipeline import SCHEMA, deployment
    from app.core.config import get_settings
    legacy = get_settings().forecast_architecture == "legacy-v1"
    samples=learning_samples(db)
    match_ids=list(dict.fromkeys(m.id for _,m in samples))
    if len(match_ids)<MIN_LEARNING_MATCHES: return
    # Calibra únicamente probabilidades producidas por el despliegue actual.
    signature = deployment(db) if not legacy else None
    match_ids=list(dict.fromkeys(m.id for _,m in samples))
    if len(match_ids)<MIN_LEARNING_MATCHES:return
    fingerprint=digest([SCHEMA,signature,[(r.id,r.outcomes) for r,_ in samples]])
    if db.query(ForecastRevision.id).filter_by(dataset_digest=fingerprint).first(): return
    cut=int(len(match_ids)*.7)
    split_time=aware(next(m.kickoff for _,m in samples if m.id==match_ids[cut]))
    train_ids={m.id for _,m in samples if aware(m.kickoff)<split_time}
    validation_ids={m.id for _,m in samples if aware(m.kickoff)>=split_time}
    train=[s for s in samples if s[1].id in train_ids]
    validation=[s for s in samples if s[1].id in validation_ids]
    if len(train_ids)<25 or len(validation_ids)<10: return
    champion=active_revision(db)
    train_end=max(aware(m.kickoff) for _,m in train)
    validation_start=min(aware(m.kickoff) for _,m in validation)
    # Ningún mismo partido, ni partidos simultáneos en la frontera, pueden filtrarse entre bloques.
    if train_end>=validation_start: return
    previous_cut=champion.report.get("train_end")
    if previous_cut and parse_iso(previous_cut)>=validation_start: return
    candidate=fit_parameters(train,champion.parameters,validation)
    calibration_checks={}
    if not legacy:
        candidate,calibration_checks=independent_calibration_gate(validation,candidate,champion.parameters)
    candidate_loss=loss_for(validation,candidate)
    champion_loss=loss_for(validation,champion.parameters)
    adopted=candidate_loss is not None and champion_loss is not None and candidate_loss<champion_loss-.002
    report={"architecture":SCHEMA if not legacy else "legacy-v1","deployment":signature,"market_checks":calibration_checks,"status":"adopted" if adopted else "not_improved","train_matches":len(train_ids),"validation_matches":len(validation_ids),
        "train_end":kickoff_iso(train_end),"validation_start":kickoff_iso(validation_start),
        "validation_end":kickoff_iso(max(aware(m.kickoff) for _,m in validation)),
        "candidate_log_loss":candidate_loss,"champion_log_loss":champion_loss,
        "reason":"Candidato adoptado tras reducir log loss temporal." if adopted else "Se conserva la versión vigente; el candidato no redujo lo suficiente el error temporal.",
        "scope":"Calibración global de las competiciones compatibles; un ejemplo por partido y fase. No es una prueba externa independiente."}
    db.add(ForecastRevision(created_at=utcnow(),adopted=adopted,parameters=candidate,report=report,dataset_digest=fingerprint))
    db.commit()


def learning_status(db):
    from app.services.market_pipeline import SCHEMA, model_status
    active=active_revision(db)
    latest=next((r for r in db.query(ForecastRevision).order_by(ForecastRevision.id.desc()).all() if r.report.get("architecture")==SCHEMA and r.report.get("deployment")==active.report.get("deployment")),active)
    samples=learning_samples(db)
    n=len({m.id for r,m in samples if db.get(ForecastRevision,r.revision_id).report.get("deployment")==active.report.get("deployment")})
    return {"version":f"{SCHEMA}-r{active.id}" if active else "Inicializando","architecture":SCHEMA,"specialists":model_status(db),
        "evaluated_matches":n,"minimum_matches":MIN_LEARNING_MATCHES,
        "status":"awaiting_evidence" if n<MIN_LEARNING_MATCHES else "monitoring",
        "last_attempt":latest.report if latest else None,
        "updated_at":kickoff_iso(active.created_at) if active else None,
        "notice":"Aprende de resultados confirmados, no de tus elecciones. Una revisión puede no mejorar y no se adopta automáticamente por el simple paso del tiempo."}

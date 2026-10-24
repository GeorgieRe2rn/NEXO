"""Diagnóstico de selecciones congeladas; nunca modifica apuestas ni entrena."""
from collections import Counter

from app.infrastructure.db.models import AutomaticForecastLink, ForecastSelection, ForecastSnapshot, Match, League
from app.ml.markets import MARKETS, SELECTION_POLICY, result_suggestion, result_wins
from app.services.forecasts import actual_outcomes


def error_analysis(db,user_id,league="ALL"):
    query=db.query(ForecastSelection,ForecastSnapshot,Match).join(AutomaticForecastLink,AutomaticForecastLink.selection_id==ForecastSelection.id).join(ForecastSnapshot,ForecastSnapshot.id==ForecastSelection.snapshot_id).join(Match,Match.id==ForecastSnapshot.match_id).filter(ForecastSelection.user_id==user_id)
    if league!="ALL": query=query.join(League,League.id==Match.league_id).filter(League.code==league)
    rows=query.all()
    settled=[r for r in rows if r[0].status in {"WON","LOST"}]
    discrepancies=[]
    for s,f,m in settled:
        actual=actual_outcomes(m) or {}
        value=actual.get(s.market)
        if value is None:
            discrepancies.append({"selection_id":s.id,"reason":"Resultado final actualmente no disponible."})
            continue
        won=result_wins(s.pick,value) if s.market=="result" else ((s.pick=="OVER")== (value>s.line_key))
        if value!=s.result_value or won!=(s.status=="WON"):
            discrepancies.append({"selection_id":s.id,"reason":"El registro no coincide con el último resultado de la fuente; revisar liquidación."})
    markets={}
    for key in MARKETS:
        sample=[r for r in settled if r[0].market==key]
        counts=Counter(s.status for s,_,_ in sample)
        counts_data=[(f.payload["markets"][key].get("expected_total"),s.result_value) for s,f,_ in sample]
        values=[(expected,actual) for expected,actual in counts_data if expected is not None and actual is not None]
        markets[key]={"settled":len(sample),"won":counts["WON"],"lost":counts["LOST"],
            "retrospective":sum(f.phase=="RETRO" for _,f,_ in sample),
            "reconstructed":sum(key in f.payload.get("reconstructed_markets",[]) for _,f,_ in sample),
            "mean_expected":sum(v[0] for v in values)/len(values) if values else None,
            "mean_actual":sum(v[1] for v in values)/len(values) if values else None,
            "mean_error":sum(v[0]-v[1] for v in values)/len(values) if values else None}
    result_rows=[r for r in settled if r[0].market=="result"]
    baseline=candidate=changed=close_losses=0
    for s,f,_ in result_rows:
        choices=f.payload["markets"]["result"]["choices"]
        old=max(choices,key=choices.get)
        suggestion=result_suggestion(choices)
        baseline+=result_wins(old,s.result_value)
        candidate+=result_wins(suggestion["pick"],s.result_value)
        changed+=old!=suggestion["pick"]
        close_losses+=s.status=="LOST" and suggestion["pick"] in {"1X","X2"}
    return {"settled":len(settled),"matches":len({m.id for _,_,m in settled}),
        "won":sum(s.status=="WON" for s,_,_ in settled),"lost":sum(s.status=="LOST" for s,_,_ in settled),
        "prospective_matches":len({m.id for _,f,m in settled if f.phase!="RETRO"}),
        "retrospective_matches":len({m.id for _,f,m in settled if f.phase=="RETRO"}),
        "markets":markets,"settlement_discrepancies":discrepancies,
        "policy":{"version":SELECTION_POLICY,"threshold_pp":5,"sample":len(result_rows),"single_wins":baseline,
            "candidate_wins":candidate,"changed":changed,"close_result_losses":close_losses,
            "note":"Comparación retrospectiva de la regla sobre los mismos partidos. No son apuestas ganadas nuevas ni validación independiente."},
        "conclusion":"La muestra es pequeña. La doble oportunidad cambia la cobertura de la selección, no mejora por sí sola la calibración 1X2. Los coeficientes se mantienen hasta disponer de evidencia temporal suficiente."}

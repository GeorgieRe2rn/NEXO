"""Distribuciones interpretables para mercados de resultado y conteos.

No hay cuotas, dinero ni cobros. Las probabilidades son estimaciones del modelo.
"""
import math
import re

from app.ml.engine import _poisson

MARKETS = ("result", "goals", "corners", "yellows")
DEFAULT_PARAMETERS = {"temperature": 1.0, "goals_scale": 1.0, "corners_scale": 1.0, "yellows_scale": 1.0}
MARKET_LINES = {"goals": [i + .5 for i in range(6)], "corners": [i + .5 for i in range(6, 12)], "yellows": [i + .5 for i in range(1, 7)]}
SELECTION_POLICY = "doble-oportunidad-v1-5pp"
DOUBLE_CHANCE_GAP = .05


def result_suggestion(choices):
    """Cubre equipo/empate solo si son las dos clases principales y cercanas."""
    ranked=sorted(choices,key=choices.get,reverse=True)
    first,second=ranked[:2]
    gap=abs(choices[first]-choices[second])
    if "EMPATE" in (first,second) and gap<=DOUBLE_CHANCE_GAP+1e-12:
        team=second if first=="EMPATE" else first
        pick="1X" if team=="LOCAL" else "X2"
        return {"pick":pick,"probability":choices[team]+choices["EMPATE"],"gap":gap,
            "policy":SELECTION_POLICY,"reason":"Equipo y empate son las dos opciones principales y difieren como máximo 5 puntos porcentuales; se recomienda doble oportunidad."}
    return {"pick":first,"probability":choices[first],"gap":gap,"policy":SELECTION_POLICY,
        "reason":"Se mantiene el resultado simple: equipo y empate no son las dos opciones principales con diferencia de hasta 5 puntos porcentuales."}


def result_wins(pick,outcome):
    return int(outcome) in {"LOCAL":{0},"EMPATE":{1},"VISITANTE":{2},"1X":{0,1},"X2":{1,2}}.get(pick,set())


def market_lines(market):
    """Líneas fijas; una línea superada permanece visible pero cerrada."""
    if not market.get("available") or market["market"] == "result":
        return {}
    current = market["current"]
    remaining = max(0, market["expected_total"] - current)
    return {str(line): {"line": line, "choices": {"OVER": over_probability(current, remaining, line),
        "UNDER": 1-over_probability(current, remaining, line)}, "closed": current > line}
        for line in MARKET_LINES[market["market"]]}


def minute_from_clock(clock):
    if not clock:
        return None
    if str(clock).upper() in {"HT", "HALFTIME", "HALF TIME"}:
        return 45.0
    parts = re.findall(r"\d+", str(clock))
    if not parts:
        return None
    return min(130.0, float(parts[0]) + (float(parts[1]) if "+" in str(clock) and len(parts) > 1 else 0))


def over_probability(current, remaining_mean, line):
    threshold = math.floor(line - current)
    if threshold < 0:
        return 1.0
    if remaining_mean <= 0:
        return 0.0
    cdf = sum(_poisson(k, remaining_mean) for k in range(threshold + 1))
    return max(0.0, min(1.0, 1.0 - cdf))


def result_probabilities(home_goals, away_goals, home_remaining, away_remaining):
    probs = [0.0, 0.0, 0.0]
    # Malla adaptativa para no truncar indebidamente medias de goles altas.
    limit = max(15, int(max(home_remaining, away_remaining) + 10 * math.sqrt(max(home_remaining, away_remaining) + 1)))
    for i in range(limit + 1):
        for j in range(limit + 1):
            p = _poisson(i, home_remaining) * _poisson(j, away_remaining)
            result = 0 if home_goals + i > away_goals + j else 2 if home_goals + i < away_goals + j else 1
            probs[result] += p
    total = sum(probs)
    return [p / total for p in probs]


def calibrated_probs(base, temperature):
    logits = [math.log(max(p, 1e-12)) / temperature for p in base]
    offset = max(logits)
    values = [math.exp(v - offset) for v in logits]
    return [v / sum(values) for v in values]


def project_market(base, parameters):
    if base["market"] == "result":
        probs = calibrated_probs(base["probabilities"], parameters["temperature"])
        choices = dict(zip(("LOCAL", "EMPATE", "VISITANTE"), probs))
        return {"market":"result", "available":True, "choices":choices, "recommendation":max(choices, key=choices.get),"suggestion":result_suggestion(choices)}
    name = base["market"]
    mean = base["remaining_mean"] * parameters[f"{name}_scale"]
    over = over_probability(base["current"], mean, base["line"])
    choices = {"OVER":over, "UNDER":1 - over}
    return {"market":name, "available":True, "current":base["current"],
            "expected_total":base["current"] + mean, "line":base["line"],
            "choices":choices, "recommendation":max(choices, key=choices.get),
            "closed":base["current"] > base["line"], "prior_samples":base.get("prior_samples",0),
            "basis":base.get("basis"),**({"history":base["history"],"history_coverage":base["history_coverage"]} if "history" in base else {})}


def count_base(market, prior, observed, minute, prior_samples=0):
    if minute is None:
        remaining = prior
    else:
        remaining_time = max(1.0, 95.0 - minute)
        rate = (60 * prior + observed * 95) / (60 + minute)
        remaining = rate * remaining_time / 95
    expected = observed + remaining
    line = max(observed + 0.5, math.floor(expected) + 0.5)
    return {"market":market,"current":observed,"remaining_mean":remaining,"line":line,
            "prior_samples":prior_samples,"basis":"histórico observado con suavizado" if prior_samples else "prior inicial de dominio; sin histórico observado suficiente"}

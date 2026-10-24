"""Modelo inicial de marcadores publicados entre competiciones; sin cuotas ni datos en vivo."""
import math
from datetime import timedelta
from app.etl.calendar import aware, parse_iso, utcnow, kickoff_iso
from app.infrastructure.db.models import Prediction
from app.ml.engine import poisson_grid

VERSION = "global-l5-v1.0"
NOTICE = "Cinco antecedentes disponibles de ESPN entre competiciones. La cobertura puede ser incompleta y no ajusta la fuerza entre ligas. Modelo inicial sin entrenamiento; los mercados sin historial real suficiente no están disponibles."

def extract_history(data, match):
    result = {"home": [], "away": [], "notice": NOTICE}
    cutoff = aware(match.kickoff)
    for side, team in (("home", match.home_team), ("away", match.away_team)):
        rows = {}
        for group in data.get("lastFiveGames") or []:
            if str((group.get("team") or {}).get("id")) != str(team.espn_id):
                continue
            for event in group.get("events") or []:
                try:
                    ident = str(event["id"])
                    date = parse_iso(event["gameDate"])
                    hid, aid = str(event["homeTeamId"]), str(event["awayTeamId"])
                    hg, ag = float(event["homeTeamScore"]), float(event["awayTeamScore"])
                    if ident == str(match.provider_id) or not cutoff-timedelta(days=365) <= date < cutoff:
                        continue
                    if str(team.espn_id) not in (hid, aid) or not all(math.isfinite(v) and v >= 0 and v.is_integer() for v in (hg, ag)):
                        continue
                    gf, ga = (hg, ag) if str(team.espn_id) == hid else (ag, hg)
                    rows[ident] = {"id": ident, "kickoff": kickoff_iso(date), "goals": int(gf), "goals_against": int(ga), "is_home": str(team.espn_id) == hid, "result": "W" if gf > ga else "L" if gf < ga else "D", "opponent": (event.get("opponent") or {}).get("displayName"), "competition": event.get("leagueName") or event.get("competitionName"), "source_url": f"https://www.espn.com/soccer/match/_/gameId/{ident}"}
                except (KeyError, TypeError, ValueError):
                    continue
        result[side] = sorted(rows.values(), key=lambda r:r["kickoff"], reverse=True)[:5]
    return result

def form_payload(match, side):
    history = (match.live_data or {}).get("global_history")
    if history is None: return None
    rows = history.get(side, [])
    n = len(rows)
    return {"matches_used": n, "form_string": "-".join({"W":"V","D":"E","L":"D"}[r["result"]] for r in rows), "points": sum(3 if r["result"] == "W" else 1 if r["result"] == "D" else 0 for r in rows), "gf_avg": sum(r["goals"] for r in rows)/n if n else None, "ga_avg": sum(r["goals_against"] for r in rows)/n if n else None, "xg_avg": None, "xga_avg": None, "attack_index": None, "defense_index": None, "breakdown": {"slices": rows, "notice": NOTICE}}

def build_prediction(db, match):
    if match.status != "SCHEDULED" or aware(match.kickoff) <= utcnow(): return False
    history = (match.live_data or {}).get("global_history") or {}
    h, a = history.get("home", []), history.get("away", [])
    if len(h) != 5 or len(a) != 5: return False
    def rate(rows, field): return (sum(r[field] for r in rows)+5*1.25)/10
    lh = min(3.8,max(.2,math.sqrt(rate(h,"goals")*rate(a,"goals_against"))*1.06))
    la = min(3.8,max(.2,math.sqrt(rate(a,"goals")*rate(h,"goals_against"))/1.06))
    ph,pd,pa,over = poisson_grid(lh,la)
    pred = db.query(Prediction).filter_by(match_id=match.id).first()
    if pred is None:
        pred = Prediction(match_id=match.id)
        db.add(pred)
    pred.p_home,pred.p_draw,pred.p_away = ph,pd,pa
    pred.p_over_25,pred.p_under_25 = over,1-over
    pred.lambda_home,pred.lambda_away = lh,la
    pred.confidence,pred.confidence_label = .35,"BAJA"
    pred.pick = max(((ph,"LOCAL"),(pd,"EMPATE"),(pa,"VISITANTE")))[1]
    pred.model_version,pred.computed_at = VERSION,utcnow()
    pred.explanation = {"notice": NOTICE, "history_scope": "cross_competition", "home_history": h, "away_history": a, "smoothing": "5 partidos de prior a 1.25 goles; factor local 1.06; Poisson Dixon-Coles"}
    db.flush()
    return True


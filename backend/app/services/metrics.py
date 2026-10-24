"""Evaluación descriptiva de pronósticos guardados antes del inicio del partido.

No reentrena ni reconstruye predicciones con resultados ya conocidos.
"""

import math
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.etl.calendar import aware
from app.infrastructure.db.models import League, Match, Prediction, TeamFormSnapshot, ForecastSnapshot, ForecastRevision

LABELS = ["LOCAL", "EMPATE", "VISITANTE"]


def classification_metrics(samples: list[tuple[int, list[float]]]) -> dict:
    """Brier multiclase sin dividir por clases: rango [0, 2]."""
    matrix = [[0] * 3 for _ in LABELS]
    loss = brier = 0.0
    for actual, probs in samples:
        predicted = max(range(3), key=lambda i: probs[i])
        matrix[actual][predicted] += 1
        loss -= math.log(max(probs[actual], 1e-15))
        brier += sum((p - int(i == actual)) ** 2 for i, p in enumerate(probs))
    n = len(samples)
    per_class = []
    for i, label in enumerate(LABELS):
        tp = matrix[i][i]
        support = sum(matrix[i])
        predicted = sum(row[i] for row in matrix)
        precision = tp / predicted if predicted else 0.0
        recall = tp / support if support else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class.append(dict(label=label, support=support, precision=precision, recall=recall, f1=f1))
    return {
        "samples": n,
        "accuracy": sum(matrix[i][i] for i in range(3)) / n if n else None,
        "macro_f1": sum(c["f1"] for c in per_class) / 3 if n else None,
        "log_loss": loss / n if n else None,
        "brier": brier / n if n else None,
        "uniform_log_loss": math.log(3) if n else None,
        "uniform_brier": 2 / 3 if n else None,
        "confusion_matrix": matrix,
        "per_class": per_class,
    }


def knowledge_metrics(db: Session, league_code="ALL") -> dict:
    finished = db.query(Match).filter(
        Match.status == "FINISHED", Match.external_id.isnot(None),
        Match.is_h2h_only.is_(False),
        Match.provider == "espn", Match.verified_at.isnot(None),
    )
    if league_code != "ALL":
        finished=finished.join(League,League.id==Match.league_id).filter(League.code==league_code)
    completed = finished.count()
    with_scores = finished.filter(Match.home_goals >= 0, Match.away_goals >= 0).count()
    rows = finished.join(Prediction).with_entities(Match, Prediction).all()
    skipped = Counter()
    samples = []
    versions = Counter()
    for match, pred in rows:
        if pred.model_version.startswith("specialists-v2.0"):
            continue
        if (match.home_goals is None or match.away_goals is None
                or match.home_goals < 0 or match.away_goals < 0):
            skipped["missing_or_invalid_score"] += 1
            continue
        if aware(pred.computed_at) >= aware(match.kickoff):
            skipped["computed_after_kickoff"] += 1
            continue
        probs = [pred.p_home, pred.p_draw, pred.p_away]
        if (any(p is None or not math.isfinite(p) or not 0 <= p <= 1 for p in probs)
                or not math.isclose(sum(probs), 1, abs_tol=0.001)):
            skipped["invalid_probabilities"] += 1
            continue
        actual = 0 if match.home_goals > match.away_goals else 2 if match.home_goals < match.away_goals else 1
        # Corrige únicamente la tolerancia de redondeo de almacenamiento.
        samples.append((actual, [p / sum(probs) for p in probs]))
        versions[pred.model_version] += 1
    evaluation = classification_metrics(samples)
    legacy_evaluation = None
    from app.core.config import get_settings
    from app.services.market_pipeline import SCHEMA, deployment
    if get_settings().forecast_architecture == SCHEMA:
        legacy_evaluation = {**evaluation,"model_versions":dict(versions),"architecture":"legacy-v1","notice":"Historial anterior: no entrena ni calibra v2."}
        samples=[];versions=Counter();seen=set();skipped=Counter()
        signature=deployment(db)
        snapshots_query=db.query(ForecastSnapshot,Match).join(Match,Match.id==ForecastSnapshot.match_id).filter(ForecastSnapshot.phase=="PRE",ForecastSnapshot.evaluated_at.isnot(None),Match.provider=="espn").order_by(ForecastSnapshot.created_at,ForecastSnapshot.id)
        if league_code!="ALL":snapshots_query=snapshots_query.join(League,League.id==Match.league_id).filter(League.code==league_code)
        for snap,match in snapshots_query.all():
            if snap.match_id in seen or snap.payload.get("architecture")!=SCHEMA or not snap.outcomes or "void" in snap.outcomes:continue
            rev=db.get(ForecastRevision,snap.revision_id)
            if not rev or rev.report.get("deployment")!=signature:continue
            if aware(snap.created_at)>=aware(match.kickoff):continue
            choices=snap.payload.get("markets",{}).get("result",{}).get("choices",{})
            probs=[choices.get(k) for k in LABELS]
            if any(p is None or not math.isfinite(p) or not 0<=p<=1 for p in probs) or not math.isclose(sum(probs),1,abs_tol=.001):continue
            actual=snap.outcomes.get("result")
            if actual not in (0,1,2):continue
            seen.add(snap.match_id);samples.append((actual,probs));versions[snap.payload["model_version"]]+=1
        evaluation={**classification_metrics(samples),"architecture":SCHEMA,"scope":"Solo previos prospectivos del despliegue v2 actual; versiones anteriores separadas."}
    snapshot_query = db.query(TeamFormSnapshot).join(Match, Match.id == TeamFormSnapshot.as_of_match_id).filter(Match.provider == "espn", Match.verified_at.isnot(None))
    if league_code != "ALL":
        snapshot_query=snapshot_query.join(League,League.id==Match.league_id).filter(League.code==league_code)
    snapshots = snapshot_query.count()
    full = snapshot_query.filter(TeamFormSnapshot.matches_used == 5).count()
    duplicate_query = db.query(Match.external_id).filter(Match.external_id.isnot(None), Match.provider == "espn", Match.verified_at.isnot(None))
    if league_code != "ALL":
        duplicate_query=duplicate_query.join(League,League.id==Match.league_id).filter(League.code==league_code)
    duplicate_groups = duplicate_query.group_by(
        Match.external_id
    ).having(func.count(Match.id) > 1).count()
    evaluation.update({
        "status": "sin_evidencia" if not samples else "muestra_pequena" if len(samples) < 30 else "disponible",
        "excluded": dict(skipped),
        "model_versions": dict(versions),
        "coverage": len(samples) / completed if completed else None,
    })
    return {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "evaluation": evaluation,
        "legacy_evaluation": legacy_evaluation,
        "quality": {
            "finished_matches": completed,
            "score_completeness": with_scores / completed if completed else None,
            "form_snapshots": snapshots,
            "full_last5_ratio": full / snapshots if snapshots else None,
            "duplicate_external_id_groups": duplicate_groups,
        },
        "limitations": [
            "Solo se evalúan partidos oficiales finalizados con pronóstico guardado antes del inicio.",
            "La evaluación agrupa las versiones indicadas; no es una validación temporal de entrenamiento.",
            "Menos de 30 casos se señala como muestra pequeña; superar ese número no garantiza validez estadística.",
            "Las columnas heredadas pueden contener valores imputados; v2 no los utiliza como estadísticas observadas ni como variables de entrenamiento.",
            "El seguimiento actual conserva los pronósticos; la evaluación excluye los datos antiguos sin verificación de fuente.",
            "La confianza del motor es heurística y no equivale a una probabilidad de acierto calibrada.",
        ],
    }

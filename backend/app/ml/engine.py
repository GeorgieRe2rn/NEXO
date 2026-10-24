"""Motor de predicción FORMA v1.

Usa ÚNICAMENTE la forma de los últimos 5 partidos de cada equipo.

Dos capas interpretables (adecuadas a extracción de conocimiento):
1. Poisson (Dixon-Coles ligero) → 1X2 y Over/Under 2.5
2. Softmax con pesos iniciales manuales sobre features last-5 → combina el 1X2

No se consultan tablas de clasificación ni históricos de temporada.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from sklearn.linear_model import LogisticRegression

from app.ml.form import TeamForm

MODEL_VERSION = "forma-l5-v1.1"
MAX_GOALS = 8

# Coeficientes manuales de dominio. La calibración de mercados no reentrena esta matriz.
# Features: [bias, pts_diff/15, gf_diff, ga_diff_inv, xg_diff, sot_diff/5, poss_diff/40, venue]
# Clases: 0=away, 1=draw, 2=home
_PRIOR_COEF = np.array(
    [
        [-0.15, -1.55, -0.42, -0.38, -0.36, -0.22, -0.18, -0.55],  # away
        [0.22, -0.15, -0.05, -0.04, -0.06, -0.02, -0.01, -0.08],  # draw
        [-0.07, 1.70, 0.47, 0.42, 0.42, 0.24, 0.19, 0.63],  # home
    ]
)


@dataclass
class PredictionResult:
    p_home: float
    p_draw: float
    p_away: float
    p_over_25: float
    p_under_25: float
    lambda_home: float
    lambda_away: float
    confidence: float
    confidence_label: str
    pick: str
    model_version: str
    explanation: dict


def _poisson(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(k * math.log(lam) - lam - math.lgamma(k + 1))


def _dixon_coles_tau(i: int, j: int, lam_h: float, lam_a: float, rho: float = -0.08) -> float:
    if i == 0 and j == 0:
        return 1 - lam_h * lam_a * rho
    if i == 0 and j == 1:
        return 1 + lam_h * rho
    if i == 1 and j == 0:
        return 1 + lam_a * rho
    if i == 1 and j == 1:
        return 1 - rho
    return 1.0


def poisson_grid(lam_h: float, lam_a: float) -> tuple[float, float, float, float]:
    p_home = p_draw = p_away = p_over = 0.0
    for i in range(MAX_GOALS + 1):
        pi = _poisson(i, lam_h)
        for j in range(MAX_GOALS + 1):
            p = pi * _poisson(j, lam_a) * _dixon_coles_tau(i, j, lam_h, lam_a)
            if i > j:
                p_home += p
            elif i == j:
                p_draw += p
            else:
                p_away += p
            if i + j >= 3:
                p_over += p
    total = p_home + p_draw + p_away
    if total <= 0:
        return 0.34, 0.32, 0.34, 0.5
    return p_home / total, p_draw / total, p_away / total, p_over / total


def _softmax(logits: np.ndarray) -> np.ndarray:
    z = logits - logits.max()
    e = np.exp(z)
    return e / e.sum()


def last5_features(home: TeamForm, away: TeamForm) -> np.ndarray:
    """Vector de conocimiento: diferencias de forma reciente, nada de tabla anual."""
    pts_diff = (home.points - away.points) / 15.0
    gf_diff = home.gf_avg - away.gf_avg
    ga_inv = away.ga_avg - home.ga_avg
    xg_diff = home.xg_avg - away.xg_avg
    sot_diff = (home.sot_avg - away.sot_avg) / 5.0
    poss_diff = (home.possession_avg - away.possession_avg) / 40.0
    venue = 1.0  # contexto del partido (localía), no histórico de temporada
    return np.array([1.0, pts_diff, gf_diff, ga_inv, xg_diff, sot_diff, poss_diff, venue])


def logistic_1x2(home: TeamForm, away: TeamForm, coef: np.ndarray | None = None) -> tuple[float, float, float]:
    x = last5_features(home, away)
    w = coef if coef is not None else _PRIOR_COEF
    logits = w @ x
    probs = _softmax(logits)
    return float(probs[2]), float(probs[1]), float(probs[0])


def blend(a: float, b: float, w: float) -> float:
    return (1 - w) * a + w * b


def lambdas(home: TeamForm, away: TeamForm) -> tuple[float, float]:
    """λ de goles esperados a partir de ataque/defensa de los últimos 5."""
    mu = 1.32
    # Ligero factor de localía (contexto del evento, no tabla).
    venue = 1.07
    lam_h = mu * home.attack_index * away.defense_index * venue
    lam_a = mu * away.attack_index * home.defense_index * 0.95
    return max(0.35, min(3.6, lam_h)), max(0.30, min(3.4, lam_a))


def _confidence(home: TeamForm, away: TeamForm, p_home: float, p_draw: float, p_away: float) -> tuple[float, str]:
    ranked = sorted([p_home, p_draw, p_away], reverse=True)
    gap = ranked[0] - ranked[1]
    completeness = (home.matches_used + away.matches_used) / 10.0
    stability = (home.consistency + away.consistency) / 2.0
    score = 0.42 * gap + 0.33 * completeness + 0.25 * stability
    score = max(0.18, min(0.96, score))
    if score >= 0.62:
        label = "ALTA"
    elif score >= 0.42:
        label = "MEDIA"
    else:
        label = "BAJA"
    return round(score, 3), label


def _pick(p_home: float, p_draw: float, p_away: float) -> str:
    best = max(p_home, p_draw, p_away)
    if best == p_home:
        return "LOCAL"
    if best == p_away:
        return "VISITANTE"
    return "EMPATE"


def predict_match(
    home: TeamForm,
    away: TeamForm,
    logistic_coef: np.ndarray | None = None,
) -> PredictionResult:
    lam_h, lam_a = lambdas(home, away)
    ph_p, pd_p, pa_p, p_over = poisson_grid(lam_h, lam_a)
    ph_l, pd_l, pa_l = logistic_1x2(home, away, logistic_coef)

    # Blend: Poisson aporta goles/O-U; logística calibra el 1X2 con features last-5.
    ph = blend(ph_p, ph_l, 0.42)
    pd = blend(pd_p, pd_l, 0.42)
    pa = blend(pa_p, pa_l, 0.42)
    total = ph + pd + pa
    ph, pd, pa = ph / total, pd / total, pa / total

    conf, label = _confidence(home, away, ph, pd, pa)
    pick = _pick(ph, pd, pa)

    return PredictionResult(
        p_home=round(ph, 4),
        p_draw=round(pd, 4),
        p_away=round(pa, 4),
        p_over_25=round(p_over, 4),
        p_under_25=round(1 - p_over, 4),
        lambda_home=round(lam_h, 3),
        lambda_away=round(lam_a, 3),
        confidence=conf,
        confidence_label=label,
        pick=pick,
        model_version=MODEL_VERSION,
        explanation={
            "home_form": home.form_string,
            "away_form": away.form_string,
            "home_gf_avg": home.gf_avg,
            "away_gf_avg": away.gf_avg,
            "home_ga_avg": home.ga_avg,
            "away_ga_avg": away.ga_avg,
            "home_xg_avg": home.xg_avg,
            "away_xg_avg": away.xg_avg,
            "home_attack": home.attack_index,
            "away_attack": away.attack_index,
            "home_defense": home.defense_index,
            "away_defense": away.defense_index,
            "poisson": {"p_home": round(ph_p, 4), "p_draw": round(pd_p, 4), "p_away": round(pa_p, 4)},
            "logistic": {"p_home": round(ph_l, 4), "p_draw": round(pd_l, 4), "p_away": round(pa_l, 4)},
            "features": last5_features(home, away).round(4).tolist(),
            "constraint": "last_5_matches_only",
        },
    )


def fit_logistic(X: np.ndarray, y: np.ndarray) -> np.ndarray | None:
    """Entrena logística multinomial si hay suficientes ventanas last-5 etiquetadas."""
    if X.shape[0] < 12 or len(set(y.tolist())) < 3:
        return None
    clf = LogisticRegression(
        solver="lbfgs",
        max_iter=400,
        C=0.85,
    )
    clf.fit(X[:, 1:], y)
    classes = list(clf.classes_)
    coef = np.zeros((3, X.shape[1]))
    for i, cls in enumerate([0, 1, 2]):
        if cls not in classes:
            continue
        k = classes.index(cls)
        coef[i, 0] = float(clf.intercept_[k])
        coef[i, 1:] = clf.coef_[k]
    return coef

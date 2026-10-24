"""Ingeniería de características a partir EXCLUSIVAMENTE de los últimos 5 partidos."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import mean, pstdev


@dataclass
class MatchSlice:
    opponent: str
    is_home: bool
    goals_for: int
    goals_against: int
    xg: float
    xga: float
    shots: int
    shots_on_target: int
    possession: float
    corners: int
    yellows: int
    reds: int
    result: str  # W D L
    kickoff: str


@dataclass
class TeamForm:
    team_id: int
    form_string: str
    matches_used: int
    points: int
    gf_avg: float
    ga_avg: float
    xg_avg: float
    xga_avg: float
    shots_avg: float
    sot_avg: float
    possession_avg: float
    corners_avg: float
    cards_avg: float
    attack_index: float
    defense_index: float
    gd_avg: float
    consistency: float
    slices: list[MatchSlice]

    def to_breakdown(self) -> dict:
        payload = asdict(self)
        payload["slices"] = [asdict(s) for s in self.slices]
        return payload


def estimate_xg(shots: int, shots_on_target: int, goals: int) -> float:
    """Proxy de xG cuando la API no lo entrega. No usa tablas de temporada."""
    raw = 0.07 * shots + 0.21 * shots_on_target
    return round(max(0.15, min(4.2, 0.72 * raw + 0.28 * goals)), 2)


def _avg(values: list[float]) -> float:
    return round(mean(values), 3) if values else 0.0


def compute_team_form(team_id: int, slices: list[MatchSlice]) -> TeamForm:
    """Agrega los últimos 5 (o menos si el equipo no tiene 5) en índices de forma."""
    used = slices[:5]
    n = len(used)
    if n == 0:
        return TeamForm(
            team_id=team_id,
            form_string="—",
            matches_used=0,
            points=0,
            gf_avg=0,
            ga_avg=0,
            xg_avg=0,
            xga_avg=0,
            shots_avg=0,
            sot_avg=0,
            possession_avg=50,
            corners_avg=0,
            cards_avg=0,
            attack_index=0.8,
            defense_index=1.2,
            gd_avg=0,
            consistency=0.3,
            slices=[],
        )

    results = [s.result for s in used]
    points = sum(3 if r == "W" else 1 if r == "D" else 0 for r in results)
    form_letters = {"W": "V", "D": "E", "L": "D"}
    gf = [s.goals_for for s in used]
    ga = [s.goals_against for s in used]
    xg = [s.xg for s in used]
    xga = [s.xga for s in used]
    shots = [s.shots for s in used]
    sot = [s.shots_on_target for s in used]
    poss = [s.possession for s in used]
    corners = [s.corners for s in used]
    cards = [s.yellows + 2 * s.reds for s in used]
    gd = [a - b for a, b in zip(gf, ga)]

    gf_avg, ga_avg = _avg(gf), _avg(ga)
    xg_avg, xga_avg = _avg(xg), _avg(xga)
    sot_avg = _avg(sot)

    # Índices relativos a una media de liga implícita (~1.35 goles).
    league_mu = 1.35
    attack_index = max(
        0.35,
        0.45 * (gf_avg / league_mu) + 0.35 * (xg_avg / league_mu) + 0.20 * (sot_avg / 4.4),
    )
    defense_index = max(
        0.35,
        0.55 * (ga_avg / league_mu) + 0.45 * (xga_avg / league_mu),
    )

    consistency = 1.0
    if n > 1:
        consistency = max(0.15, 1.0 - min(1.0, pstdev(gd) / 2.4))

    return TeamForm(
        team_id=team_id,
        form_string="-".join(form_letters.get(r, r) for r in results),
        matches_used=n,
        points=points,
        gf_avg=gf_avg,
        ga_avg=ga_avg,
        xg_avg=xg_avg,
        xga_avg=xga_avg,
        shots_avg=_avg(shots),
        sot_avg=sot_avg,
        possession_avg=_avg(poss),
        corners_avg=_avg(corners),
        cards_avg=_avg(cards),
        attack_index=round(attack_index, 3),
        defense_index=round(defense_index, 3),
        gd_avg=_avg(gd),
        consistency=round(consistency, 3),
        slices=used,
    )

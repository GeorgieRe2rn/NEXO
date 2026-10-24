from app.ml.engine import predict_match
from app.ml.form import MatchSlice, compute_team_form


def _slice(gf, ga, result, xg=None):
    xg = xg if xg is not None else gf * 0.9 + 0.3
    return MatchSlice(
        opponent="X",
        is_home=True,
        goals_for=gf,
        goals_against=ga,
        xg=xg,
        xga=ga * 0.9 + 0.2,
        shots=12 + gf,
        shots_on_target=4 + gf,
        possession=55,
        corners=5,
        yellows=1,
        reds=0,
        result=result,
        kickoff="2026-09-01T00:00:00Z",
    )


def test_hot_form_favours_home():
    home = compute_team_form(1, [_slice(3, 0, "W"), _slice(2, 1, "W"), _slice(2, 0, "W"), _slice(1, 1, "D"), _slice(3, 1, "W")])
    away = compute_team_form(2, [_slice(0, 2, "L"), _slice(1, 2, "L"), _slice(0, 1, "L"), _slice(1, 1, "D"), _slice(0, 3, "L")])
    pred = predict_match(home, away)
    assert pred.p_home > pred.p_away
    assert pred.p_home > 0.45
    assert 0.2 <= pred.p_over_25 <= 0.95
    assert pred.explanation["constraint"] == "last_5_matches_only"


def test_form_string_uses_only_five():
    slices = [_slice(1, 0, "W")] * 7
    form = compute_team_form(1, slices)
    assert form.matches_used == 5
    assert form.form_string == "V-V-V-V-V"
    assert form.points == 15

import math
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.infrastructure.db.models import League, Match, Prediction, Team
from app.infrastructure.db.session import Base
from app.services.metrics import classification_metrics, knowledge_metrics


def test_no_samples_are_not_zero_accuracy():
    result = classification_metrics([])
    assert result["accuracy"] is None
    assert result["log_loss"] is None


def test_perfect_predictions():
    result = classification_metrics([(0, [1, 0, 0]), (1, [0, 1, 0]), (2, [0, 0, 1])])
    assert result["accuracy"] == result["macro_f1"] == 1
    assert result["brier"] == result["log_loss"] == 0
    assert result["confusion_matrix"] == [[1, 0, 0], [0, 1, 0], [0, 0, 1]]


def test_uniform_and_wrong_probabilities():
    result = classification_metrics([(i, [1 / 3] * 3) for i in range(3)])
    assert result["log_loss"] == pytest.approx(math.log(3))
    assert result["brier"] == pytest.approx(2 / 3)
    wrong = classification_metrics([(0, [0, 0, 1])])
    assert wrong["brier"] == 2
    assert math.isfinite(wrong["log_loss"])
    assert wrong["confusion_matrix"][0][2] == 1


def test_database_excludes_late_invalid_and_unfinished_predictions():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        league = League(code="PL", name="Test", country="Test", season=2026)
        db.add(league)
        db.flush()
        teams = [Team(league_id=league.id, name=n, short_name=n, tla=n) for n in ("A", "B")]
        db.add_all(teams)
        db.flush()
        for i in range(6):
            match = Match(external_id=100 + i, league_id=league.id,
                          provider="espn", verified_at=now,
                          home_team_id=teams[0].id, away_team_id=teams[1].id,
                          kickoff=now, status="SCHEDULED" if i == 3 else "FINISHED",
                          home_goals=None if i == 4 else 2, away_goals=0)
            db.add(match)
            db.flush()
            db.add(Prediction(match_id=match.id, p_home=float("inf") if i == 2 else 0.8,
                              p_draw=0.1, p_away=0.1, p_over_25=0.5, p_under_25=0.5,
                              lambda_home=1, lambda_away=1, confidence=0.5,
                              confidence_label="MEDIA", pick="LOCAL", model_version="test",
                              explanation={}, computed_at=now if i == 1 else now - timedelta(hours=1)))
            if i == 5:
                match.is_h2h_only = True
        db.commit()
        result = knowledge_metrics(db)
        e = result["evaluation"]
        assert e["samples"] == 1
        assert e["accuracy"] == 1
        assert e["coverage"] == 0.25
        assert e["excluded"] == {"computed_after_kickoff": 1, "invalid_probabilities": 1, "missing_or_invalid_score": 1}
        assert e["model_versions"] == {"test": 1}
        assert result["quality"]["score_completeness"] == 0.75
    engine.dispose()

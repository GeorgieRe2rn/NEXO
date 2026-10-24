"""Capa de conocimiento: materializa forma last-5, jugador clave y predicciones."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.domain.identity import club_fits_league
from app.etl.calendar import is_visible_upcoming
from app.infrastructure.db.models import (
    League,
    Match,
    MatchStat,
    Player,
    PlayerFormSnapshot,
    PlayerMatchStat,
    Prediction,
    Team,
    TeamFormSnapshot,
)
from app.ml.engine import predict_match
from app.ml.form import MatchSlice, compute_team_form


def _league_match_query(db: Session, team_id: int, before: datetime):
    team = db.get(Team, team_id)
    league_id = team.league_id if team else None
    q = (
        db.query(Match)
        .join(MatchStat, MatchStat.match_id == Match.id)
        .filter(
            MatchStat.team_id == team_id,
            Match.status == "FINISHED",
            Match.is_h2h_only.is_(False),
            Match.external_id.isnot(None),
            Match.verified_at.isnot(None),
            Match.kickoff < before,
        )
    )
    if league_id is not None:
        q = q.filter(Match.league_id == league_id)
    return q, team


def _is_league_fixture(match: Match, team: Team | None) -> bool:
    if team is None or match.external_id is None:
        return False
    if match.league_id != team.league_id:
        return False
    home = match.home_team
    away = match.away_team
    if home is None or away is None:
        return False
    if home.league_id != team.league_id or away.league_id != team.league_id:
        return False
    league = match.league
    code = league.code if league else ""
    return club_fits_league(home.name, code) and club_fits_league(away.name, code)


def _team_slices(db: Session, team_id: int, before: datetime, limit: int = 5) -> list[MatchSlice]:
    q, team = _league_match_query(db, team_id, before)
    rows = q.order_by(desc(Match.kickoff)).limit(limit * 4).all()
    stats = []
    for match in rows:
        if not _is_league_fixture(match, team):
            continue
        st = next((s for s in match.stats if s.team_id == team_id), None)
        if st is None:
            continue
        stats.append((st, match))
        if len(stats) >= limit:
            break
    slices: list[MatchSlice] = []
    for st, match in stats:
        opp_id = match.away_team_id if match.home_team_id == team_id else match.home_team_id
        opp = match.away_team if match.home_team_id == team_id else match.home_team
        slices.append(
            MatchSlice(
                opponent=opp.short_name if opp else str(opp_id),
                is_home=match.home_team_id == team_id,
                goals_for=st.goals,
                goals_against=st.goals_against,
                xg=st.xg,
                xga=st.xga,
                shots=st.shots,
                shots_on_target=st.shots_on_target,
                possession=st.possession,
                corners=st.corners,
                yellows=st.yellows,
                reds=st.reds,
                result=st.result,
                kickoff=match.kickoff.isoformat(),
            )
        )
    return slices


def _key_players(db: Session, team_id: int, match_id: int, before: datetime) -> list[PlayerFormSnapshot]:
    q, team = _league_match_query(db, team_id, before)
    recent_match_ids = []
    for match in q.order_by(desc(Match.kickoff)).limit(20).all():
        if _is_league_fixture(match, team):
            recent_match_ids.append(match.id)
        if len(recent_match_ids) >= 5:
            break
    if not recent_match_ids:
        return []

    rows = (
        db.query(PlayerMatchStat)
        .filter(
            PlayerMatchStat.team_id == team_id,
            PlayerMatchStat.match_id.in_(recent_match_ids),
        )
        .all()
    )
    agg: dict[int, dict] = {}
    for r in rows:
        bucket = agg.setdefault(
            r.player_id,
            {
                "minutes": 0,
                "goals": 0,
                "assists": 0,
                "rating": [],
                "yellows": 0,
                "reds": 0,
                "shots": 0,
            },
        )
        bucket["minutes"] += r.minutes
        bucket["goals"] += r.goals
        bucket["assists"] += r.assists
        bucket["rating"].append(r.rating)
        bucket["yellows"] += r.yellows
        bucket["reds"] += r.reds
        bucket["shots"] += r.shots

    now = datetime.now(timezone.utc)
    snapshots: list[PlayerFormSnapshot] = []
    ranked: list[tuple[float, int]] = []
    for pid, b in agg.items():
        games = max(1, len(b["rating"]))
        rating_avg = sum(b["rating"]) / games
        score = (
            b["goals"] * 4.2
            + b["assists"] * 3.1
            + rating_avg * 1.15
            + b["minutes"] / 90 * 0.45
            + b["shots"] * 0.08
            - b["yellows"] * 0.35
            - b["reds"] * 1.2
        )
        ranked.append((score, pid))
        snapshots.append(
            PlayerFormSnapshot(
                player_id=pid,
                team_id=team_id,
                as_of_match_id=match_id,
                computed_at=now,
                minutes=b["minutes"],
                goals=b["goals"],
                assists=b["assists"],
                rating_avg=round(rating_avg, 2),
                yellows=b["yellows"],
                reds=b["reds"],
                shots=b["shots"],
                form_score=round(score, 3),
                is_key_player=False,
            )
        )
    if ranked:
        best = max(ranked)[1]
        for snap in snapshots:
            if snap.player_id == best:
                snap.is_key_player = True
    return snapshots


def rebuild_knowledge(db: Session) -> dict:
    candidates = (
        db.query(Match)
        .join(League)
        .filter(
            Match.status == "SCHEDULED",
            Match.kickoff > datetime.now(timezone.utc),
            Match.verified_at.isnot(None),
            Match.is_h2h_only.is_(False),
            Match.external_id.isnot(None),
            League.is_active.is_(True),
        )
        .all()
    )
    upcoming = []
    for match in candidates:
        if match.external_id is None:
            continue
        if not is_visible_upcoming(match.kickoff, match.status):
            continue
        home, away = match.home_team, match.away_team
        if not home or not away:
            continue
        if home.league_id != match.league_id or away.league_id != match.league_id:
            continue
        code = match.league.code if match.league else ""
        if not club_fits_league(home.name, code) or not club_fits_league(away.name, code):
            continue
        upcoming.append(match)
    now = datetime.now(timezone.utc)
    forms = preds = players = 0

    for match in upcoming:
        from app.services.competition_registry import EXTENDED_COMPETITIONS
        if match.league.code in EXTENDED_COMPETITIONS:
            from app.services.global_form import build_prediction
            if build_prediction(db,match): preds+=1
            continue
        db.query(TeamFormSnapshot).filter(TeamFormSnapshot.as_of_match_id == match.id).delete()
        db.query(PlayerFormSnapshot).filter(PlayerFormSnapshot.as_of_match_id == match.id).delete()
        db.query(Prediction).filter(Prediction.match_id == match.id).delete()

        home_form = compute_team_form(
            match.home_team_id, _team_slices(db, match.home_team_id, match.kickoff)
        )
        away_form = compute_team_form(
            match.away_team_id, _team_slices(db, match.away_team_id, match.kickoff)
        )

        for form in (home_form, away_form):
            db.add(
                TeamFormSnapshot(
                    team_id=form.team_id,
                    as_of_match_id=match.id,
                    computed_at=now,
                    form_string=form.form_string,
                    matches_used=form.matches_used,
                    points=form.points,
                    gf_avg=form.gf_avg,
                    ga_avg=form.ga_avg,
                    xg_avg=form.xg_avg,
                    xga_avg=form.xga_avg,
                    shots_avg=form.shots_avg,
                    sot_avg=form.sot_avg,
                    possession_avg=form.possession_avg,
                    corners_avg=form.corners_avg,
                    cards_avg=form.cards_avg,
                    attack_index=form.attack_index,
                    defense_index=form.defense_index,
                    breakdown=form.to_breakdown(),
                )
            )
            forms += 1

        for snap in _key_players(db, match.home_team_id, match.id, match.kickoff):
            db.add(snap)
            players += 1
        for snap in _key_players(db, match.away_team_id, match.id, match.kickoff):
            db.add(snap)
            players += 1

        if home_form.matches_used < 5 or away_form.matches_used < 5:
            continue
        result = predict_match(home_form, away_form)
        db.add(
            Prediction(
                match_id=match.id,
                p_home=result.p_home,
                p_draw=result.p_draw,
                p_away=result.p_away,
                p_over_25=result.p_over_25,
                p_under_25=result.p_under_25,
                lambda_home=result.lambda_home,
                lambda_away=result.lambda_away,
                confidence=result.confidence,
                confidence_label=result.confidence_label,
                pick=result.pick,
                model_version=result.model_version,
                explanation=result.explanation,
                computed_at=now,
            )
        )
        preds += 1

    db.commit()
    return {"form_snapshots": forms, "predictions": preds, "player_snapshots": players}


def h2h_matches(db: Session, home_id: int, away_id: int, limit: int = 3) -> list[Match]:
    home = db.get(Team, home_id)
    league_id = home.league_id if home else None
    q = db.query(Match).filter(
        Match.status == "FINISHED",
        Match.external_id.isnot(None),
        ((Match.home_team_id == home_id) & (Match.away_team_id == away_id))
        | ((Match.home_team_id == away_id) & (Match.away_team_id == home_id)),
    )
    if league_id is not None:
        q = q.filter(Match.league_id == league_id)
    return q.order_by(desc(Match.kickoff)).limit(limit).all()

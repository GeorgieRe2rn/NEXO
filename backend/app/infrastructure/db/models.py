from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

PG_JSON = JSON().with_variant(JSONB(), "postgresql")

from app.infrastructure.db.session import Base


class League(Base):
    __tablename__ = "leagues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(8), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    country: Mapped[str] = mapped_column(String(80))
    season: Mapped[int] = mapped_column(Integer)
    api_football_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    football_data_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    accent: Mapped[str] = mapped_column(String(16), default="#00E5A8")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    teams: Mapped[list["Team"]] = relationship(back_populates="league")
    matches: Mapped[list["Match"]] = relationship(back_populates="league")


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    espn_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"))
    name: Mapped[str] = mapped_column(String(120), index=True)
    short_name: Mapped[str] = mapped_column(String(40))
    tla: Mapped[str] = mapped_column(String(8))
    logo_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(80), nullable=True)
    stadium: Mapped[str | None] = mapped_column(String(120), nullable=True)
    primary_color: Mapped[str] = mapped_column(String(16), default="#00E5A8")
    secondary_color: Mapped[str] = mapped_column(String(16), default="#0D1526")
    founded: Mapped[int | None] = mapped_column(Integer, nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    club_colors: Mapped[str | None] = mapped_column(String(80), nullable=True)
    coach_name: Mapped[str | None] = mapped_column(String(120), nullable=True)

    league: Mapped[League] = relationship(back_populates="teams")
    players: Mapped[list["Player"]] = relationship(back_populates="team")


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    name: Mapped[str] = mapped_column(String(120))
    photo_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    position: Mapped[str] = mapped_column(String(8), default="MF")
    position_label: Mapped[str | None] = mapped_column(String(32), nullable=True)
    nationality: Mapped[str] = mapped_column(String(80), default="—")
    nationality_code: Mapped[str] = mapped_column(String(8), default="UN")
    date_of_birth: Mapped[str | None] = mapped_column(String(16), nullable=True)
    age: Mapped[int] = mapped_column(Integer, default=0)
    height_cm: Mapped[int] = mapped_column(Integer, default=0)
    weight_kg: Mapped[int] = mapped_column(Integer, default=0)
    preferred_foot: Mapped[str] = mapped_column(String(12), default="—")
    shirt_number: Mapped[int] = mapped_column(Integer, default=0)
    season_stats: Mapped[dict | None] = mapped_column(PG_JSON, nullable=True)
    injured: Mapped[bool] = mapped_column(Boolean, default=False)
    injury: Mapped[str | None] = mapped_column(String(160), nullable=True)

    team: Mapped[Team] = relationship(back_populates="players")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="admin")
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), index=True)
    ip: Mapped[str] = mapped_column(String(64), index=True)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"))
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    kickoff: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    matchday: Mapped[int | None] = mapped_column(Integer, nullable=True)
    venue: Mapped[str | None] = mapped_column(String(160), nullable=True)
    home_goals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_goals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_h2h_only: Mapped[bool] = mapped_column(Boolean, default=False)
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    live_data: Mapped[dict | None] = mapped_column(PG_JSON, nullable=True)

    league: Mapped[League] = relationship(back_populates="matches")
    home_team: Mapped[Team] = relationship(foreign_keys=[home_team_id])
    away_team: Mapped[Team] = relationship(foreign_keys=[away_team_id])
    stats: Mapped[list["MatchStat"]] = relationship(back_populates="match", cascade="all, delete-orphan")
    player_stats: Mapped[list["PlayerMatchStat"]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )
    prediction: Mapped["Prediction | None"] = relationship(back_populates="match", uselist=False)


class MatchStat(Base):
    __tablename__ = "match_stats"
    __table_args__ = (UniqueConstraint("match_id", "team_id", name="uq_match_team_stat"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    goals: Mapped[int] = mapped_column(Integer, default=0)
    goals_against: Mapped[int] = mapped_column(Integer, default=0)
    xg: Mapped[float] = mapped_column(Float, default=0)
    xga: Mapped[float] = mapped_column(Float, default=0)
    shots: Mapped[int] = mapped_column(Integer, default=0)
    shots_on_target: Mapped[int] = mapped_column(Integer, default=0)
    possession: Mapped[float] = mapped_column(Float, default=50)
    corners: Mapped[int] = mapped_column(Integer, default=0)
    yellows: Mapped[int] = mapped_column(Integer, default=0)
    reds: Mapped[int] = mapped_column(Integer, default=0)
    fouls: Mapped[int] = mapped_column(Integer, default=0)
    result: Mapped[str] = mapped_column(String(1))  # W D L from this team's view

    match: Mapped[Match] = relationship(back_populates="stats")
    team: Mapped[Team] = relationship()


class PlayerMatchStat(Base):
    __tablename__ = "player_match_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    minutes: Mapped[int] = mapped_column(Integer, default=0)
    goals: Mapped[int] = mapped_column(Integer, default=0)
    assists: Mapped[int] = mapped_column(Integer, default=0)
    rating: Mapped[float] = mapped_column(Float, default=6.5)
    shots: Mapped[int] = mapped_column(Integer, default=0)
    shots_on_target: Mapped[int] = mapped_column(Integer, default=0)
    key_passes: Mapped[int] = mapped_column(Integer, default=0)
    yellows: Mapped[int] = mapped_column(Integer, default=0)
    reds: Mapped[int] = mapped_column(Integer, default=0)

    match: Mapped[Match] = relationship(back_populates="player_stats")
    player: Mapped[Player] = relationship()


class TeamFormSnapshot(Base):
    """Conocimiento extraído: forma de un equipo en sus últimos 5 partidos."""

    __tablename__ = "team_form_snapshots"
    __table_args__ = (UniqueConstraint("team_id", "as_of_match_id", name="uq_form_team_match"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    as_of_match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    form_string: Mapped[str] = mapped_column(String(16))
    matches_used: Mapped[int] = mapped_column(Integer)
    points: Mapped[int] = mapped_column(Integer)
    gf_avg: Mapped[float] = mapped_column(Float)
    ga_avg: Mapped[float] = mapped_column(Float)
    xg_avg: Mapped[float] = mapped_column(Float)
    xga_avg: Mapped[float] = mapped_column(Float)
    shots_avg: Mapped[float] = mapped_column(Float)
    sot_avg: Mapped[float] = mapped_column(Float)
    possession_avg: Mapped[float] = mapped_column(Float)
    corners_avg: Mapped[float] = mapped_column(Float)
    cards_avg: Mapped[float] = mapped_column(Float)
    attack_index: Mapped[float] = mapped_column(Float)
    defense_index: Mapped[float] = mapped_column(Float)
    breakdown: Mapped[dict] = mapped_column(PG_JSON)

    team: Mapped[Team] = relationship()


class PlayerFormSnapshot(Base):
    """Conocimiento extraído: rendimiento reciente del jugador clave."""

    __tablename__ = "player_form_snapshots"
    __table_args__ = (UniqueConstraint("player_id", "as_of_match_id", name="uq_pform_player_match"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    as_of_match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    minutes: Mapped[int] = mapped_column(Integer)
    goals: Mapped[int] = mapped_column(Integer)
    assists: Mapped[int] = mapped_column(Integer)
    rating_avg: Mapped[float] = mapped_column(Float)
    yellows: Mapped[int] = mapped_column(Integer)
    reds: Mapped[int] = mapped_column(Integer)
    shots: Mapped[int] = mapped_column(Integer)
    form_score: Mapped[float] = mapped_column(Float)
    is_key_player: Mapped[bool] = mapped_column(Boolean, default=False)

    player: Mapped[Player] = relationship()


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), unique=True)
    p_home: Mapped[float] = mapped_column(Float)
    p_draw: Mapped[float] = mapped_column(Float)
    p_away: Mapped[float] = mapped_column(Float)
    p_over_25: Mapped[float] = mapped_column(Float)
    p_under_25: Mapped[float] = mapped_column(Float)
    lambda_home: Mapped[float] = mapped_column(Float)
    lambda_away: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    confidence_label: Mapped[str] = mapped_column(String(12))
    pick: Mapped[str] = mapped_column(String(16))
    model_version: Mapped[str] = mapped_column(String(32), default="forma-l5-v1")
    explanation: Mapped[dict] = mapped_column(PG_JSON)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    match: Mapped[Match] = relationship(back_populates="prediction")


class ApiCache(Base):
    __tablename__ = "api_cache"

    cache_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), index=True)
    endpoint: Mapped[str] = mapped_column(String(255))
    payload: Mapped[dict] = mapped_column(PG_JSON)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    hit_count: Mapped[int] = mapped_column(Integer, default=0)


class EtlRun(Base):
    __tablename__ = "etl_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(16))
    requests_made: Mapped[int] = mapped_column(Integer, default=0)
    cache_hits: Mapped[int] = mapped_column(Integer, default=0)
    rows_upserted: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class FeedState(Base):
    __tablename__ = "feed_states"

    code: Mapped[str] = mapped_column(String(8), primary_key=True)
    attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    succeeded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    calendar_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    message: Mapped[str | None] = mapped_column(String(255), nullable=True)


class MarketLearner(Base):
    __tablename__ = "market_learners"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market: Mapped[str] = mapped_column(String(16), index=True)
    phase: Mapped[str] = mapped_column(String(8), index=True)
    schema_version: Mapped[str] = mapped_column(String(48), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    adopted: Mapped[bool] = mapped_column(Boolean, default=False)
    dataset_digest: Mapped[str] = mapped_column(String(64), index=True)
    model_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    report: Mapped[dict] = mapped_column(PG_JSON)


class ShadowForecast(Base):
    __tablename__ = "shadow_forecasts"
    __table_args__ = (UniqueConstraint("match_id", "model_id", "phase", name="uq_shadow_match_model_phase"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("market_learners.id"), index=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("forecast_snapshots.id"))
    phase: Mapped[str] = mapped_column(String(8))
    market: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(PG_JSON)
    outcomes: Mapped[dict | None] = mapped_column(PG_JSON, nullable=True)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ForecastRevision(Base):
    __tablename__ = "forecast_revisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    adopted: Mapped[bool] = mapped_column(Boolean, default=False)
    parameters: Mapped[dict] = mapped_column(PG_JSON)
    report: Mapped[dict] = mapped_column(PG_JSON)
    dataset_digest: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)


class ForecastSnapshot(Base):
    __tablename__ = "forecast_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    phase: Mapped[str] = mapped_column(String(8), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    revision_id: Mapped[int] = mapped_column(ForeignKey("forecast_revisions.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(PG_JSON)
    outcomes: Mapped[dict | None] = mapped_column(PG_JSON, nullable=True)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ForecastSelection(Base):
    __tablename__ = "forecast_selections_v2"
    __table_args__ = (UniqueConstraint("user_id", "snapshot_id", "market", "line_key", name="uq_selection_user_snapshot_market_line"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("forecast_snapshots.id"), index=True)
    market: Mapped[str] = mapped_column(String(16))
    line_key: Mapped[float] = mapped_column(Float, default=-1.0)
    pick: Mapped[str] = mapped_column(String(12))
    probability: Mapped[float] = mapped_column(Float)
    policy_version: Mapped[str | None] = mapped_column(String(48), nullable=True)
    selection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    result_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    settlement_history: Mapped[list] = mapped_column(PG_JSON, default=list)


class AutomaticForecastLink(Base):
    __tablename__ = "automatic_forecast_links"
    __table_args__ = (UniqueConstraint("user_id", "match_id", "market", name="uq_auto_user_match_market"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    market: Mapped[str] = mapped_column(String(16))
    selection_id: Mapped[int] = mapped_column(ForeignKey("forecast_selections_v2.id"), unique=True)


class AutomaticSelectionRevision(Base):
    __tablename__ = "automatic_selection_revisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    selection_id: Mapped[int] = mapped_column(ForeignKey("forecast_selections_v2.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    previous: Mapped[dict] = mapped_column(PG_JSON)
    current: Mapped[dict] = mapped_column(PG_JSON)
    reason: Mapped[str] = mapped_column(Text)


class CountObservation(Base):
    """Contadores publicados; no modifica marcadores ni características del motor 1X2."""
    __tablename__ = "count_observations"
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True)
    home_corners: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_corners: Mapped[int | None] = mapped_column(Integer, nullable=True)
    home_yellows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_yellows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_url: Mapped[str] = mapped_column(String(255))


class OddsObservation(Base):
    __tablename__ = "odds_observations"
    __table_args__ = (UniqueConstraint("match_id", "captured_at", name="uq_odds_capture"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload: Mapped[dict] = mapped_column(PG_JSON)

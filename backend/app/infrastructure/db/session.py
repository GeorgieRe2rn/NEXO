from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def _sqlite_url() -> str:
    db_path = Path(__file__).resolve().parents[3] / "data" / "forma.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite+pysqlite:///{db_path.as_posix()}"


def _build_engine():
    settings = get_settings()
    url = settings.database_url
    if url.startswith("sqlite"):
        eng = create_engine(
            url,
            connect_args={"check_same_thread": False, "timeout": 30},
        )
        _enable_sqlite_wal(eng)
        return eng, url
    try:
        kwargs = {"pool_pre_ping": True, "pool_size": 8, "max_overflow": 4}
        if url.startswith("postgresql"):
            kwargs["connect_args"] = {"connect_timeout": 2}
        eng = create_engine(url, **kwargs)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        return eng, url
    except Exception:
        sqlite_url = _sqlite_url()
        eng = create_engine(
            sqlite_url,
            connect_args={"check_same_thread": False, "timeout": 30},
        )
        _enable_sqlite_wal(eng)
        return eng, sqlite_url


def _enable_sqlite_wal(eng) -> None:
    @event.listens_for(eng, "connect")
    def _on_connect(dbapi_conn, _connection_record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=8000")
        cur.close()


engine, ACTIVE_DATABASE_URL = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def migrate_schema() -> None:
    """Añade columnas nuevas sin borrar datos (SQLite / PostgreSQL)."""
    statements = [
        ("players", "date_of_birth", "VARCHAR(16)"),
        ("players", "position_label", "VARCHAR(32)"),
        ("teams", "founded", "INTEGER"),
        ("teams", "website", "VARCHAR(255)"),
        ("teams", "club_colors", "VARCHAR(80)"),
        ("teams", "coach_name", "VARCHAR(120)"),
        ("players", "injured", "BOOLEAN DEFAULT FALSE"),
        ("players", "injury", "VARCHAR(160)"),
        ("players", "season_stats", "TEXT"),
        ("leagues", "is_active", "BOOLEAN DEFAULT TRUE"),
        ("teams", "espn_id", "INTEGER"),
        ("matches", "provider", "VARCHAR(32)"),
        ("matches", "provider_id", "VARCHAR(64)"),
        ("matches", "verified_at", "TIMESTAMP"),
        ("matches", "live_data", "JSON"),
        ("forecast_selections_v2", "policy_version", "VARCHAR(48)"),
        ("forecast_selections_v2", "selection_reason", "TEXT"),
    ]
    with engine.begin() as conn:
        dialect = engine.dialect.name
        for table, column, coltype in statements:
            if dialect == "sqlite":
                rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
                existing = {r[1] for r in rows}
            else:
                rows = conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = :t"
                    ),
                    {"t": table},
                ).fetchall()
                existing = {r[0] for r in rows}
            if column not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}"))
                if table == "leagues" and column == "is_active":
                    conn.execute(text("UPDATE leagues SET is_active = TRUE WHERE is_active IS NULL"))


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def migrate_selection_lines() -> None:
    """Copia el registro anterior conservando su tabla original y sus líneas."""
    from sqlalchemy import MetaData, Table, inspect, select, func
    from app.infrastructure.db.models import ForecastSelection, ForecastSnapshot
    if not inspect(engine).has_table("forecast_selections"):
        return
    legacy = Table("forecast_selections", MetaData(), autoload_with=engine)
    target = ForecastSelection.__table__
    with engine.begin() as conn:
        if conn.scalar(select(func.count()).select_from(target)):
            return
        for record in conn.execute(select(legacy)).mappings():
            values = dict(record)
            payload = conn.scalar(select(ForecastSnapshot.payload).where(ForecastSnapshot.id == values["snapshot_id"]))
            values["line_key"] = payload["markets"][values["market"]].get("line", -1.0)
            conn.execute(target.insert().values(**values))

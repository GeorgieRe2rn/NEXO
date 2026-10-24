from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    app_secret: str = "change-me"
    app_name: str = "Nexo"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    session_hours: int = 720
    login_max_attempts: int = 5
    login_lock_minutes: int = 15
    admin_username: str = "velar.admin"

    database_url: str = "postgresql+psycopg://forma:forma_secret@localhost:5432/forma"

    data_source: Literal["seed", "live"] = "live"
    forecast_architecture: Literal["specialists-v2.0", "legacy-v1"] = "specialists-v2.0"

    api_football_key: str = ""
    api_football_host: str = "v3.football.api-sports.io"
    api_football_rapidapi: bool = False

    football_data_key: str = ""
    odds_api_key: str = ""

    cache_ttl_hours: int = 12
    etl_max_requests_per_min: int = 8

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def has_api_football(self) -> bool:
        return bool(self.api_football_key)

    @property
    def has_football_data(self) -> bool:
        return bool(self.football_data_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()

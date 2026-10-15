from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
RULES_CONFIG_DIR = BACKEND_DIR / "rules_config"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = "postgresql+psycopg://carteira:carteira@localhost:5432/carteira"
    database_url_test: str = "postgresql+psycopg://carteira:carteira@localhost:5432/carteira_test"
    # Only to create the database of a new profile (app.jobs.setup_profiles); the app never uses it
    postgres_superuser_password: str = ""
    # Independent portfolios, each in its own database: "eu:Eu,pai:Pai" (see app.core.profiles)
    profiles: str = ""
    discord_webhook_url: str = ""
    # Watchlist alert (price vs. SMA200): its own channel; empty → same channel as the daily report
    discord_watchlist_webhook_url: str = ""
    # Daily report: B3 business days, after the close (HH:MM, America/Sao_Paulo)
    report_time: str = "19:00"
    timezone: str = "America/Sao_Paulo"
    # Warn when a manual trade price is this far (fraction) from the day's close
    price_deviation_warning: float = 0.15


@lru_cache
def get_settings() -> Settings:
    return Settings()

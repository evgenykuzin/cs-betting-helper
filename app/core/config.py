"""
Centralised configuration via pydantic-settings.
Reads from .env automatically.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # --- OddsPapi ---
    oddspapi_api_key: str
    oddspapi_base_url: str = "https://api.oddspapi.io/v4"

    # --- Postgres ---
    database_url: str = "postgresql+asyncpg://cs_user:cs_password@localhost:5432/cs_betting"

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- Celery ---
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # --- Telegram ---
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # --- App ---
    debug: bool = False
    poll_interval_seconds: int = 300  # 5 min default

    # --- Analysis thresholds ---
    anomaly_drop_pct: float = 15.0       # steam move threshold %
    arbitrage_min_profit_pct: float = 1.0
    value_bet_threshold_pct: float = 5.0  # odds > market_avg by X%
    suspicious_drop_pct: float = 25.0
    suspicious_books_moved: int = 4

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()

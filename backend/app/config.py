import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.getenv("ENV_FILE", str(BASE_DIR.parent / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite:///./data/stock.db"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "dev-only-secret"
    access_token_expire_minutes: int = 720
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    inline_jobs: bool = False
    seed_on_startup: bool = True
    log_level: str = "INFO"

    # crawler knobs, kept here so ops can tune without touching spiders
    crawl_user_agent: str = "nepse-research-bot/0.1 (+contact: dev@example.com)"
    crawl_delay_seconds: float = 1.5
    crawl_max_pages_per_portal: int = 40

    @property
    def cors_origin_list(self):
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

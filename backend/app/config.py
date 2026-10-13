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

    # demo login accounts, created by the seed. Off in any real deployment: with
    # demo_mode false the seed skips these users and /api/auth/demo-accounts is a
    # 404. The passwords are read from the environment (DEMO_*_PASSWORD); the
    # fallbacks below are local-demo only and are documented in the README.
    demo_mode: bool = True
    demo_admin_email: str = "admin@demo.local"
    demo_admin_username: str = "admin"
    demo_admin_password: str = "admin123"
    demo_analyst_email: str = "analyst@demo.local"
    demo_analyst_username: str = "analyst"
    demo_analyst_password: str = "analyst123"
    demo_viewer_email: str = "viewer@demo.local"
    demo_viewer_username: str = "viewer"
    demo_viewer_password: str = "viewer123"

    # crawler knobs, kept here so ops can tune without touching spiders. These
    # are handed to the spider subprocess as scrapy settings by tasks/crawl.py.
    crawl_user_agent: str = "nepse-research-bot/0.1 (+contact: dev@example.com)"
    crawl_delay_seconds: float = 1.5
    crawl_max_pages_per_portal: int = 40
    # per-portal download-delay overrides; set as JSON, e.g.
    # CRAWL_PORTAL_DELAYS='{"sharesansar": 3.0}'. Anything unlisted falls back
    # to crawl_delay_seconds, so this is the per-portal rate-limit knob.
    crawl_portal_delays: dict[str, float] = {}

    # robust-z threshold for the volume-anomaly alert
    volume_anomaly_z: float = 3.5
    volume_anomaly_lookback: int = 20

    @property
    def cors_origin_list(self):
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def crawl_delay_for(self, portal: str) -> float:
        """Download delay for one portal, honouring per-portal overrides."""
        return float(self.crawl_portal_delays.get(portal, self.crawl_delay_seconds))

    @property
    def demo_accounts(self) -> list[dict]:
        """The three seeded accounts, in role order (admin, analyst, viewer)."""
        return [
            {
                "email": self.demo_admin_email,
                "username": self.demo_admin_username,
                "role": "admin",
                "password": self.demo_admin_password,
            },
            {
                "email": self.demo_analyst_email,
                "username": self.demo_analyst_username,
                "role": "analyst",
                "password": self.demo_analyst_password,
            },
            {
                "email": self.demo_viewer_email,
                "username": self.demo_viewer_username,
                "role": "viewer",
                "password": self.demo_viewer_password,
            },
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

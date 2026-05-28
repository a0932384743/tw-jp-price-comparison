from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str = ""
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/twjp_prices"
    app_env: str = "development"
    app_port: int = 8000

    @model_validator(mode="after")
    def _fix_database_url(self) -> "Settings":
        # Render (and many PaaS) provide postgresql:// — asyncpg needs postgresql+asyncpg://
        url = self.database_url
        if url.startswith("postgresql://") and "+asyncpg" not in url:
            self.database_url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return self

    # Exchange rate used when no live source is configured
    jpy_to_twd_rate: float = 0.218

    # Politeness delay between scraper HTTP requests (seconds)
    scraper_request_delay: float = 1.5

    # Japan tax-free refund rate applied for physical JP shopping
    jp_tax_free_rate: float = 0.10


@lru_cache
def get_settings() -> Settings:
    return Settings()

from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/twjp_prices"
    app_env: str = "development"
    app_port: int = 8000

    # Exchange rate used when no live source is configured
    jpy_to_twd_rate: float = 0.218

    # Politeness delay between scraper HTTP requests (seconds)
    scraper_request_delay: float = 1.5

    # Japan tax-free refund rate applied for physical JP shopping
    jp_tax_free_rate: float = 0.10


@lru_cache
def get_settings() -> Settings:
    return Settings()

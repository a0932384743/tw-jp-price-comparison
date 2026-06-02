from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str = ""

    # Firebase Admin SDK – paste the full service account JSON as one line
    firebase_service_account_json: str = ""
    firebase_project_id: str = "adjoined-b367d"

    app_env: str = "development"
    app_port: int = 8000

    # Exchange rate used when live fetch fails
    jpy_to_twd_rate: float = 0.218

    # Politeness delay between scraper HTTP requests (seconds)
    scraper_request_delay: float = 1.5

    # Japan tax-free refund rate applied for physical JP shopping
    jp_tax_free_rate: float = 0.10

    # Optional: Rakuten Ichiba API (free – register at https://webservice.rakuten.co.jp/)
    rakuten_app_id: str = ""

    # Optional: Yahoo Shopping JP API (free – register at https://developer.yahoo.co.jp/)
    yahoo_jp_app_id: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()

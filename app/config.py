from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    keitaro_url: str = "https://tlgk.host"
    keitaro_api_key: str = ""
    keitaro_timeout: float = 30.0

    database_url: str = "sqlite:///./app.db"

    # URL that stream #1 (geo filter) redirects to.
    geo_redirect_url: str = "https://www.google.com"

    # Optional defaults pre-selected in the "create campaign" form.
    default_group_id: int | None = None
    default_domain_id: int | None = None
    default_traffic_source_id: int | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()

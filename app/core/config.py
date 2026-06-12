from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    app_name: str = "Stock Discovery GPT API"
    environment: str = "development"
    fmp_api_key: str | None = None
    fmp_base_url: str = "https://financialmodelingprep.com/api/v3"
    fmp_timeout_seconds: float = 15
    fmp_statement_limit: int = 2
    market_snapshot_reliability_basic: float = 0.48
    market_snapshot_reliability_valuation: float = 0.66
    market_snapshot_reliability_financials: float = 0.82
    dart_api_key: str | None = None
    action_api_bearer_token: str | None = None
    stock_data_gateway_url: str = "https://stock-data-gateway.onrender.com"
    stock_data_gateway_bearer_token: str | None = None
    cors_allow_origins: list[str] = ["*"]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()

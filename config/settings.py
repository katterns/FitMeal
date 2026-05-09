from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "FitMeal AI"
    app_version: str = "0.1.0"

    database_url: str = "sqlite:///./fitmeal.db"
    redis_url: str = "redis://localhost:6379/0"
    celery_task_always_eager: bool = False

    jwt_secret_key: str = "change-me-in-env"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24

    models_dir: str = "models"
    basic_tariff_price: int = 5
    pro_tariff_price: int = 15
    mistral_api_key: str = ""
    mistral_model: str = "mistral-small-latest"
    mistral_base_url: str = "https://api.mistral.ai/v1"

    analysis_stale_reclaim_seconds: int = 600
    celery_analysis_soft_time_limit: int = 300
    celery_analysis_time_limit: int = 900

    admin_emails: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings():
    return Settings()

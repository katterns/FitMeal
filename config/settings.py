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
    mistral_api_key: str | None = None
    mistral_model: str = "mistral-medium-latest"
    mistral_base_url: str = "https://api.mistral.ai/v1"

    admin_emails: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings():
    return Settings()

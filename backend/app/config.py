"""Application configuration loaded from environment variables."""
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    app_name: str = "AICSP"
    api_v1_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:5173"

    auth_secret: str = "insecure-dev-secret-change-me"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    jwt_algorithm: str = "HS256"

    database_url: str = "postgresql+psycopg://aicsp:aicsp@localhost:5432/aicsp"

    openai_api_key: str = ""
    openai_chat_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    rate_limit_per_minute: int = 60
    prompt_injection_threshold: float = 0.6

    seed_admin_email: str = "admin@example.com"
    seed_admin_password: str = "ChangeMe123!"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def has_openai_key(self) -> bool:
        return bool(self.openai_api_key) and self.openai_api_key != "sk-your-key-here"


@lru_cache
def get_settings() -> Settings:
    return Settings()

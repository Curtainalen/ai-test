from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore", case_sensitive=False)

    app_env: str = "development"
    app_name: str = "AI Test"
    api_prefix: str = "/api"
    log_level: str = "INFO"
    frontend_origin: str = "http://localhost:8080"
    database_url: str
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480
    upload_root: Path = Path("data/uploads")
    max_upload_bytes: int = 20 * 1024 * 1024
    max_pdf_pages: int = 200
    max_docx_images: int = 200
    document_parse_timeout_seconds: int = 120
    remote_openapi_enabled: bool = False
    remote_openapi_allowed_hosts: str = ""
    remote_openapi_max_bytes: int = 5 * 1024 * 1024
    remote_openapi_timeout_seconds: int = 10

    @field_validator("jwt_secret")
    @classmethod
    def validate_secret(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError("JWT_SECRET must contain at least 32 characters")
        return value

    @property
    def allowed_remote_hosts(self) -> set[str]:
        return {item.strip().lower() for item in self.remote_openapi_allowed_hosts.split(",") if item.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()

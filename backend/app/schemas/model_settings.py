from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, SecretStr, field_validator


def _validate_base_url(value: str | None) -> str | None:
    if value in (None, ""):
        return None
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("base_url must be an http(s) URL without credentials, query, or fragment")
    return value.rstrip("/")


class ModelConfigFields(BaseModel):
    provider: str = Field(default="custom", min_length=1, max_length=64)
    protocol: str = Field(min_length=1, max_length=32)
    model_name: str = Field(min_length=1, max_length=256)
    base_url: str | None = Field(default=None, max_length=2048)
    extra_params: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=120, ge=1, le=300)
    max_retries: int = Field(default=0, ge=0, le=5)
    context_window: int | None = Field(default=None, ge=128, le=2_000_000)
    supports_vision: bool = False
    supports_streaming: bool = True
    is_enabled: bool = True

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str | None) -> str | None:
        return _validate_base_url(value)


class ModelConfigCreate(ModelConfigFields):
    name: str = Field(min_length=1, max_length=64)
    api_key: SecretStr | None = Field(default=None, max_length=4096)
    is_default: bool = False


class ModelConfigUpdate(BaseModel):
    revision: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=64)
    provider: str | None = Field(default=None, min_length=1, max_length=64)
    protocol: str | None = Field(default=None, min_length=1, max_length=32)
    model_name: str | None = Field(default=None, min_length=1, max_length=256)
    base_url: str | None = Field(default=None, max_length=2048)
    extra_params: dict[str, Any] | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=300)
    max_retries: int | None = Field(default=None, ge=0, le=5)
    context_window: int | None = Field(default=None, ge=128, le=2_000_000)
    supports_vision: bool | None = None
    supports_streaming: bool | None = None
    is_enabled: bool | None = None
    api_key: SecretStr | None = Field(default=None, max_length=4096)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str | None) -> str | None:
        return _validate_base_url(value)


class ModelConfigProbeRequest(ModelConfigFields):
    api_key: SecretStr | None = Field(default=None, max_length=4096)


class DefaultConfigRequest(BaseModel):
    revision: int = Field(ge=1)


class ModelConfigView(BaseModel):
    id: str
    name: str
    provider: str
    protocol: str
    model_name: str
    base_url: str | None
    api_key_configured: bool
    api_key_hint: str
    extra_params: dict[str, Any]
    timeout_seconds: int
    max_retries: int
    context_window: int | None
    supports_vision: bool
    supports_streaming: bool
    is_default: bool
    is_enabled: bool
    revision: int
    created_by: str
    created_at: str | None = None
    updated_at: str | None = None

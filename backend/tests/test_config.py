import pytest
from pydantic import ValidationError

from app.config import Settings


def test_short_jwt_secret_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(jwt_secret="short")


def test_short_secret_key_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(jwt_secret="x" * 32, secret_key="short")


def test_remote_hosts_are_normalized() -> None:
    settings = Settings(jwt_secret="x" * 32, remote_openapi_allowed_hosts=" API.EXAMPLE.COM, docs.example.com ")
    assert settings.allowed_remote_hosts == {"api.example.com", "docs.example.com"}

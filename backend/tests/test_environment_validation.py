import pytest
from pydantic import ValidationError

from app.schemas.identity import EnvironmentCreate


def test_environment_accepts_service_base_path() -> None:
    environment = EnvironmentCreate(name="gateway", base_url="https://api.example.test/v1")
    assert environment.base_url == "https://api.example.test/v1"


@pytest.mark.parametrize("url", [
    "https://api.example.test/api-docs",
    "https://api.example.test/openapi.json",
    "https://api.example.test/swagger.yaml",
])
def test_environment_rejects_openapi_document_url(url: str) -> None:
    with pytest.raises(ValidationError, match="OpenAPI or Swagger document URL"):
        EnvironmentCreate(name="docs", base_url=url)

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=10, max_length=128)
    name: str = Field(default="", max_length=64)
    email: str = Field(default="", max_length=255)


class LoginRequest(BaseModel):
    username: str
    password: str


class UserCreate(RegisterRequest):
    system_role: Literal["admin", "user"] = "user"


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=2000)


class MemberCreate(BaseModel):
    username: str
    role: Literal["Admin", "Member"] = "Member"


class EnvironmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    base_url: str = Field(max_length=1024)
    variables: dict = Field(default_factory=dict)
    global_headers: dict = Field(default_factory=dict)
    secret_refs: dict = Field(default_factory=dict)
    is_enabled: bool = True

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        from urllib.parse import urlsplit

        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password or parts.fragment:
            raise ValueError("base_url must be an http(s) origin without credentials or fragment")
        return value.rstrip("/")

    @field_validator("secret_refs")
    @classmethod
    def validate_secret_refs(cls, value: dict) -> dict:
        for name, ref in value.items():
            if not isinstance(name, str) or not isinstance(ref, str) or not ref.startswith("secret://"):
                raise ValueError("secret_refs values must use secret://name")
        return value


class EnvironmentUpdate(EnvironmentCreate):
    revision: int = Field(ge=1)

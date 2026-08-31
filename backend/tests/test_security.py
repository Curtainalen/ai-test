import os

os.environ.setdefault("JWT_SECRET", "test-secret-that-is-at-least-32-characters")

from app.security import create_access_token, decode_access_token, hash_password, verify_password


def test_password_round_trip() -> None:
    encoded = hash_password("strong-password")
    assert "strong-password" not in encoded
    assert verify_password("strong-password", encoded)
    assert not verify_password("wrong-password", encoded)


def test_jwt_round_trip() -> None:
    assert decode_access_token(create_access_token("user-1")) == "user-1"

import os

os.environ.setdefault("JWT_SECRET", "test-secret-that-is-at-least-32-characters")

from app.security import create_access_token, decode_access_token, decrypt_secret, encrypt_secret, hash_password, mask_secret, verify_password


def test_password_round_trip() -> None:
    encoded = hash_password("strong-password")
    assert "strong-password" not in encoded
    assert verify_password("strong-password", encoded)
    assert not verify_password("wrong-password", encoded)


def test_jwt_round_trip() -> None:
    assert decode_access_token(create_access_token("user-1")) == "user-1"


def test_model_secret_is_encrypted_and_only_has_a_safe_hint() -> None:
    secret = "sk-" + "x" * 36 + "ab3f"
    encrypted = encrypt_secret(secret)
    assert encrypted != secret
    assert secret not in encrypted
    assert decrypt_secret(encrypted) == secret
    assert mask_secret(secret) == "sk-***ab3f"

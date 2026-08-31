import base64
import hashlib
import hmac
import os
from datetime import UTC, datetime, timedelta

import jwt
from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings
from app.errors import AppError

PBKDF2_ITERATIONS = 600_000


def _fernet() -> Fernet:
    """Derive the application Fernet key without persisting another key."""
    digest = hashlib.sha256(get_settings().secret_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str) -> str:
    if not value:
        return ""
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str) -> str:
    if not value:
        return ""
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError, ValueError, TypeError) as exc:
        raise AppError("SECRET_DECRYPTION_FAILED", "加密密钥无法解密，请联系系统管理员", 500) from exc


def mask_secret(value: str) -> str:
    """Return a stable non-reversible hint; never expose short secrets."""
    if len(value) <= 7:
        return "******" if value else ""
    return f"{value[:3]}***{value[-4:]}"


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_text, digest_text = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_text)
        expected = base64.b64decode(digest_text)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iterations))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: str) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    return jwt.encode({"sub": user_id, "iat": now, "exp": now + timedelta(minutes=settings.jwt_expire_minutes)}, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> str:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_id = payload.get("sub")
        if not user_id:
            raise ValueError("missing subject")
        return str(user_id)
    except (jwt.InvalidTokenError, ValueError) as exc:
        raise AppError("AUTH_INVALID_TOKEN", "登录状态无效或已过期", 401) from exc

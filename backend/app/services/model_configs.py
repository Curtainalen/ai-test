from __future__ import annotations

from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import SecretStr

from app.errors import AppError
from app.models import ModelConfig, User
from app.security import decrypt_secret, encrypt_secret, mask_secret
from app.services.llm_probe import validate_protocol

DEFAULT_MODEL_CONFIG_LOCK = 817_201_404


def require_admin(actor: User) -> None:
    if actor.system_role != "admin":
        raise AppError("AUTH_FORBIDDEN", "仅系统管理员可管理模型设置", 403)


def _secret_value(value: SecretStr | str | None) -> str:
    if isinstance(value, SecretStr):
        return value.get_secret_value()
    return value or ""


def view(row: ModelConfig) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "provider": row.provider,
        "protocol": row.protocol,
        "model_name": row.model_name,
        "base_url": row.base_url,
        "api_key_configured": bool(row.api_key_encrypted),
        "api_key_hint": row.api_key_hint,
        "extra_params": row.extra_params or {},
        "timeout_seconds": row.timeout_seconds,
        "max_retries": row.max_retries,
        "context_window": row.context_window,
        "supports_vision": row.supports_vision,
        "supports_streaming": row.supports_streaming,
        "is_default": row.is_default,
        "is_enabled": row.is_enabled,
        "revision": row.revision,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


async def _lock_default_switch(db: AsyncSession) -> None:
    await db.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": DEFAULT_MODEL_CONFIG_LOCK})


async def _make_default(db: AsyncSession, row: ModelConfig) -> None:
    await _lock_default_switch(db)
    await db.execute(update(ModelConfig).where(ModelConfig.is_default.is_(True), ModelConfig.id != row.id).values(is_default=False))
    row.is_default = True


async def list_all(db: AsyncSession, actor: User) -> list[dict]:
    require_admin(actor)
    rows = (await db.scalars(select(ModelConfig).order_by(ModelConfig.is_default.desc(), ModelConfig.created_at.desc()))).all()
    return [view(row) for row in rows]


async def get(db: AsyncSession, actor: User, config_id: str) -> ModelConfig:
    require_admin(actor)
    row = await db.scalar(select(ModelConfig).where(ModelConfig.id == config_id))
    if row is None:
        raise AppError("MODEL_CONFIG_NOT_FOUND", "模型配置不存在", 404)
    return row


async def create(db: AsyncSession, actor: User, data) -> ModelConfig:
    require_admin(actor)
    validate_protocol(data.protocol)
    api_key = _secret_value(data.api_key)
    row = ModelConfig(
        name=data.name,
        provider=data.provider,
        protocol=data.protocol,
        model_name=data.model_name,
        base_url=data.base_url,
        api_key_encrypted=encrypt_secret(api_key),
        api_key_hint=mask_secret(api_key),
        extra_params=data.extra_params,
        timeout_seconds=data.timeout_seconds,
        max_retries=data.max_retries,
        context_window=data.context_window,
        supports_vision=data.supports_vision,
        supports_streaming=data.supports_streaming,
        is_enabled=data.is_enabled,
        is_default=False,
        created_by=actor.id,
    )
    db.add(row)
    try:
        await db.flush()
        if data.is_default:
            await _make_default(db, row)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError("MODEL_CONFIG_NAME_EXISTS", "模型配置名称已存在", 409) from exc
    await db.refresh(row)
    return row


async def update_config(db: AsyncSession, actor: User, config_id: str, data) -> ModelConfig:
    row = await get(db, actor, config_id)
    if row.revision != data.revision:
        raise AppError("REVISION_CONFLICT", "模型配置已被其他用户修改", 409, {"current_revision": row.revision})
    changed = data.model_fields_set - {"revision", "api_key"}
    if "protocol" in changed:
        validate_protocol(data.protocol)
    for field in changed:
        setattr(row, field, getattr(data, field))
    if "api_key" in data.model_fields_set:
        api_key = _secret_value(data.api_key)
        if api_key:
            row.api_key_encrypted = encrypt_secret(api_key)
            row.api_key_hint = mask_secret(api_key)
    row.revision += 1
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError("MODEL_CONFIG_NAME_EXISTS", "模型配置名称已存在", 409) from exc
    await db.refresh(row)
    return row


async def set_default(db: AsyncSession, actor: User, config_id: str, revision: int) -> ModelConfig:
    row = await get(db, actor, config_id)
    if row.revision != revision:
        raise AppError("REVISION_CONFLICT", "模型配置已被其他用户修改", 409, {"current_revision": row.revision})
    if row.is_enabled is False:
        raise AppError("MODEL_CONFIG_DISABLED", "停用的模型配置不能设为默认", 422)
    await _make_default(db, row)
    row.revision += 1
    await db.commit()
    await db.refresh(row)
    return row


async def saved_probe_secret(db: AsyncSession, actor: User, config_id: str) -> tuple[ModelConfig, str]:
    row = await get(db, actor, config_id)
    if not row.is_enabled:
        raise AppError("MODEL_CONFIG_DISABLED", "模型配置已停用", 422)
    return row, decrypt_secret(row.api_key_encrypted)

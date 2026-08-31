from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, new_uuid


class ModelConfig(Base, TimestampMixin):
    __tablename__ = "model_configs"
    __table_args__ = (
        Index("uq_model_configs_default", "is_default", unique=True, postgresql_where=text("is_default")),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    provider: Mapped[str] = mapped_column(String(64), default="custom")
    protocol: Mapped[str] = mapped_column(String(32))
    model_name: Mapped[str] = mapped_column(String(256))
    base_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    api_key_encrypted: Mapped[str] = mapped_column(Text, default="")
    api_key_hint: Mapped[str] = mapped_column(String(32), default="")
    extra_params: Mapped[dict] = mapped_column(JSON, default=dict)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=30)
    max_retries: Mapped[int] = mapped_column(Integer, default=0)
    context_window: Mapped[int | None] = mapped_column(Integer, nullable=True)
    supports_vision: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_streaming: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)


class ModelConfigRevision(Base):
    __tablename__ = "model_config_revisions"
    __table_args__ = (UniqueConstraint("project_id", "model_config_id", "revision", name="uq_model_config_revision"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    model_config_id: Mapped[str] = mapped_column(ForeignKey("model_configs.id", ondelete="RESTRICT"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    config_snapshot: Mapped[dict] = mapped_column(JSON)
    api_key_encrypted: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class LlmCallRecord(Base):
    __tablename__ = "llm_call_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    model_config_id: Mapped[str] = mapped_column(ForeignKey("model_configs.id", ondelete="RESTRICT"), index=True)
    model_config_revision_id: Mapped[str] = mapped_column(ForeignKey("model_config_revisions.id", ondelete="RESTRICT"), index=True)
    purpose: Mapped[str] = mapped_column(String(64), default="generation", index=True)
    status: Mapped[str] = mapped_column(String(24), index=True)
    prompt_redacted: Mapped[str] = mapped_column(Text, default="")
    response_redacted: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    response_schema: Mapped[dict] = mapped_column(JSON)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    usage_unknown: Mapped[bool] = mapped_column(Boolean, default=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, Integer, JSON, String, Text, text
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

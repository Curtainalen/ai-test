from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, new_uuid


class RequirementDocument(Base, TimestampMixin):
    __tablename__ = "requirement_documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class DocumentVersion(Base, TimestampMixin):
    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("project_id", "sha256", name="uq_document_sha256"), UniqueConstraint("document_id", "version", name="uq_document_version"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("requirement_documents.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column()
    file_name: Mapped[str] = mapped_column(String(255))
    object_key: Mapped[str] = mapped_column(String(512))
    mime_type: Mapped[str] = mapped_column(String(128))
    file_size: Mapped[int] = mapped_column()
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    parse_status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class DocumentParseJob(Base, TimestampMixin):
    __tablename__ = "document_parse_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    document_version_id: Mapped[str] = mapped_column(ForeignKey("document_versions.id", ondelete="CASCADE"), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    progress: Mapped[int] = mapped_column(default=0)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)


class ContentBlock(Base):
    __tablename__ = "content_blocks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    document_version_id: Mapped[str] = mapped_column(ForeignKey("document_versions.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column()
    block_type: Mapped[str] = mapped_column(String(24))
    content: Mapped[str] = mapped_column(Text, default="")
    structured_content: Mapped[dict] = mapped_column(JSON, default=dict)
    source_locator: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    needs_correction: Mapped[bool] = mapped_column(Boolean, default=False)


class RequirementModule(Base, TimestampMixin):
    __tablename__ = "requirement_modules"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    document_version_id: Mapped[str] = mapped_column(ForeignKey("document_versions.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    source_block_ids: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), default="pending_confirmation", index=True)
    revision: Mapped[int] = mapped_column(default=1)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)


class ApiImport(Base, TimestampMixin):
    __tablename__ = "api_imports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    source_type: Mapped[str] = mapped_column(String(16), default="file")
    source_name: Mapped[str] = mapped_column(String(512))
    spec_version: Mapped[str] = mapped_column(String(32))
    raw_snapshot: Mapped[dict] = mapped_column(JSON)
    normalized_snapshot: Mapped[list] = mapped_column(JSON)
    diff: Mapped[dict] = mapped_column(JSON)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), default="pending_confirmation", index=True)
    revision: Mapped[int] = mapped_column(default=1)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class ApiModule(Base, TimestampMixin):
    __tablename__ = "api_modules"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_api_module_name"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    source: Mapped[str] = mapped_column(String(16), default="tag")
    revision: Mapped[int] = mapped_column(default=1)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class ApiInterface(Base, TimestampMixin):
    __tablename__ = "api_interfaces"
    __table_args__ = (UniqueConstraint("project_id", "stable_key", name="uq_api_interface_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    module_id: Mapped[str | None] = mapped_column(ForeignKey("api_modules.id", ondelete="SET NULL"), nullable=True, index=True)
    import_id: Mapped[str] = mapped_column(ForeignKey("api_imports.id", ondelete="RESTRICT"), index=True)
    stable_key: Mapped[str] = mapped_column(String(512))
    method: Mapped[str] = mapped_column(String(12))
    path: Mapped[str] = mapped_column(String(1024))
    summary: Mapped[str] = mapped_column(String(255), default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    parameters: Mapped[list] = mapped_column(JSON, default=list)
    request_body: Mapped[dict] = mapped_column(JSON, default=dict)
    responses: Mapped[dict] = mapped_column(JSON, default=dict)
    security: Mapped[list] = mapped_column(JSON, default=list)
    manual_config: Mapped[dict] = mapped_column(JSON, default=dict)
    imported_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    revision: Mapped[int] = mapped_column(default=1)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class DebugRun(Base, TimestampMixin):
    __tablename__ = "debug_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    interface_id: Mapped[str | None] = mapped_column(ForeignKey("api_interfaces.id", ondelete="SET NULL"), nullable=True)
    environment_id: Mapped[str] = mapped_column(ForeignKey("test_environments.id", ondelete="RESTRICT"))
    request_snapshot: Mapped[dict] = mapped_column(JSON)
    response_snapshot: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16))
    duration_ms: Mapped[int] = mapped_column()
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))

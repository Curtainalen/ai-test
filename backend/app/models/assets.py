from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
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
    # 新上传文件以密文落盘；该标记让旧版本明文文件可以兼容读取并逐步迁移。
    storage_encrypted: Mapped[bool] = mapped_column(Boolean, default=False)
    parse_status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 解析和业务确认是两个独立阶段：上传后先解析，解析结果经人工确认后才能拆分模块。
    content_status: Mapped[str] = mapped_column(String(24), default="pending_confirmation", index=True)
    content_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content_confirmed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    full_text: Mapped[str] = mapped_column(Text, default="")
    uploaded_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class DocumentImage(Base, TimestampMixin):
    __tablename__ = "document_images"
    __table_args__ = (UniqueConstraint("document_version_id", "image_id", name="uq_document_image_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    document_version_id: Mapped[str] = mapped_column(ForeignKey("document_versions.id", ondelete="CASCADE"), index=True)
    image_id: Mapped[str] = mapped_column(String(64))
    object_key: Mapped[str] = mapped_column(String(512))
    mime_type: Mapped[str] = mapped_column(String(128))
    file_size: Mapped[int] = mapped_column(Integer)
    sort_order: Mapped[int] = mapped_column(Integer)
    # 从 DOCX 提取的图片也属于原始文档内容，和原始文件采用同样的存储标记。
    storage_encrypted: Mapped[bool] = mapped_column(Boolean, default=False)


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


class RequirementModuleSplitJob(Base, TimestampMixin):
    __tablename__ = "requirement_module_split_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    document_version_id: Mapped[str] = mapped_column(ForeignKey("document_versions.id", ondelete="CASCADE"), index=True)
    method: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False)
    coverage_report: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class ContentBlock(Base):
    __tablename__ = "content_blocks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    document_version_id: Mapped[str] = mapped_column(ForeignKey("document_versions.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column()
    block_type: Mapped[str] = mapped_column(String(24))
    # 内容块是统一解析中间层，需求模块通过 source_block_ids 回链到这里。
    content: Mapped[str] = mapped_column(Text, default="")
    # 原始解析正文只以密文保存，普通查询永远只返回上面的脱敏正文。
    raw_content_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    structured_content: Mapped[dict] = mapped_column(JSON, default=dict)
    # 表格、图片等结构化原始结果可能包含敏感文本，因此同样保存密文。
    raw_structured_content_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_locator: Mapped[dict] = mapped_column(JSON, default=dict)
    # 仅保存敏感字段的位置和引用，不保存匹配到的真实值。
    sensitive_spans: Mapped[list] = mapped_column(JSON, default=list)
    # 解析器告警用于驱动人工校正门禁，例如 OCR 未实现或图片无文本层。
    parse_warnings: Mapped[list] = mapped_column(JSON, default=list)
    # 低置信度块必须进入人工校正，不能被静默当作可靠需求正文。
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
    source_type: Mapped[str] = mapped_column(String(16), default="content_blocks")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, index=True)
    parent_module_id: Mapped[str | None] = mapped_column(ForeignKey("requirement_modules.id", ondelete="SET NULL"), nullable=True, index=True)
    split_method: Mapped[str] = mapped_column(String(16), default="rule")
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending_confirmation", index=True)
    revision: Mapped[int] = mapped_column(default=1)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ApiImport(Base, TimestampMixin):
    __tablename__ = "api_imports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    source_type: Mapped[str] = mapped_column(String(16), default="file")
    source_name: Mapped[str] = mapped_column(String(512))
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
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

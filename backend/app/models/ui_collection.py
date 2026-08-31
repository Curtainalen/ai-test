from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, new_uuid


class UiCollectionSession(Base, TimestampMixin):
    __tablename__ = "ui_collection_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    environment_id: Mapped[str] = mapped_column(ForeignKey("test_environments.id", ondelete="RESTRICT"), index=True)
    start_url: Mapped[str] = mapped_column(String(2048))
    allowed_paths: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    max_pages: Mapped[int] = mapped_column(Integer, default=1)
    max_elements_per_page: Mapped[int] = mapped_column(Integer, default=200)
    max_iframes: Mapped[int] = mapped_column(Integer, default=10)
    total_timeout_ms: Mapped[int] = mapped_column(Integer, default=60000)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UiCollectionSnapshot(Base, TimestampMixin):
    __tablename__ = "ui_collection_snapshots"
    __table_args__ = (UniqueConstraint("session_id", "revision", name="uq_ui_collection_snapshot_revision"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("ui_collection_sessions.id", ondelete="CASCADE"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    actual_url: Mapped[str] = mapped_column(String(2048))
    title: Mapped[str] = mapped_column(String(512), default="")
    accessibility_tree: Mapped[dict] = mapped_column(JSON)
    dom_inventory: Mapped[list] = mapped_column(JSON)
    evidence_refs: Mapped[list] = mapped_column(JSON, default=list)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class UiCollectedPage(Base, TimestampMixin):
    __tablename__ = "ui_collected_pages"
    __table_args__ = (UniqueConstraint("snapshot_id", "page_key", name="uq_ui_collected_page_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("ui_collection_snapshots.id", ondelete="CASCADE"), index=True)
    page_key: Mapped[str] = mapped_column(String(128))
    url: Mapped[str] = mapped_column(String(2048))
    title: Mapped[str] = mapped_column(String(512), default="")
    frame_path: Mapped[list] = mapped_column(JSON, default=list)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class UiCollectedElement(Base, TimestampMixin):
    __tablename__ = "ui_collected_elements"
    __table_args__ = (UniqueConstraint("snapshot_id", "element_key", name="uq_ui_collected_element_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("ui_collection_snapshots.id", ondelete="CASCADE"), index=True)
    collected_page_id: Mapped[str] = mapped_column(ForeignKey("ui_collected_pages.id", ondelete="CASCADE"), index=True)
    element_key: Mapped[str] = mapped_column(String(160))
    tag: Mapped[str] = mapped_column(String(32))
    role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    accessible_name: Mapped[str] = mapped_column(String(512), default="")
    attributes: Mapped[dict] = mapped_column(JSON)
    visible: Mapped[bool] = mapped_column(Boolean)
    enabled: Mapped[bool] = mapped_column(Boolean)
    actionable: Mapped[bool] = mapped_column(Boolean)
    checked: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    frame_path: Mapped[list] = mapped_column(JSON, default=list)
    dom_fingerprint: Mapped[str] = mapped_column(String(64))
    evidence_ref: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class UiLocatorCandidate(Base, TimestampMixin):
    __tablename__ = "ui_locator_candidates"
    __table_args__ = (UniqueConstraint("collected_element_id", "priority", name="uq_ui_locator_candidate_priority"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("ui_collection_snapshots.id", ondelete="CASCADE"), index=True)
    collected_element_id: Mapped[str] = mapped_column(ForeignKey("ui_collected_elements.id", ondelete="CASCADE"), index=True)
    priority: Mapped[int] = mapped_column(Integer)
    locator: Mapped[dict] = mapped_column(JSON)
    frame_path: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(24), default="draft", index=True)
    verification_id: Mapped[str | None] = mapped_column(ForeignKey("locator_verifications.id", ondelete="SET NULL"), nullable=True)
    validation_result: Mapped[dict] = mapped_column(JSON, default=dict)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class UiLocatorRevision(Base, TimestampMixin):
    __tablename__ = "ui_locator_revisions"
    __table_args__ = (UniqueConstraint("project_id", "ui_element_id", "revision", name="uq_ui_locator_revision"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    ui_element_id: Mapped[str] = mapped_column(ForeignKey("ui_elements.id", ondelete="RESTRICT"), index=True)
    source_candidate_id: Mapped[str] = mapped_column(ForeignKey("ui_locator_candidates.id", ondelete="RESTRICT"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    primary_locator: Mapped[dict] = mapped_column(JSON)
    fallback_locators: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(24), default="pending_review", index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

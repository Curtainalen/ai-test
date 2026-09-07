from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, new_uuid


class RequirementReview(Base, TimestampMixin):
    __tablename__ = "requirement_reviews"
    __table_args__ = (UniqueConstraint("project_id", "requirement_module_id", "revision", name="uq_requirement_review_revision"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    requirement_module_id: Mapped[str] = mapped_column(ForeignKey("requirement_modules.id", ondelete="RESTRICT"), index=True)
    requirement_module_revision: Mapped[int] = mapped_column(Integer)
    model_config_id: Mapped[str] = mapped_column(ForeignKey("model_configs.id", ondelete="RESTRICT"), index=True)
    model_config_revision_id: Mapped[str | None] = mapped_column(ForeignKey("model_config_revisions.id", ondelete="RESTRICT"), nullable=True)
    llm_call_id: Mapped[str | None] = mapped_column(ForeignKey("llm_call_records.id", ondelete="RESTRICT"), nullable=True)
    revision: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="draft", index=True)
    ambiguities: Mapped[list] = mapped_column(JSON, default=list)
    acceptance_suggestions: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[str] = mapped_column(Text, default="")
    recommendations: Mapped[list] = mapped_column(JSON, default=list)
    scores: Mapped[dict] = mapped_column(JSON, default=dict)
    issues: Mapped[list] = mapped_column(JSON, default=list)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    current_step: Mapped[str] = mapped_column(String(128), default="")
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class RequirementDataItem(Base, TimestampMixin):
    __tablename__ = "requirement_data_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    document_version_id: Mapped[str] = mapped_column(ForeignKey("document_versions.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(128)); data_type: Mapped[str] = mapped_column(String(24), default="string")
    value_ref: Mapped[str] = mapped_column(String(512)); preview: Mapped[str] = mapped_column(String(255), default="")
    sensitive: Mapped[bool] = mapped_column(default=False); source_block_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="pending_confirmation")


class RequirementTestPoint(Base, TimestampMixin):
    __tablename__ = "requirement_test_points"
    __table_args__ = (UniqueConstraint("review_id", "stable_key", name="uq_requirement_test_point_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    review_id: Mapped[str] = mapped_column(ForeignKey("requirement_reviews.id", ondelete="CASCADE"), index=True)
    stable_key: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(255))
    preconditions: Mapped[list] = mapped_column(JSON, default=list)
    test_data_refs: Mapped[list] = mapped_column(JSON, default=list)
    expected_result: Mapped[str] = mapped_column(Text)
    risk: Mapped[str] = mapped_column(String(16))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class RequirementTestCase(Base, TimestampMixin):
    __tablename__ = "requirement_test_cases"
    # 仅约束新流程：历史评审可保留同模块下不同评审版本的相同 stable_key。
    __table_args__ = (Index("ux_requirement_test_case_module_key", "project_id", "requirement_module_id", "stable_key", unique=True, postgresql_where=text("review_id IS NULL")),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    document_version_id: Mapped[str] = mapped_column(ForeignKey("document_versions.id", ondelete="RESTRICT"), index=True)
    requirement_module_id: Mapped[str] = mapped_column(ForeignKey("requirement_modules.id", ondelete="RESTRICT"), index=True)
    review_id: Mapped[str | None] = mapped_column(ForeignKey("requirement_reviews.id", ondelete="SET NULL"), nullable=True, index=True)
    model_config_id: Mapped[str] = mapped_column(ForeignKey("model_configs.id", ondelete="RESTRICT"), index=True)
    model_config_revision_id: Mapped[str | None] = mapped_column(ForeignKey("model_config_revisions.id", ondelete="RESTRICT"), nullable=True)
    llm_call_id: Mapped[str | None] = mapped_column(ForeignKey("llm_call_records.id", ondelete="RESTRICT"), nullable=True)
    stable_key: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(255))
    case_type: Mapped[str] = mapped_column(String(24))
    priority: Mapped[str] = mapped_column(String(8), default="P2")
    preconditions: Mapped[list] = mapped_column(JSON, default=list)
    test_data_refs: Mapped[list] = mapped_column(JSON, default=list)
    steps: Mapped[list] = mapped_column(JSON, default=list)
    expected_result: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="generating", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RequirementCoverage(Base, TimestampMixin):
    __tablename__ = "requirement_coverages"
    __table_args__ = (UniqueConstraint("project_id", "test_point_id", "scenario_type", "scenario_id", name="uq_requirement_coverage"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    test_point_id: Mapped[str] = mapped_column(ForeignKey("requirement_test_points.id", ondelete="RESTRICT"), index=True)
    scenario_type: Mapped[str] = mapped_column(String(16))
    scenario_id: Mapped[str] = mapped_column(String(36), index=True)
    execution_report_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="UNCOVERED", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class ApiScenarioCandidate(Base, TimestampMixin):
    __tablename__ = "api_scenario_candidates"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    model_config_id: Mapped[str] = mapped_column(ForeignKey("model_configs.id", ondelete="RESTRICT"), index=True)
    model_config_revision_id: Mapped[str | None] = mapped_column(ForeignKey("model_config_revisions.id", ondelete="RESTRICT"), nullable=True)
    llm_call_id: Mapped[str | None] = mapped_column(ForeignKey("llm_call_records.id", ondelete="RESTRICT"), nullable=True)
    interface_ids: Mapped[list] = mapped_column(JSON)
    requirement_test_point_ids: Mapped[list] = mapped_column(JSON, default=list)
    requirement_test_case_ids: Mapped[list] = mapped_column(JSON, default=list)
    instruction: Mapped[str] = mapped_column(Text)
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="generating", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_asset_id: Mapped[str | None] = mapped_column(ForeignKey("test_scenarios.id", ondelete="RESTRICT"), nullable=True)

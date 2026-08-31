from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
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
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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

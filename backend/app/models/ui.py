from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, new_uuid


class UiModule(Base, TimestampMixin):
    __tablename__ = "ui_modules"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_ui_module_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("ui_modules.id", ondelete="RESTRICT"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    revision: Mapped[int] = mapped_column(default=1)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class UiPage(Base, TimestampMixin):
    __tablename__ = "ui_pages"
    __table_args__ = (UniqueConstraint("project_id", "module_id", "name", name="uq_ui_page_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    module_id: Mapped[str] = mapped_column(ForeignKey("ui_modules.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(String(2048))
    description: Mapped[str] = mapped_column(Text, default="")
    revision: Mapped[int] = mapped_column(default=1)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class UiElement(Base, TimestampMixin):
    __tablename__ = "ui_elements"
    __table_args__ = (UniqueConstraint("project_id", "page_id", "name", name="uq_ui_element_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    page_id: Mapped[str] = mapped_column(ForeignKey("ui_pages.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    primary_locator: Mapped[dict] = mapped_column(JSON, default=dict)
    fallback_locators: Mapped[list] = mapped_column(JSON, default=list)
    locator_index: Mapped[int | None] = mapped_column(nullable=True)
    iframe_locator: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    verified_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    dom_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revision: Mapped[int] = mapped_column(default=1)
    description: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class UiPageStep(Base, TimestampMixin):
    __tablename__ = "ui_page_steps"
    __table_args__ = (UniqueConstraint("project_id", "page_id", "name", name="uq_ui_page_step_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    page_id: Mapped[str] = mapped_column(ForeignKey("ui_pages.id", ondelete="RESTRICT"), index=True)
    module_id: Mapped[str] = mapped_column(ForeignKey("ui_modules.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    revision: Mapped[int] = mapped_column(default=1)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class UiPageStepDetail(Base, TimestampMixin):
    __tablename__ = "ui_page_step_details"
    __table_args__ = (UniqueConstraint("page_step_id", "step_sort", name="uq_ui_page_step_detail_sort"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    page_step_id: Mapped[str] = mapped_column(ForeignKey("ui_page_steps.id", ondelete="CASCADE"), index=True)
    step_sort: Mapped[int] = mapped_column()
    step_type: Mapped[str] = mapped_column(String(32))
    element_id: Mapped[str | None] = mapped_column(ForeignKey("ui_elements.id", ondelete="RESTRICT"), nullable=True, index=True)
    operation: Mapped[str] = mapped_column(String(32))
    input_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    assertion: Mapped[dict] = mapped_column(JSON, default=dict)
    description: Mapped[str] = mapped_column(Text, default="")


class UiScenario(Base, TimestampMixin):
    __tablename__ = "ui_scenarios"
    __table_args__ = (UniqueConstraint("project_id", "module_id", "name", name="uq_ui_scenario_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    module_id: Mapped[str] = mapped_column(ForeignKey("ui_modules.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    revision: Mapped[int] = mapped_column(default=1)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class UiScenarioStep(Base, TimestampMixin):
    __tablename__ = "ui_scenario_steps"
    __table_args__ = (UniqueConstraint("scenario_id", "step_sort", name="uq_ui_scenario_step_sort"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    scenario_id: Mapped[str] = mapped_column(ForeignKey("ui_scenarios.id", ondelete="CASCADE"), index=True)
    page_step_id: Mapped[str] = mapped_column(ForeignKey("ui_page_steps.id", ondelete="RESTRICT"), index=True)
    step_sort: Mapped[int] = mapped_column()
    data_override: Mapped[dict] = mapped_column(JSON, default=dict)


class LocatorVerification(Base):
    __tablename__ = "locator_verifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    environment_id: Mapped[str | None] = mapped_column(ForeignKey("test_environments.id", ondelete="RESTRICT"), nullable=True, index=True)
    page_id: Mapped[str] = mapped_column(ForeignKey("ui_pages.id", ondelete="RESTRICT"), index=True)
    element_id: Mapped[str | None] = mapped_column(ForeignKey("ui_elements.id", ondelete="SET NULL"), nullable=True, index=True)
    element_revision: Mapped[int | None] = mapped_column(nullable=True)
    locator: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    iframe_locator: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    target_url: Mapped[str] = mapped_column(String(2048))
    actual_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    navigation_timeout_ms: Mapped[int] = mapped_column(Integer, default=15000)
    operation_timeout_ms: Mapped[int] = mapped_column(Integer, default=5000)
    total_timeout_ms: Mapped[int] = mapped_column(Integer, default=30000)
    match_count: Mapped[int | None] = mapped_column(nullable=True)
    visible: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    actionable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    dom_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    dom_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class UiExplorationSession(Base, TimestampMixin):
    __tablename__ = "ui_exploration_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    environment_id: Mapped[str] = mapped_column(ForeignKey("test_environments.id", ondelete="RESTRICT"), index=True)
    model_config_id: Mapped[str | None] = mapped_column(ForeignKey("model_configs.id", ondelete="RESTRICT"), nullable=True, index=True)
    goal: Mapped[str] = mapped_column(Text)
    requirement_test_point_ids: Mapped[list] = mapped_column(JSON, default=list)
    start_url: Mapped[str] = mapped_column(String(2048))
    allowed_paths: Mapped[list] = mapped_column(JSON, default=list)
    allowed_operations: Mapped[list] = mapped_column(JSON, default=list)
    blocked_operations: Mapped[list] = mapped_column(JSON, default=list)
    max_steps: Mapped[int] = mapped_column(Integer)
    total_timeout_ms: Mapped[int] = mapped_column(Integer)
    navigation_timeout_ms: Mapped[int] = mapped_column(Integer, default=30000)
    operation_timeout_ms: Mapped[int] = mapped_column(Integer, default=8000)
    llm_turn_timeout_ms: Mapped[int] = mapped_column(Integer, default=45000)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    current_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    dom_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_evidence_ref: Mapped[str | None] = mapped_column(ForeignKey("ui_evidence.id", ondelete="SET NULL"), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    lease_token: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class UiExplorationStep(Base, TimestampMixin):
    __tablename__ = "ui_exploration_steps"
    __table_args__ = (UniqueConstraint("exploration_id", "seq", name="uq_ui_exploration_step_seq"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    exploration_id: Mapped[str] = mapped_column(ForeignKey("ui_exploration_sessions.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    operation: Mapped[str] = mapped_column(String(32))
    locator: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    input_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    actual_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    dom_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UiExplorationTurn(Base, TimestampMixin):
    __tablename__ = "ui_exploration_turns"
    __table_args__ = (UniqueConstraint("exploration_id", "seq", name="uq_ui_exploration_turn_seq"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    exploration_id: Mapped[str] = mapped_column(ForeignKey("ui_exploration_sessions.id", ondelete="CASCADE"), index=True)
    snapshot_id: Mapped[str | None] = mapped_column(ForeignKey("ui_collection_snapshots.id", ondelete="SET NULL"), nullable=True)
    seq: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(24), index=True)
    action_proposal: Mapped[dict] = mapped_column(JSON, default=dict)
    policy_decision: Mapped[dict] = mapped_column(JSON, default=dict)
    observation: Mapped[dict] = mapped_column(JSON, default=dict)
    llm_call_id: Mapped[str | None] = mapped_column(ForeignKey("llm_call_records.id", ondelete="RESTRICT"), nullable=True)
    approval_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class UiExecutionTask(Base, TimestampMixin):
    __tablename__ = "ui_execution_tasks"
    __table_args__ = (UniqueConstraint("project_id", "idempotency_key", name="uq_ui_execution_idempotency"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    scenario_id: Mapped[str] = mapped_column(ForeignKey("ui_scenarios.id", ondelete="RESTRICT"), index=True)
    environment_id: Mapped[str] = mapped_column(ForeignKey("test_environments.id", ondelete="RESTRICT"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    event_version: Mapped[int] = mapped_column(Integer, default=1)
    scenario_snapshot: Mapped[dict] = mapped_column(JSON)
    environment_snapshot: Mapped[dict] = mapped_column(JSON)
    trace_manifest_ref: Mapped[str | None] = mapped_column(ForeignKey("ui_evidence.id", ondelete="RESTRICT"), nullable=True)
    lease_token: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UiExecutionStep(Base, TimestampMixin):
    __tablename__ = "ui_execution_steps"
    __table_args__ = (UniqueConstraint("execution_id", "seq", name="uq_ui_execution_step_seq"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    execution_id: Mapped[str] = mapped_column(ForeignKey("ui_execution_tasks.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    action_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    result_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence_refs: Mapped[list] = mapped_column(JSON, default=list)
    error_category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)


class UiExecutionReport(Base, TimestampMixin):
    __tablename__ = "ui_execution_reports"
    __table_args__ = (UniqueConstraint("execution_id", name="uq_ui_execution_report_execution"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    execution_id: Mapped[str] = mapped_column(ForeignKey("ui_execution_tasks.id", ondelete="RESTRICT"), index=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    scenario_snapshot: Mapped[dict] = mapped_column(JSON)
    environment_snapshot: Mapped[dict] = mapped_column(JSON)
    trace_manifest_ref: Mapped[str | None] = mapped_column(ForeignKey("ui_evidence.id", ondelete="RESTRICT"), nullable=True)
    triggered_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UiExecutionReportStep(Base):
    __tablename__ = "ui_execution_report_steps"
    __table_args__ = (UniqueConstraint("report_id", "seq", name="uq_ui_execution_report_step_seq"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    report_id: Mapped[str] = mapped_column(ForeignKey("ui_execution_reports.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16))
    action_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    result_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence_refs: Mapped[list] = mapped_column(JSON, default=list)
    error_category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)


class UiEvidence(Base, TimestampMixin):
    __tablename__ = "ui_evidence"
    __table_args__ = (UniqueConstraint("project_id", "object_key", name="uq_ui_evidence_object_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    owner_type: Mapped[str] = mapped_column(String(32), index=True)
    owner_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    object_key: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str] = mapped_column(String(128))
    byte_size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class UiAutomationCandidate(Base, TimestampMixin):
    __tablename__ = "ui_automation_candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    exploration_id: Mapped[str | None] = mapped_column(ForeignKey("ui_exploration_sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    execution_id: Mapped[str | None] = mapped_column(ForeignKey("ui_execution_tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    model_config_id: Mapped[str | None] = mapped_column(ForeignKey("model_configs.id", ondelete="SET NULL"), nullable=True)
    candidate_type: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    source_evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmed_asset_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))

from __future__ import annotations

from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.base import TimestampMixin, new_uuid


class TestScenario(Base, TimestampMixin):
    __tablename__ = "test_scenarios"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255)); description: Mapped[str] = mapped_column(Text, default="")
    scenario_type: Mapped[str] = mapped_column(String(24), default="api"); priority: Mapped[str] = mapped_column(String(8), default="P2")
    version: Mapped[int] = mapped_column(default=1); revision: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    requirement_module_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    confirmed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ScenarioStep(Base, TimestampMixin):
    __tablename__ = "scenario_steps"; __table_args__ = (UniqueConstraint("scenario_id", "seq", name="uq_scenario_step_seq"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    scenario_id: Mapped[str] = mapped_column(ForeignKey("test_scenarios.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(); name: Mapped[str] = mapped_column(String(255))
    interface_id: Mapped[str | None] = mapped_column(ForeignKey("api_interfaces.id", ondelete="RESTRICT"), nullable=True)
    request_override: Mapped[dict] = mapped_column(JSON, default=dict); preconditions: Mapped[list] = mapped_column(JSON, default=list)
    extracts: Mapped[list] = mapped_column(JSON, default=list); assertions: Mapped[list] = mapped_column(JSON, default=list)
    expected_result: Mapped[str] = mapped_column(Text, default=""); timeout_ms: Mapped[int] = mapped_column(default=30000)
    retry_count: Mapped[int] = mapped_column(default=0); continue_on_failure: Mapped[bool] = mapped_column(Boolean, default=False)


class ExecutionTask(Base, TimestampMixin):
    __tablename__ = "execution_tasks"; __table_args__ = (UniqueConstraint("project_id", "idempotency_key", name="uq_execution_idempotency"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    scenario_id: Mapped[str] = mapped_column(ForeignKey("test_scenarios.id", ondelete="RESTRICT")); environment_id: Mapped[str] = mapped_column(ForeignKey("test_environments.id", ondelete="RESTRICT"))
    idempotency_key: Mapped[str] = mapped_column(String(128)); status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False); event_version: Mapped[int] = mapped_column(default=1)
    scenario_snapshot: Mapped[dict] = mapped_column(JSON); environment_snapshot: Mapped[dict] = mapped_column(JSON)
    error_category: Mapped[str | None] = mapped_column(String(32), nullable=True); error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT")); started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True); finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExecutionStep(Base):
    __tablename__ = "execution_steps"; __table_args__ = (UniqueConstraint("execution_id", "seq", name="uq_execution_step_seq"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid); project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    execution_id: Mapped[str] = mapped_column(ForeignKey("execution_tasks.id", ondelete="CASCADE"), index=True); seq: Mapped[int] = mapped_column(); name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="pending"); started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True); finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True); duration_ms: Mapped[int] = mapped_column(default=0)
    request_snapshot: Mapped[dict] = mapped_column(JSON, default=dict); response_snapshot: Mapped[dict] = mapped_column(JSON, default=dict); extracted: Mapped[dict] = mapped_column(JSON, default=dict); assertions: Mapped[list] = mapped_column(JSON, default=list)
    error_category: Mapped[str | None] = mapped_column(String(32), nullable=True); error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class TestReport(Base):
    __tablename__ = "test_reports"; __table_args__ = (UniqueConstraint("execution_id", name="uq_report_execution"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid); project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True); execution_id: Mapped[str] = mapped_column(ForeignKey("execution_tasks.id", ondelete="RESTRICT"), index=True)
    status: Mapped[str] = mapped_column(String(16), index=True); summary: Mapped[dict] = mapped_column(JSON); project_snapshot: Mapped[dict] = mapped_column(JSON); environment_snapshot: Mapped[dict] = mapped_column(JSON); scenario_snapshot: Mapped[dict] = mapped_column(JSON); requirement_snapshot: Mapped[list] = mapped_column(JSON, default=list); triggered_by_snapshot: Mapped[dict] = mapped_column(JSON); started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True)); finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True)); created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReportStep(Base):
    __tablename__ = "report_steps"; __table_args__ = (UniqueConstraint("report_id", "seq", name="uq_report_step_seq"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid); project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True); report_id: Mapped[str] = mapped_column(ForeignKey("test_reports.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(); name: Mapped[str] = mapped_column(String(255)); status: Mapped[str] = mapped_column(String(16)); duration_ms: Mapped[int] = mapped_column(); request_snapshot: Mapped[dict] = mapped_column(JSON); response_snapshot: Mapped[dict] = mapped_column(JSON); extracted: Mapped[dict] = mapped_column(JSON); assertions: Mapped[list] = mapped_column(JSON); error_category: Mapped[str | None] = mapped_column(String(32), nullable=True); error_message: Mapped[str | None] = mapped_column(Text, nullable=True); repro_steps: Mapped[list] = mapped_column(JSON, default=list)

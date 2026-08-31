"""assets scenarios executions reports

Revision ID: 0002
Revises: 0001
"""
from alembic import op
from app.database import Base
from app import models  # noqa: F401

revision = "0002"; down_revision = "0001"; branch_labels = None; depends_on = None
TABLES = ["requirement_documents", "document_versions", "document_parse_jobs", "content_blocks", "requirement_modules", "api_imports", "api_modules", "api_interfaces", "debug_runs", "test_scenarios", "scenario_steps", "execution_tasks", "execution_steps", "test_reports", "report_steps"]

def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, tables=[Base.metadata.tables[name] for name in TABLES], checkfirst=True)

def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, tables=[Base.metadata.tables[name] for name in reversed(TABLES)], checkfirst=True)

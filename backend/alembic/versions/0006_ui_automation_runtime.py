"""UI exploration, actuator execution, evidence and AI candidates.

Revision ID: 0006
Revises: 0005
"""

from alembic import op

from app import models  # noqa: F401
from app.database import Base

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

TABLES = [
    "ui_exploration_sessions",
    "ui_exploration_steps",
    "ui_execution_tasks",
    "ui_execution_steps",
    "ui_execution_reports",
    "ui_execution_report_steps",
    "ui_evidence",
    "ui_automation_candidates",
]


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, tables=[Base.metadata.tables[name] for name in TABLES], checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, tables=[Base.metadata.tables[name] for name in reversed(TABLES)], checkfirst=True)

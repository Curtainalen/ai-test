"""UI assets and controlled locator verification

Revision ID: 0005
Revises: 0004
"""

from alembic import op

from app import models  # noqa: F401
from app.database import Base

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

TABLES = [
    "ui_modules",
    "ui_pages",
    "ui_elements",
    "ui_page_steps",
    "ui_page_step_details",
    "ui_scenarios",
    "ui_scenario_steps",
    "locator_verifications",
]


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, tables=[Base.metadata.tables[name] for name in TABLES], checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, tables=[Base.metadata.tables[name] for name in reversed(TABLES)], checkfirst=True)

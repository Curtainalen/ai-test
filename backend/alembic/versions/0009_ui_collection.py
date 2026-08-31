"""Structured UI collection and locator revisions.

Revision ID: 0009
Revises: 0008
"""
from alembic import op
from app import models  # noqa: F401
from app.database import Base

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None
TABLES = ["ui_collection_sessions", "ui_collection_snapshots", "ui_collected_pages", "ui_collected_elements", "ui_locator_candidates", "ui_locator_revisions"]


def upgrade() -> None:
    bind = op.get_bind(); Base.metadata.create_all(bind=bind, tables=[Base.metadata.tables[name] for name in TABLES], checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind(); Base.metadata.drop_all(bind=bind, tables=[Base.metadata.tables[name] for name in reversed(TABLES)], checkfirst=True)

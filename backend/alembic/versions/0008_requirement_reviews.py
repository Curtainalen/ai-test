"""Requirement reviews, test points and coverage.

Revision ID: 0008
Revises: 0007
"""
from alembic import op
from app import models  # noqa: F401
from app.database import Base

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None
TABLES = ["requirement_reviews", "requirement_test_points", "requirement_coverages"]


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, tables=[Base.metadata.tables[name] for name in TABLES], checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, tables=[Base.metadata.tables[name] for name in reversed(TABLES)], checkfirst=True)

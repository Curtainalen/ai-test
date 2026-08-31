"""Persistent API scenario candidates.

Revision ID: 0013
Revises: 0012
"""
from alembic import op

from app import models  # noqa: F401
from app.database import Base

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(
        bind=bind,
        tables=[Base.metadata.tables["api_scenario_candidates"]],
        checkfirst=True,
    )


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(
        bind=bind,
        tables=[Base.metadata.tables["api_scenario_candidates"]],
        checkfirst=True,
    )

"""record requirement test case response normalization

Revision ID: 0023
Revises: 0022
"""
from alembic import op
import sqlalchemy as sa

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("requirement_test_cases", sa.Column("normalization_applied", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("requirement_test_cases", "normalization_applied")

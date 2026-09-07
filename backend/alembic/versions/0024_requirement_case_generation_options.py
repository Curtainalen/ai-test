"""persist requirement test case generation options

Revision ID: 0024
Revises: 0023
"""
from alembic import op
import sqlalchemy as sa

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("requirement_test_cases", sa.Column("generation_options", sa.JSON(), nullable=False, server_default="{}"))
    op.alter_column("requirement_test_cases", "generation_options", server_default=None)


def downgrade() -> None:
    op.drop_column("requirement_test_cases", "generation_options")

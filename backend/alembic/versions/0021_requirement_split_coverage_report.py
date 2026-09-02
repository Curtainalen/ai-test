"""persist module split coverage reports

Revision ID: 0021
Revises: 0020
"""
from alembic import op
import sqlalchemy as sa

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("requirement_module_split_jobs", sa.Column("coverage_report", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.alter_column("requirement_module_split_jobs", "coverage_report", server_default=None)

def downgrade() -> None:
    op.drop_column("requirement_module_split_jobs", "coverage_report")

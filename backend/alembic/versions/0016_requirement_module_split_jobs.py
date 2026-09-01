"""Add asynchronous requirement module split jobs.

Revision ID: 0016
Revises: 0015
"""
from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("requirement_module_split_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_version_id", sa.String(36), sa.ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("method", sa.String(16), nullable=False), sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error_code", sa.String(64)), sa.Column("error_message", sa.Text()), sa.Column("fallback_used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_requirement_module_split_jobs_project_id", "requirement_module_split_jobs", ["project_id"])
    op.create_index("ix_requirement_module_split_jobs_document_version_id", "requirement_module_split_jobs", ["document_version_id"])
    op.create_index("ix_requirement_module_split_jobs_status", "requirement_module_split_jobs", ["status"])


def downgrade() -> None:
    op.drop_table("requirement_module_split_jobs")

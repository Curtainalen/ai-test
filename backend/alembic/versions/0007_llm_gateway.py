"""LLM configuration revisions and call records.

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("model_config_revisions",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("model_config_id", sa.String(36), nullable=False), sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("config_snapshot", sa.JSON(), nullable=False), sa.Column("api_key_encrypted", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(36), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["model_config_id"], ["model_configs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("project_id", "model_config_id", "revision", name="uq_model_config_revision"))
    op.create_index("ix_model_config_revisions_project_id", "model_config_revisions", ["project_id"])
    op.create_index("ix_model_config_revisions_model_config_id", "model_config_revisions", ["model_config_id"])
    op.create_table("llm_call_records",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("model_config_id", sa.String(36), nullable=False), sa.Column("model_config_revision_id", sa.String(36), nullable=False),
        sa.Column("purpose", sa.String(64), nullable=False), sa.Column("status", sa.String(24), nullable=False),
        sa.Column("prompt_redacted", sa.Text(), nullable=False), sa.Column("response_redacted", sa.JSON(), nullable=True),
        sa.Column("response_schema", sa.JSON(), nullable=False), sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True), sa.Column("usage_unknown", sa.Boolean(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False), sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True), sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["model_config_id"], ["model_configs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["model_config_revision_id"], ["model_config_revisions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"))
    for column in ("project_id", "model_config_id", "model_config_revision_id", "purpose", "status"):
        op.create_index(f"ix_llm_call_records_{column}", "llm_call_records", [column])


def downgrade() -> None:
    op.drop_table("llm_call_records")
    op.drop_table("model_config_revisions")

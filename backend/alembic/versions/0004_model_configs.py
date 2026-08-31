"""global model configurations

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "model_configs" in inspect(bind).get_table_names():
        return
    op.create_table(
        "model_configs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("protocol", sa.String(length=32), nullable=False),
        sa.Column("model_name", sa.String(length=256), nullable=False),
        sa.Column("base_url", sa.String(length=2048), nullable=True),
        sa.Column("api_key_encrypted", sa.Text(), nullable=False, server_default=""),
        sa.Column("api_key_hint", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("extra_params", sa.JSON(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("max_retries", sa.Integer(), nullable=False),
        sa.Column("context_window", sa.Integer(), nullable=True),
        sa.Column("supports_vision", sa.Boolean(), nullable=False),
        sa.Column("supports_streaming", sa.Boolean(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("name", name="uq_model_configs_name"),
    )
    op.create_index("ix_model_configs_name", "model_configs", ["name"])
    op.create_index("ix_model_configs_created_by", "model_configs", ["created_by"])
    op.create_index("ix_model_configs_is_default", "model_configs", ["is_default"])
    op.create_index("ix_model_configs_is_enabled", "model_configs", ["is_enabled"])
    op.create_index("uq_model_configs_default", "model_configs", ["is_default"], unique=True, postgresql_where=sa.text("is_default"))


def downgrade() -> None:
    bind = op.get_bind()
    if "model_configs" in inspect(bind).get_table_names():
        op.drop_table("model_configs")

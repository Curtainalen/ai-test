"""requirement data references
Revision ID: 0022
Revises: 0021
"""
from alembic import op
import sqlalchemy as sa
revision = "0022"; down_revision = "0021"; branch_labels = None; depends_on = None
def upgrade():
    op.create_table("requirement_data_items", sa.Column("id", sa.String(36), primary_key=True), sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False), sa.Column("document_version_id", sa.String(36), sa.ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False), sa.Column("name", sa.String(128), nullable=False), sa.Column("data_type", sa.String(24), nullable=False, server_default="string"), sa.Column("value_ref", sa.String(512), nullable=False), sa.Column("preview", sa.String(255), nullable=False, server_default=""), sa.Column("sensitive", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("source_block_seq", sa.Integer()), sa.Column("status", sa.String(24), nullable=False, server_default="pending_confirmation"), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False))
def downgrade(): op.drop_table("requirement_data_items")

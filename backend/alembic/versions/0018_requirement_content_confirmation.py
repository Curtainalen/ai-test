"""require source-document confirmation before parsing

Revision ID: 0018
Revises: 0017
"""
from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {item["name"] for item in sa.inspect(bind).get_columns("document_versions")}
    if "content_status" not in columns:
        op.add_column("document_versions", sa.Column("content_status", sa.String(length=24), nullable=False, server_default="pending_confirmation"))
    if "content_confirmed_at" not in columns:
        op.add_column("document_versions", sa.Column("content_confirmed_at", sa.DateTime(timezone=True), nullable=True))
    if "content_confirmed_by" not in columns:
        op.add_column("document_versions", sa.Column("content_confirmed_by", sa.String(length=36), nullable=True))
    foreign_keys = {item["name"] for item in sa.inspect(bind).get_foreign_keys("document_versions")}
    if "fk_document_versions_content_confirmed_by_users" not in foreign_keys:
        op.create_foreign_key("fk_document_versions_content_confirmed_by_users", "document_versions", "users", ["content_confirmed_by"], ["id"], ondelete="RESTRICT")
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("document_versions")}
    if "ix_document_versions_content_status" not in indexes:
        op.create_index("ix_document_versions_content_status", "document_versions", ["content_status"])
    # Existing documents have already completed parsing, so preserve their
    # previous availability. New uploads await confirmation.
    op.execute("UPDATE document_versions SET content_status = 'confirmed' WHERE parse_status = 'completed'")
    op.alter_column("document_versions", "content_status", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_document_versions_content_status", table_name="document_versions")
    op.drop_constraint("fk_document_versions_content_confirmed_by_users", "document_versions", type_="foreignkey")
    op.drop_column("document_versions", "content_confirmed_by")
    op.drop_column("document_versions", "content_confirmed_at")
    op.drop_column("document_versions", "content_status")

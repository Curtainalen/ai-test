"""preserve ordered document text and extracted images

Revision ID: 0020
Revises: 0019
"""
from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("document_versions", sa.Column("full_text", sa.Text(), nullable=False, server_default=""))
    op.alter_column("document_versions", "full_text", server_default=None)
    op.create_table("document_images",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_version_id", sa.String(36), sa.ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("image_id", sa.String(64), nullable=False),
        sa.Column("object_key", sa.String(512), nullable=False),
        sa.Column("mime_type", sa.String(128), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("document_version_id", "image_id", name="uq_document_image_id"),
    )
    op.create_index("ix_document_images_project_id", "document_images", ["project_id"])
    op.create_index("ix_document_images_document_version_id", "document_images", ["document_version_id"])


def downgrade() -> None:
    op.drop_index("ix_document_images_document_version_id", table_name="document_images")
    op.drop_index("ix_document_images_project_id", table_name="document_images")
    op.drop_table("document_images")
    op.drop_column("document_versions", "full_text")

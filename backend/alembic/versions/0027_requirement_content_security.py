"""add encrypted source metadata and content security fields

Revision ID: 0027
Revises: 0026
"""

from alembic import op
import sqlalchemy as sa


revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 旧数据默认按明文兼容读取；新上传数据由应用层写入密文并置为 true。
    bind = op.get_bind()
    for table, column in (("document_versions", "storage_encrypted"), ("document_images", "storage_encrypted")):
        existing = {item["name"] for item in sa.inspect(bind).get_columns(table)}
        if column not in existing:
            op.add_column(table, sa.Column(column, sa.Boolean(), nullable=False, server_default=sa.false()))
            op.alter_column(table, column, server_default=None)
    existing = {item["name"] for item in sa.inspect(bind).get_columns("content_blocks")}
    columns = (
        sa.Column("raw_content_ciphertext", sa.Text(), nullable=True),
        sa.Column("raw_structured_content_ciphertext", sa.Text(), nullable=True),
        sa.Column("sensitive_spans", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("parse_warnings", sa.JSON(), nullable=False, server_default="[]"),
    )
    for column in columns:
        if column.name not in existing:
            op.add_column("content_blocks", column)
    for column in columns:
        if column.name in {item["name"] for item in sa.inspect(bind).get_columns("content_blocks")}:
            op.alter_column("content_blocks", column.name, server_default=None)
    # 旧版本的正文尚未经过本次脱敏和人工映射流程，统一要求重新核对后才可拆分。
    op.execute("UPDATE document_versions SET content_status = 'pending_confirmation', content_confirmed_at = NULL, content_confirmed_by = NULL WHERE parse_status = 'completed'")


def downgrade() -> None:
    # 数据安全字段不做自动回滚，避免回滚过程意外产生明文文件。
    pass

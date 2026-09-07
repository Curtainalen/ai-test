"""align requirement data item columns with the runtime model"""
from alembic import op
import sqlalchemy as sa

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = {column["name"] for column in sa.inspect(bind).get_columns("requirement_data_items")}
    columns = (
        sa.Column("label", sa.String(255), nullable=False, server_default=""),
        sa.Column("sensitivity", sa.String(16), nullable=False, server_default="internal"),
        sa.Column("reference", sa.String(512), nullable=False, server_default=""),
        sa.Column("source_block_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("constraints", sa.JSON(), nullable=False, server_default="{}"),
    )
    for column in columns:
        if column.name not in existing:
            op.add_column("requirement_data_items", column)


def downgrade() -> None:
    pass

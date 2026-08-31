"""remote OpenAPI source metadata

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("api_imports")}
    if "source_url" not in columns:
        op.add_column("api_imports", sa.Column("source_url", sa.String(length=2048), nullable=True))


def downgrade() -> None:
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("api_imports")}
    if "source_url" in columns:
        op.drop_column("api_imports", "source_url")

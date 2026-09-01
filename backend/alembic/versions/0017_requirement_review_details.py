"""Add detailed requirement review results.

Revision ID: 0017
Revises: 0016
"""
import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("requirement_reviews")}
    additions = (
        ("summary", sa.Column("summary", sa.Text(), nullable=False, server_default="")),
        ("recommendations", sa.Column("recommendations", sa.JSON(), nullable=False, server_default="[]")),
        ("scores", sa.Column("scores", sa.JSON(), nullable=False, server_default="{}")),
        ("issues", sa.Column("issues", sa.JSON(), nullable=False, server_default="[]")),
        ("progress", sa.Column("progress", sa.Integer(), nullable=False, server_default="0")),
        ("current_step", sa.Column("current_step", sa.String(128), nullable=False, server_default="")),
        ("cancel_requested", sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false())),
    )
    for name, column in additions:
        if name not in columns:
            op.add_column("requirement_reviews", column)


def downgrade() -> None:
    for name in ("cancel_requested", "current_step", "progress", "issues", "scores", "recommendations", "summary"):
        if name in {item["name"] for item in sa.inspect(op.get_bind()).get_columns("requirement_reviews")}:
            op.drop_column("requirement_reviews", name)

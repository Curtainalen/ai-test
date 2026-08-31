"""Queue-backed locator verification metadata.

Revision ID: 0012
Revises: 0011
"""
import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {item["name"] for item in inspector.get_columns("locator_verifications")}
    additions = (
        ("environment_id", sa.Column("environment_id", sa.String(36), nullable=True)),
        ("navigation_timeout_ms", sa.Column("navigation_timeout_ms", sa.Integer(), nullable=False, server_default="15000")),
        ("operation_timeout_ms", sa.Column("operation_timeout_ms", sa.Integer(), nullable=False, server_default="5000")),
        ("total_timeout_ms", sa.Column("total_timeout_ms", sa.Integer(), nullable=False, server_default="30000")),
        ("cancel_requested", sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false())),
    )
    for name, column in additions:
        if name not in columns:
            op.add_column("locator_verifications", column)
    foreign_keys = inspector.get_foreign_keys("locator_verifications")
    if not any(item["constrained_columns"] == ["environment_id"] for item in foreign_keys):
        op.create_foreign_key("fk_locator_verifications_environment", "locator_verifications", "test_environments", ["environment_id"], ["id"], ondelete="RESTRICT")
    indexes = inspector.get_indexes("locator_verifications")
    if not any(item["column_names"] == ["environment_id"] for item in indexes):
        op.create_index("ix_locator_verifications_environment_id", "locator_verifications", ["environment_id"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    index = next((item for item in inspector.get_indexes("locator_verifications") if item["column_names"] == ["environment_id"]), None)
    if index:
        op.drop_index(index["name"], table_name="locator_verifications")
    foreign_key = next((item for item in inspector.get_foreign_keys("locator_verifications") if item["constrained_columns"] == ["environment_id"]), None)
    if foreign_key and foreign_key["name"]:
        op.drop_constraint(foreign_key["name"], "locator_verifications", type_="foreignkey")
    for name in ("cancel_requested", "total_timeout_ms", "operation_timeout_ms", "navigation_timeout_ms", "environment_id"):
        if name in {item["name"] for item in inspector.get_columns("locator_verifications")}:
            op.drop_column("locator_verifications", name)

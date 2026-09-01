"""Add requirement module confirmation workflow metadata.

Revision ID: 0015
Revises: 0014
"""
import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("requirement_modules")}
    additions = (
        ("source_type", sa.Column("source_type", sa.String(16), nullable=False, server_default="content_blocks")),
        ("sort_order", sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0")),
        ("parent_module_id", sa.Column("parent_module_id", sa.String(36), nullable=True)),
        ("split_method", sa.Column("split_method", sa.String(16), nullable=False, server_default="rule")),
        ("confidence", sa.Column("confidence", sa.Float(), nullable=True)),
        ("created_by", sa.Column("created_by", sa.String(36), nullable=True)),
        ("updated_by", sa.Column("updated_by", sa.String(36), nullable=True)),
        ("archived_at", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True)),
    )
    for name, column in additions:
        if name not in columns:
            op.add_column("requirement_modules", column)
    indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("requirement_modules")}
    if "ix_requirement_modules_sort_order" not in indexes:
        op.create_index("ix_requirement_modules_sort_order", "requirement_modules", ["sort_order"])
    foreign_keys = sa.inspect(op.get_bind()).get_foreign_keys("requirement_modules")
    if not any(item["constrained_columns"] == ["parent_module_id"] for item in foreign_keys):
        op.create_foreign_key("fk_requirement_modules_parent", "requirement_modules", "requirement_modules", ["parent_module_id"], ["id"], ondelete="SET NULL")
    if not any(item["constrained_columns"] == ["created_by"] for item in foreign_keys):
        op.create_foreign_key("fk_requirement_modules_created_by", "requirement_modules", "users", ["created_by"], ["id"], ondelete="RESTRICT")
    if not any(item["constrained_columns"] == ["updated_by"] for item in foreign_keys):
        op.create_foreign_key("fk_requirement_modules_updated_by", "requirement_modules", "users", ["updated_by"], ["id"], ondelete="RESTRICT")


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for foreign_key in inspector.get_foreign_keys("requirement_modules"):
        if foreign_key.get("name") in {"fk_requirement_modules_parent", "fk_requirement_modules_created_by", "fk_requirement_modules_updated_by"}:
            op.drop_constraint(foreign_key["name"], "requirement_modules", type_="foreignkey")
    if "ix_requirement_modules_sort_order" in {item["name"] for item in inspector.get_indexes("requirement_modules")}:
        op.drop_index("ix_requirement_modules_sort_order", table_name="requirement_modules")
    for name in ("archived_at", "updated_by", "created_by", "confidence", "split_method", "parent_module_id", "sort_order", "source_type"):
        if name in {item["name"] for item in sa.inspect(op.get_bind()).get_columns("requirement_modules")}:
            op.drop_column("requirement_modules", name)

"""Controlled trace manifest references.

Revision ID: 0011
Revises: 0010
"""
import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table_name, constraint_name in (
        ("ui_execution_tasks", "fk_ui_execution_tasks_trace_manifest"),
        ("ui_execution_reports", "fk_ui_execution_reports_trace_manifest"),
    ):
        columns = {item["name"] for item in inspector.get_columns(table_name)}
        if "trace_manifest_ref" not in columns:
            op.add_column(table_name, sa.Column("trace_manifest_ref", sa.String(36), nullable=True))
        foreign_keys = inspector.get_foreign_keys(table_name)
        if not any(item["constrained_columns"] == ["trace_manifest_ref"] for item in foreign_keys):
            op.create_foreign_key(constraint_name, table_name, "ui_evidence", ["trace_manifest_ref"], ["id"], ondelete="RESTRICT")


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table_name in ("ui_execution_reports", "ui_execution_tasks"):
        foreign_key = next((item for item in inspector.get_foreign_keys(table_name) if item["constrained_columns"] == ["trace_manifest_ref"]), None)
        if foreign_key and foreign_key["name"]:
            op.drop_constraint(foreign_key["name"], table_name, type_="foreignkey")
        columns = {item["name"] for item in inspector.get_columns(table_name)}
        if "trace_manifest_ref" in columns:
            op.drop_column(table_name, "trace_manifest_ref")

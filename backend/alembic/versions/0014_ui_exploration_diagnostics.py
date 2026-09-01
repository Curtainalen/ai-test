"""Separate exploration budgets and persist failure diagnostics.

Revision ID: 0014
Revises: 0013
"""
import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def _add_columns(table: str, additions) -> None:
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table)}
    for name, column in additions:
        if name not in columns:
            op.add_column(table, column)


def upgrade() -> None:
    _add_columns("ui_exploration_sessions", (
        ("navigation_timeout_ms", sa.Column("navigation_timeout_ms", sa.Integer(), nullable=False, server_default="30000")),
        ("operation_timeout_ms", sa.Column("operation_timeout_ms", sa.Integer(), nullable=False, server_default="8000")),
        ("llm_turn_timeout_ms", sa.Column("llm_turn_timeout_ms", sa.Integer(), nullable=False, server_default="25000")),
        ("last_evidence_ref", sa.Column("last_evidence_ref", sa.String(36), nullable=True)),
    ))
    _add_columns("ui_exploration_turns", (
        ("error_code", sa.Column("error_code", sa.String(64), nullable=True)),
        ("error_message", sa.Column("error_message", sa.Text(), nullable=True)),
        ("started_at", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True)),
        ("finished_at", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True)),
    ))
    foreign_keys = sa.inspect(op.get_bind()).get_foreign_keys("ui_exploration_sessions")
    if not any(item["constrained_columns"] == ["last_evidence_ref"] for item in foreign_keys):
        op.create_foreign_key("fk_ui_exploration_last_evidence", "ui_exploration_sessions", "ui_evidence", ["last_evidence_ref"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    foreign_key = next((item for item in inspector.get_foreign_keys("ui_exploration_sessions") if item["constrained_columns"] == ["last_evidence_ref"]), None)
    if foreign_key and foreign_key["name"]:
        op.drop_constraint(foreign_key["name"], "ui_exploration_sessions", type_="foreignkey")
    for name in ("last_evidence_ref", "llm_turn_timeout_ms", "operation_timeout_ms", "navigation_timeout_ms"):
        if name in {item["name"] for item in sa.inspect(op.get_bind()).get_columns("ui_exploration_sessions")}:
            op.drop_column("ui_exploration_sessions", name)
    for name in ("finished_at", "started_at", "error_message", "error_code"):
        if name in {item["name"] for item in sa.inspect(op.get_bind()).get_columns("ui_exploration_turns")}:
            op.drop_column("ui_exploration_turns", name)

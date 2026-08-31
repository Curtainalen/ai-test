"""AI exploration turns and model binding.

Revision ID: 0010
Revises: 0009
"""
import sqlalchemy as sa
from alembic import op
from app import models  # noqa: F401
from app.database import Base

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {item["name"] for item in inspector.get_columns("ui_exploration_sessions")}
    if "model_config_id" not in columns:
        op.add_column("ui_exploration_sessions", sa.Column("model_config_id", sa.String(36), nullable=True))
    if "requirement_test_point_ids" not in columns:
        op.add_column("ui_exploration_sessions", sa.Column("requirement_test_point_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")))
    foreign_keys = inspector.get_foreign_keys("ui_exploration_sessions")
    if not any(item["constrained_columns"] == ["model_config_id"] for item in foreign_keys):
        op.create_foreign_key("fk_ui_exploration_model_config", "ui_exploration_sessions", "model_configs", ["model_config_id"], ["id"], ondelete="RESTRICT")
    indexes = inspector.get_indexes("ui_exploration_sessions")
    if not any(item["column_names"] == ["model_config_id"] for item in indexes):
        op.create_index("ix_ui_exploration_sessions_model_config_id", "ui_exploration_sessions", ["model_config_id"])
    Base.metadata.create_all(bind=op.get_bind(), tables=[Base.metadata.tables["ui_exploration_turns"]], checkfirst=True)


def downgrade() -> None:
    op.drop_table("ui_exploration_turns")
    inspector = sa.inspect(op.get_bind())
    index = next((item for item in inspector.get_indexes("ui_exploration_sessions") if item["column_names"] == ["model_config_id"]), None)
    if index:
        op.drop_index(index["name"], table_name="ui_exploration_sessions")
    foreign_key = next((item for item in inspector.get_foreign_keys("ui_exploration_sessions") if item["constrained_columns"] == ["model_config_id"]), None)
    if foreign_key and foreign_key["name"]:
        op.drop_constraint(foreign_key["name"], "ui_exploration_sessions", type_="foreignkey")
    op.drop_column("ui_exploration_sessions", "model_config_id")
    op.drop_column("ui_exploration_sessions", "requirement_test_point_ids")

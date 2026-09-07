"""add confirmed structured requirement test cases

Revision ID: 0019
Revises: 0018
"""
from alembic import op
import sqlalchemy as sa

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("requirement_test_cases"):
        op.create_table("requirement_test_cases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_version_id", sa.String(36), sa.ForeignKey("document_versions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("requirement_module_id", sa.String(36), sa.ForeignKey("requirement_modules.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("review_id", sa.String(36), sa.ForeignKey("requirement_reviews.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model_config_id", sa.String(36), sa.ForeignKey("model_configs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("model_config_revision_id", sa.String(36), sa.ForeignKey("model_config_revisions.id", ondelete="RESTRICT")),
        sa.Column("llm_call_id", sa.String(36), sa.ForeignKey("llm_call_records.id", ondelete="RESTRICT")),
        sa.Column("stable_key", sa.String(128), nullable=False), sa.Column("title", sa.String(255), nullable=False),
        sa.Column("case_type", sa.String(24), nullable=False), sa.Column("priority", sa.String(8), nullable=False, server_default="P2"),
        sa.Column("preconditions", sa.JSON(), nullable=False), sa.Column("test_data_refs", sa.JSON(), nullable=False), sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("expected_result", sa.Text(), nullable=False), sa.Column("status", sa.String(24), nullable=False, server_default="generating"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"), sa.Column("error_code", sa.String(64)), sa.Column("error_message", sa.Text()),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False), sa.Column("reviewed_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT")), sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("project_id", "review_id", "stable_key", name="uq_requirement_test_case_key"),
        )
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("requirement_test_cases")}
    if "ix_requirement_test_cases_project_id" not in indexes:
        op.create_index("ix_requirement_test_cases_project_id", "requirement_test_cases", ["project_id"])
    if "ix_requirement_test_cases_status" not in indexes:
        op.create_index("ix_requirement_test_cases_status", "requirement_test_cases", ["status"])
    for table in ("api_scenario_candidates", "test_scenarios", "ui_exploration_sessions"):
        columns = {item["name"] for item in sa.inspect(bind).get_columns(table)}
        if "requirement_test_case_ids" not in columns:
            op.add_column(table, sa.Column("requirement_test_case_ids", sa.JSON(), nullable=False, server_default="[]"))
            op.alter_column(table, "requirement_test_case_ids", server_default=None)


def downgrade() -> None:
    op.drop_column("api_scenario_candidates", "requirement_test_case_ids")
    op.drop_column("test_scenarios", "requirement_test_case_ids")
    op.drop_column("ui_exploration_sessions", "requirement_test_case_ids")
    op.drop_index("ix_requirement_test_cases_status", table_name="requirement_test_cases")
    op.drop_index("ix_requirement_test_cases_project_id", table_name="requirement_test_cases")
    op.drop_table("requirement_test_cases")

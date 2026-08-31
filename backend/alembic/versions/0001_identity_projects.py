"""identity projects environments

Revision ID: 0001
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("users", sa.Column("id", sa.String(36), primary_key=True), sa.Column("username", sa.String(64), nullable=False), sa.Column("password_hash", sa.String(256), nullable=False), sa.Column("name", sa.String(64), nullable=False), sa.Column("email", sa.String(255), nullable=False), sa.Column("system_role", sa.String(16), nullable=False), sa.Column("is_active", sa.Boolean(), nullable=False), sa.Column("last_login_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.UniqueConstraint("username"))
    op.create_index("ix_users_username", "users", ["username"])
    op.create_table("projects", sa.Column("id", sa.String(36), primary_key=True), sa.Column("name", sa.String(128), nullable=False), sa.Column("description", sa.Text(), nullable=False), sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False), sa.Column("status", sa.String(16), nullable=False), sa.Column("revision", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_projects_owner_id", "projects", ["owner_id"]); op.create_index("ix_projects_status", "projects", ["status"]); op.create_index("ix_projects_name", "projects", ["name"])
    op.create_table("project_members", sa.Column("id", sa.String(36), primary_key=True), sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False), sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("role", sa.String(16), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.UniqueConstraint("project_id", "user_id", name="uq_project_member"))
    op.create_index("ix_project_members_project_id", "project_members", ["project_id"]); op.create_index("ix_project_members_user_id", "project_members", ["user_id"])
    op.create_table("test_environments", sa.Column("id", sa.String(36), primary_key=True), sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False), sa.Column("name", sa.String(64), nullable=False), sa.Column("base_url", sa.String(1024), nullable=False), sa.Column("variables", sa.JSON(), nullable=False), sa.Column("global_headers", sa.JSON(), nullable=False), sa.Column("secret_refs", sa.JSON(), nullable=False), sa.Column("is_enabled", sa.Boolean(), nullable=False), sa.Column("revision", sa.Integer(), nullable=False), sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.UniqueConstraint("project_id", "name", name="uq_environment_name"))
    op.create_index("ix_test_environments_project_id", "test_environments", ["project_id"])


def downgrade() -> None:
    op.drop_table("test_environments"); op.drop_table("project_members"); op.drop_table("projects"); op.drop_table("users")

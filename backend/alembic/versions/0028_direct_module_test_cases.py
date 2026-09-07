"""allow requirement test cases to be generated directly from confirmed modules

Revision ID: 0028
Revises: 0027
"""

from alembic import op
import sqlalchemy as sa


revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 历史用例继续指向评审；新流程以 NULL 表示“直接由已确认模块生成”。
    op.drop_constraint("requirement_test_cases_review_id_fkey", "requirement_test_cases", type_="foreignkey")
    op.alter_column("requirement_test_cases", "review_id", existing_type=sa.String(36), nullable=True)
    op.create_foreign_key("requirement_test_cases_review_id_fkey", "requirement_test_cases", "requirement_reviews", ["review_id"], ["id"], ondelete="SET NULL")
    op.drop_constraint("uq_requirement_test_case_key", "requirement_test_cases", type_="unique")
    # 部分唯一索引只约束 review_id 为空的新记录，避免阻断历史评审的版本留存。
    op.create_index("ux_requirement_test_case_module_key", "requirement_test_cases", ["project_id", "requirement_module_id", "stable_key"], unique=True, postgresql_where=sa.text("review_id IS NULL"))


def downgrade() -> None:
    op.drop_index("ux_requirement_test_case_module_key", table_name="requirement_test_cases")
    op.drop_constraint("requirement_test_cases_review_id_fkey", "requirement_test_cases", type_="foreignkey")
    # 无法安全地将新流程记录回填为历史评审，因此降级保持 review_id 可空。
    op.create_foreign_key("requirement_test_cases_review_id_fkey", "requirement_test_cases", "requirement_reviews", ["review_id"], ["id"], ondelete="CASCADE")
    op.create_unique_constraint("uq_requirement_test_case_key", "requirement_test_cases", ["project_id", "review_id", "stable_key"])

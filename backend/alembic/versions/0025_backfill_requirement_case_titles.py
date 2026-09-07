"""backfill contextual titles for legacy test case generation rows

Revision ID: 0025
Revises: 0024
"""
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE requirement_test_cases AS test_case
        SET title = requirement_module.name || ' · ' ||
            CASE WHEN test_case.status = 'failed' THEN '测试用例生成失败' ELSE '正在生成测试用例' END
        FROM requirement_modules AS requirement_module
        WHERE test_case.requirement_module_id = requirement_module.id
          AND test_case.title = '正在生成测试用例候选'
    """)


def downgrade() -> None:
    pass

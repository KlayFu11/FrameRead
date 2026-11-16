from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # S0 显式保存未解析引用为 SQL NULL；S1 创建目标表时补充外键约束。
    op.execute("""
        ALTER TABLE tasks
            ADD COLUMN source_id uuid NULL,
            ADD COLUMN snapshot_id uuid NULL,
            ADD COLUMN provider_revision_id uuid NULL,
            ADD COLUMN asr_revision_id uuid NULL
    """)


def downgrade() -> None:
    raise NotImplementedError

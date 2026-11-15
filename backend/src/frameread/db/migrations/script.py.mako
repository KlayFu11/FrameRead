# ${message}
from alembic import op

${imports if imports else ""}
revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = None
depends_on = None


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    # 不提供破坏性 downgrade（SPEC §19）
    raise NotImplementedError

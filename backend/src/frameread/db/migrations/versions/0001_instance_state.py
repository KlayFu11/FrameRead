# S0：实例状态单例与通用 updated_at 触发器
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

APP_ROLE = "frameread_app"


def upgrade() -> None:
    # updated_at 由触发器统一维护，业务代码不设置（Q9）
    op.execute(
        """
        CREATE FUNCTION frameread_touch_updated_at() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            NEW.updated_at := clock_timestamp();
            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE TABLE instance_state (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            deleted_at timestamptz NULL,
            version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
            singleton_key smallint NOT NULL UNIQUE CHECK (singleton_key = 1),
            installation_id uuid NOT NULL,
            instance_epoch uuid NOT NULL,
            restore_state text NOT NULL
                CHECK (restore_state IN ('normal', 'backup_image', 'restoring', 'review_required')),
            restore_id uuid NULL,
            restore_confirmed_at timestamptz NULL,
            restore_audit_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            maintenance_mode text NOT NULL CHECK (maintenance_mode IN ('normal', 'draining', 'frozen')),
            policy_json jsonb NOT NULL,
            config_revision bigint NOT NULL CHECK (config_revision > 0),
            last_backup_id uuid NULL,
            root_key_check bytea NOT NULL CHECK (octet_length(root_key_check) = 32)
        )
        """
    )
    op.execute(
        "CREATE TRIGGER instance_state_touch BEFORE UPDATE ON instance_state "
        "FOR EACH ROW EXECUTE FUNCTION frameread_touch_updated_at()"
    )
    # 应用角色只读写既有单例，不插入、不删除；单例由 migrate 初始化
    op.execute(f"GRANT SELECT, UPDATE ON instance_state TO {APP_ROLE}")
    op.execute(f"GRANT SELECT ON alembic_version TO {APP_ROLE}")


def downgrade() -> None:
    # 不提供破坏性 downgrade（SPEC §19）
    raise NotImplementedError

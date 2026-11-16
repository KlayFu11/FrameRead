from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    LargeBinary,
    MetaData,
    SmallInteger,
    Table,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()

# 数据库角色名：迁移按表授予应用角色最小 DML 权限
MIGRATE_ROLE = "frameread_migrate"
APP_ROLE = "frameread_app"


def common_columns() -> list[Column[object]]:
    """所有表共享的通用列（SPEC §6，U2）。"""
    return [
        Column("id", Uuid, primary_key=True, server_default=text("gen_random_uuid()")),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")),
        Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")),
        Column("deleted_at", DateTime(timezone=True), nullable=True),
        Column("version", BigInteger, nullable=False, server_default=text("1")),
    ]


instance_state = Table(
    "instance_state",
    metadata,
    *common_columns(),
    Column("singleton_key", SmallInteger, nullable=False),
    Column("installation_id", Uuid, nullable=False),
    Column("instance_epoch", Uuid, nullable=False),
    Column("restore_state", Text, nullable=False),
    Column("restore_id", Uuid, nullable=True),
    Column("restore_confirmed_at", DateTime(timezone=True), nullable=True),
    Column("restore_audit_json", JSONB, nullable=False),
    Column("maintenance_mode", Text, nullable=False),
    Column("policy_json", JSONB, nullable=False),
    Column("config_revision", BigInteger, nullable=False),
    Column("last_backup_id", Uuid, nullable=True),
    Column("root_key_check", LargeBinary, nullable=False),
)

admin_sessions = Table(
    "admin_sessions",
    metadata,
    *common_columns(),
    Column("token_hash", LargeBinary, nullable=False, unique=True),
    Column("csrf_hash", LargeBinary, nullable=False),
    Column("credential_generation", Text, nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False, index=True),
    Column("last_seen_at", DateTime(timezone=True), nullable=False),
)

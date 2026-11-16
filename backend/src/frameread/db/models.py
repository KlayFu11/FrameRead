from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Integer,
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

tasks = Table(
    "tasks",
    metadata,
    *common_columns(),
    Column("kind", Text, nullable=False),
    Column("pool", Text, nullable=False),
    Column("intent", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("stage", Text, nullable=True),
    Column("accepted_instance_epoch", Uuid, nullable=False),
    Column("operation_scope", Text, nullable=False),
    Column("idempotency_key", Uuid, nullable=False),
    Column("request_digest", Text, nullable=False),
    Column("effective_input_json", JSONB, nullable=False),
    Column("input_hash", Text, nullable=False),
    Column("source_id", Uuid, nullable=True),
    Column("snapshot_id", Uuid, nullable=True),
    Column("provider_revision_id", Uuid, nullable=True),
    Column("asr_revision_id", Uuid, nullable=True),
    Column("retry_of_task_id", Uuid, nullable=True),
    Column("deadline_at", DateTime(timezone=True), nullable=False),
    Column("not_before_at", DateTime(timezone=True), nullable=False),
    Column("admission_class", Text, nullable=False),
    Column("dispatch_generation", Integer, nullable=False),
    Column("attempt_no", Integer, nullable=False),
    Column("fence", BigInteger, nullable=False),
    Column("lease_token", Uuid, nullable=True),
    Column("lease_until", DateTime(timezone=True), nullable=True),
    Column("worker_id", Text, nullable=True),
    Column("cancel_requested_at", DateTime(timezone=True), nullable=True),
    Column("state_revision", BigInteger, nullable=False),
    Column("event_seq", BigInteger, nullable=False),
    Column("progress_json", JSONB, nullable=False),
    Column("budget_json", JSONB, nullable=False),
    Column("reserved_usage_json", JSONB, nullable=False),
    Column("known_usage_json", JSONB, nullable=False),
    Column("result_json", JSONB(none_as_null=True), nullable=True),
    Column("error_json", JSONB(none_as_null=True), nullable=True),
    Column("restore_original_json", JSONB(none_as_null=True), nullable=True),
)

task_outbox = Table(
    "task_outbox",
    metadata,
    *common_columns(),
    Column("task_id", Uuid, nullable=False),
    Column("instance_epoch", Uuid, nullable=False),
    Column("generation", Integer, nullable=False),
    Column("queue", Text, nullable=False),
    Column("available_at", DateTime(timezone=True), nullable=False),
    Column("claim_token", Uuid, nullable=True),
    Column("claim_until", DateTime(timezone=True), nullable=True),
    Column("delivery_status", Text, nullable=False),
    Column("publish_attempts", Integer, nullable=False),
    Column("delivered_at", DateTime(timezone=True), nullable=True),
    Column("last_error_code", Text, nullable=True),
    Column("last_publish_at", DateTime(timezone=True), nullable=True),
)

task_events = Table(
    "task_events",
    metadata,
    *common_columns(),
    Column("task_id", Uuid, nullable=False),
    Column("seq", BigInteger, nullable=False),
    Column("state_revision", BigInteger, nullable=False),
    Column("instance_epoch", Uuid, nullable=False),
    Column("event_type", Text, nullable=False),
    Column("payload_json", JSONB, nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
)

resource_slots = Table(
    "resource_slots",
    metadata,
    *common_columns(),
    Column("resource_key", Text, nullable=False),
    Column("slot_no", Integer, nullable=False),
    Column("assigned_task_id", Uuid, nullable=True),
    Column("assigned_fence", BigInteger, nullable=True),
    Column("owner_token", Uuid, nullable=True),
    Column("lease_until", DateTime(timezone=True), nullable=True),
    Column("slot_state", Text, nullable=False),
)

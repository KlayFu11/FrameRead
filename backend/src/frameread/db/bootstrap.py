import hmac
import uuid
from dataclasses import dataclass
from importlib.resources import files

import structlog
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, func, insert, select, text
from sqlalchemy.exc import DBAPIError

from frameread.db.models import instance_state
from frameread.domain.gate import MaintenanceMode, RestoreState
from frameread.domain.policy import ResourcePolicy
from frameread.security.crypto import ROOT_KEY_BYTES, KeyRing, root_key_check
from frameread.settings import DeploymentScale, connection_budget

# 迁移 advisory lock 的固定键（"FRMG"），等待上限 60s（D04）
MIGRATION_LOCK_KEY = 0x46524D47
MIGRATION_LOCK_TIMEOUT = "60s"
_log = structlog.get_logger()


class StartupError(Exception):
    """启动前置条件不满足；消息不含密钥或连接串。"""


class FatalStartupError(StartupError):
    """不可通过重试恢复：例如根密钥与实例不符（SPEC §19）。"""


class SchemaNotReady(StartupError):
    """数据库 head 与代码期望不一致或实例未初始化；可等待部署者完成迁移。"""


def alembic_config(connection: Connection | None = None) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(files("frameread.db") / "migrations"))
    if connection is not None:
        cfg.attributes["connection"] = connection
    return cfg


def expected_head() -> str:
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    if head is None:
        raise RuntimeError("迁移脚本缺少 head")
    return head


def database_head(conn: Connection) -> str | None:
    return MigrationContext.configure(conn).get_current_revision()


def parse_root_key(hex_text: str) -> bytes:
    try:
        key = bytes.fromhex(hex_text)
    except ValueError:
        raise FatalStartupError("MASTER_KEY_FILE 内容不是十六进制") from None
    if len(key) != ROOT_KEY_BYTES:
        raise FatalStartupError(f"MASTER_KEY_FILE 长度不是 {ROOT_KEY_BYTES} 字节")
    return key


def check_connection_budget(conn: Connection, scale: DeploymentScale) -> None:
    max_connections = int(conn.execute(text("SHOW max_connections")).scalar_one())
    required = connection_budget(scale)
    if required > max_connections:
        raise StartupError(f"连接预算 {required} 超过 max_connections {max_connections}")


def _initialize_instance(conn: Connection, policy: ResourcePolicy, root_key: bytes) -> None:
    c = instance_state.c
    row = conn.execute(select(c.root_key_check, c.policy_json).where(c.singleton_key == 1).with_for_update()).first()
    if row is None:
        conn.execute(
            insert(instance_state).values(
                singleton_key=1,
                installation_id=uuid.uuid4(),
                instance_epoch=uuid.uuid4(),
                restore_state=RestoreState.NORMAL.value,
                restore_audit_json={},
                maintenance_mode=MaintenanceMode.NORMAL.value,
                policy_json=policy.model_dump(mode="json"),
                config_revision=1,
                root_key_check=root_key_check(root_key),
            )
        )
        _log.info("instance_initialized")
    else:
        if not hmac.compare_digest(bytes(row.root_key_check), root_key_check(root_key)):
            raise FatalStartupError("根密钥与已有实例不符，拒绝继续")
        if row.policy_json != policy.model_dump(mode="json"):
            # policy_json 是运行时唯一来源，settings.toml 只提供初始值（Q14）
            _log.warning("policy_differs_from_settings")
    conn.commit()


def run_migrations(conn: Connection, *, scale: DeploymentScale, policy: ResourcePolicy, root_key: bytes) -> None:
    """持 advisory lock 执行迁移并在空库初始化实例单例（Q7、D04）。"""
    check_connection_budget(conn, scale)
    conn.commit()
    conn.execute(text(f"SET lock_timeout = '{MIGRATION_LOCK_TIMEOUT}'"))
    try:
        conn.execute(select(func.pg_advisory_lock(MIGRATION_LOCK_KEY)))
    except DBAPIError as exc:
        raise StartupError("等待迁移锁超时") from exc
    conn.execute(text("RESET lock_timeout"))
    conn.commit()
    try:
        command.upgrade(alembic_config(conn), "head")
        conn.commit()
        _initialize_instance(conn, policy, root_key)
    finally:
        conn.rollback()
        conn.execute(select(func.pg_advisory_unlock(MIGRATION_LOCK_KEY)))
        conn.commit()


@dataclass(frozen=True)
class RuntimeIdentity:
    installation_id: uuid.UUID
    instance_epoch: uuid.UUID
    keyring: KeyRing


def verify_startup(conn: Connection, root_key: bytes) -> RuntimeIdentity:
    """启动顺序：校验 head → 读实例 → 比对 root_key_check → 派生子密钥（E7）。"""
    head = database_head(conn)
    if head != expected_head():
        raise SchemaNotReady("数据库 migration head 与代码期望不一致")
    c = instance_state.c
    row = conn.execute(
        select(c.installation_id, c.instance_epoch, c.root_key_check).where(c.singleton_key == 1)
    ).first()
    conn.rollback()
    if row is None:
        raise SchemaNotReady("实例尚未初始化")
    if not hmac.compare_digest(bytes(row.root_key_check), root_key_check(root_key)):
        raise FatalStartupError("根密钥与已有实例不符，拒绝启动")
    return RuntimeIdentity(row.installation_id, row.instance_epoch, KeyRing(root_key, row.installation_id))

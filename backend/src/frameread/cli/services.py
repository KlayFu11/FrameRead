import json
import os
import signal
import time
from pathlib import Path
from types import FrameType

import structlog
import typer
from alembic.util.exc import CommandError
from sqlalchemy.exc import DBAPIError

from frameread.api.admin_app import build_app
from frameread.api.sessions import cleanup_expired_sessions
from frameread.db.bootstrap import (
    FatalStartupError,
    StartupError,
    parse_root_key,
    run_migrations,
    verify_startup,
)
from frameread.db.engine import make_engine
from frameread.db.uow import run_transaction, sqlstate_of
from frameread.observability.liveness import DEFAULT_HEARTBEAT_DIR, HEARTBEAT_DIR_ENV, touch_heartbeat
from frameread.observability.logging import configure_logging
from frameread.services.admission import sync_execution_slots
from frameread.settings import (
    CONTROL_CONNECTIONS,
    WORKER_CHILD_CONNECTIONS,
    ConfigError,
    MigrateSecrets,
    ServiceSecrets,
    load_config,
    load_secrets,
)

_TICK_SECONDS = 5.0
_log = structlog.get_logger()

openapi_app = typer.Typer(no_args_is_help=True, help="接口契约导出")
worker_app = typer.Typer(no_args_is_help=True, help="后台 Worker 进程")
control_app = typer.Typer(no_args_is_help=True, help="控制进程")


def migrate() -> None:
    """持迁移锁执行 Alembic 升级，并在空库初始化实例单例。"""
    configure_logging()
    try:
        config = load_config()
        secrets = load_secrets(MigrateSecrets)
        root_key = parse_root_key(secrets.secret("master_key_file"))
        engine = make_engine(secrets.secret("database_dsn_file"), pool_size=1, pool_timeout=10)
        try:
            with engine.connect() as conn:
                run_migrations(
                    conn,
                    scale=config.deployment,
                    policy=config.policy,
                    root_key=root_key,
                    after_initialize=sync_execution_slots,
                )
        finally:
            engine.dispose()
    except (ConfigError, StartupError) as exc:
        _log.error("migrate_failed", error_code=type(exc).__name__)
        typer.echo(f"迁移失败：{exc}", err=True)
        raise typer.Exit(1) from None
    except (DBAPIError, CommandError) as exc:
        # 只报告 SQLSTATE，不回显 SQL 或连接信息；数据库保持失败前状态（SPEC §19）
        sqlstate = sqlstate_of(exc)
        _log.exception("migrate_failed", error_code=sqlstate or type(exc).__name__)
        typer.echo(f"迁移失败：数据库错误 {sqlstate or type(exc).__name__}，schema 未变更", err=True)
        raise typer.Exit(1) from None
    _log.info("migrate_completed")


@openapi_app.command("export")
def export_openapi(
    app_name: str = typer.Option("admin", "--app", help="目前只有 admin；public 在 S7 加入"),
    out: Path = typer.Option(..., "--out", help="输出的 OpenAPI JSON 路径"),
) -> None:
    if app_name != "admin":
        typer.echo("未知 app", err=True)
        raise typer.Exit(2)
    spec = build_app().openapi()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(spec, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _run_service(name: str, pool_size: int) -> None:
    """S0 占位进程：完成启动校验并维持存活心跳；业务循环在后续 Ticket 接入。"""
    configure_logging()
    config = load_config()
    secrets = load_secrets(ServiceSecrets)
    root_key = parse_root_key(secrets.secret("master_key_file"))
    heartbeat_dir = Path(os.environ.get(HEARTBEAT_DIR_ENV, DEFAULT_HEARTBEAT_DIR))
    engine = make_engine(
        secrets.secret("database_dsn_file"), pool_size=pool_size, pool_timeout=config.runtime.pool_timeout_seconds
    )
    stopping = False

    def stop(_signum: int, _frame: FrameType | None) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    verified = False
    next_session_cleanup = 0.0
    try:
        while not stopping:
            touch_heartbeat(heartbeat_dir, name)
            if not verified:
                try:
                    with engine.connect() as conn:
                        identity = verify_startup(conn, root_key)
                    verified = True
                    _log.info("startup_verified", worker_id=name, epoch=str(identity.instance_epoch))
                except FatalStartupError:
                    _log.critical("startup_fatal", worker_id=name)
                    raise typer.Exit(1) from None
                except (StartupError, DBAPIError, OSError):
                    _log.warning("startup_not_ready", worker_id=name)
            if verified and name == "control" and time.monotonic() >= next_session_cleanup:
                run_transaction(engine, cleanup_expired_sessions)
                next_session_cleanup = time.monotonic() + 24 * 60 * 60
                _log.info("sessions_cleaned", worker_id=name)
            time.sleep(_TICK_SECONDS)
    finally:
        engine.dispose()


@worker_app.command("run")
def worker_run() -> None:
    _run_service("worker", WORKER_CHILD_CONNECTIONS)


@control_app.command("run")
def control_run() -> None:
    _run_service("control", CONTROL_CONNECTIONS)


@control_app.command("cleanup-sessions")
def control_cleanup_sessions() -> None:
    configure_logging()
    config = load_config()
    secrets = load_secrets(ServiceSecrets)
    engine = make_engine(
        secrets.secret("database_dsn_file"), pool_size=1, pool_timeout=config.runtime.pool_timeout_seconds
    )
    try:
        with engine.connect() as conn:
            verify_startup(conn, parse_root_key(secrets.secret("master_key_file")))
        run_transaction(engine, cleanup_expired_sessions)
    finally:
        engine.dispose()
    _log.info("sessions_cleaned")

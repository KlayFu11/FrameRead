from collections.abc import Callable

from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from frameread.db.bootstrap import StartupError, parse_root_key, verify_startup
from frameread.db.engine import make_engine
from frameread.db.uow import CommitOutcomeUnknown, UnitOfWork, run_transaction
from frameread.settings import CliSecrets, ConfigError, load_secrets

CLI_POOL_SIZE = 1
CLI_POOL_TIMEOUT_SECONDS = 5.0


def run_database_transaction[T](fn: Callable[[UnitOfWork], T]) -> T:
    """使用应用 DML 角色运行一个短 sync UoW，不加载服务或 settings 配置。"""
    secrets = load_secrets(CliSecrets)
    engine: Engine = make_engine(
        secrets.secret("database_dsn_file"),
        pool_size=CLI_POOL_SIZE,
        pool_timeout=CLI_POOL_TIMEOUT_SECONDS,
    )
    try:
        with engine.connect() as conn:
            verify_startup(conn, parse_root_key(secrets.secret("master_key_file")))
        return run_transaction(engine, fn)
    finally:
        engine.dispose()


def is_dependency_error(exc: BaseException) -> bool:
    return isinstance(exc, (ConfigError, StartupError, SQLAlchemyError, CommitOutcomeUnknown, OSError))

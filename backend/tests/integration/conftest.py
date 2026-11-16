import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

from frameread.db.engine import make_engine
from frameread.db.models import APP_ROLE, MIGRATE_ROLE
from frameread.domain.policy import ResourcePolicy
from frameread.settings import DeploymentScale

# 集成测试连接真实 PostgreSQL；未配置时直接失败，不跳过
PG_URL_ENV = "FRAMEREAD_TEST_PG_URL"
REDIS_URL_ENV = "FRAMEREAD_TEST_REDIS_URL"
ROLE_PASSWORD = "integration-test-only"
ROOT_KEY = bytes(range(32))
POLICY = ResourcePolicy.model_validate({"pools": {"video": {"execution_slots": 2, "waiting_slots": 4}}})
SCALE = DeploymentScale()


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"集成测试需要环境变量 {name}")
    return value


@pytest.fixture(scope="session")
def superuser_engine() -> Iterator[Engine]:
    engine = create_engine(_required_env(PG_URL_ENV), isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        # 与 deploy 的 postgres initdb 脚本创建相同的两个角色
        for role in (MIGRATE_ROLE, APP_ROLE):
            exists = conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": role}).first()
            if not exists:
                conn.execute(text(f"CREATE ROLE {role} LOGIN PASSWORD '{ROLE_PASSWORD}'"))
    yield engine
    engine.dispose()


@dataclass(frozen=True)
class TestDatabase:
    name: str
    migrate_dsn: str
    app_dsn: str
    superuser_dsn: str

    def migrate_engine(self) -> Engine:
        return make_engine(self.migrate_dsn, pool_size=2, pool_timeout=5)

    def app_engine(self) -> Engine:
        return make_engine(self.app_dsn, pool_size=4, pool_timeout=5)


def _dsn(base: str, *, user: str | None, password: str | None, database: str) -> str:
    url = make_url(base).set(database=database)
    if user is not None:
        url = url.set(username=user, password=password)
    return url.render_as_string(hide_password=False)


@pytest.fixture
def closing_port() -> Iterator[int]:
    """接受连接后立即关闭的本地端口：确定地模拟“依赖已停止”，不受平台拒绝连接耗时影响。"""
    import socket
    import threading

    server = socket.create_server(("127.0.0.1", 0))
    server.settimeout(0.2)
    stop = threading.Event()

    def serve() -> None:
        while not stop.is_set():
            try:
                conn, _ = server.accept()
            except TimeoutError:
                continue
            conn.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    yield server.getsockname()[1]
    stop.set()
    thread.join()
    server.close()


def _create_database(superuser_engine: Engine, template: str | None = None) -> TestDatabase:
    name = f"fr_test_{uuid.uuid4().hex[:12]}"
    source = f" TEMPLATE {template}" if template else ""
    with superuser_engine.connect() as conn:
        conn.execute(text(f"CREATE DATABASE {name} OWNER {MIGRATE_ROLE}{source}"))
        conn.execute(text(f"GRANT CONNECT ON DATABASE {name} TO {APP_ROLE}"))
    base = superuser_engine.url.render_as_string(hide_password=False)
    return TestDatabase(
        name=name,
        migrate_dsn=_dsn(base, user=MIGRATE_ROLE, password=ROLE_PASSWORD, database=name),
        app_dsn=_dsn(base, user=APP_ROLE, password=ROLE_PASSWORD, database=name),
        superuser_dsn=_dsn(base, user=None, password=None, database=name),
    )


def _drop_database(superuser_engine: Engine, db: TestDatabase) -> None:
    with superuser_engine.connect() as conn:
        conn.execute(text(f"DROP DATABASE {db.name} WITH (FORCE)"))


@pytest.fixture
def fresh_db(superuser_engine: Engine) -> Iterator[TestDatabase]:
    """未迁移的空库：用于迁移本身的测试。"""
    db = _create_database(superuser_engine)
    yield db
    _drop_database(superuser_engine, db)


@pytest.fixture(scope="session")
def template_db(superuser_engine: Engine) -> Iterator[TestDatabase]:
    """每个测试会话迁移一次的模板库（D38）；模板不被测试直接使用。"""
    from frameread.db.bootstrap import run_migrations
    from frameread.services.admission import sync_execution_slots

    db = _create_database(superuser_engine)
    engine = db.migrate_engine()
    with engine.connect() as conn:
        run_migrations(conn, scale=SCALE, policy=POLICY, root_key=ROOT_KEY, after_initialize=sync_execution_slots)
    engine.dispose()
    yield db
    _drop_database(superuser_engine, db)


@pytest.fixture
def migrated_db(superuser_engine: Engine, template_db: TestDatabase) -> Iterator[TestDatabase]:
    """从模板复制的已迁移独立库：每个测试拿到同一初始状态，互不可见（D38）。"""
    db = _create_database(superuser_engine, template=template_db.name)
    yield db
    _drop_database(superuser_engine, db)

import os
import tomllib
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from frameread.domain.policy import ResourcePolicy

SETTINGS_ENV = "FRAMEREAD_SETTINGS"
DEFAULT_SETTINGS_PATH = Path("settings.toml")

# 每进程连接池初始值（SPEC §7，U3）
API_ADMIN_CONNECTIONS = 5
WORKER_CHILD_CONNECTIONS = 2
CONTROL_CONNECTIONS = 3
OPS_RESERVED_CONNECTIONS = 5


class ConfigError(Exception):
    """配置缺失或格式错误；消息只含配置项名，不含文件内容。"""


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class DeploymentScale(_Section):
    api_admin_instances: int = Field(default=1, ge=1)
    worker_concurrency: int = Field(default=2, ge=1)
    control_instances: int = Field(default=1, ge=1)


class AdminConfig(_Section):
    origins: list[str] = Field(min_length=1)
    share_base_url: str | None = None

    @field_validator("origins")
    @classmethod
    def validate_origins(cls, values: list[str]) -> list[str]:
        for value in values:
            try:
                parts = urlsplit(value)
                port = parts.port
            except ValueError:
                raise ValueError("admin.origins 格式错误") from None
            if (
                parts.scheme not in ("http", "https")
                or not parts.hostname
                or parts.username is not None
                or parts.password is not None
                or parts.path
                or parts.query
                or parts.fragment
                or parts.netloc != parts.netloc.lower()
                or port == 0
            ):
                raise ValueError("admin.origins 必须是规范的精确 Origin")
            if parts.scheme == "http" and parts.hostname not in ("localhost", "127.0.0.1", "::1"):
                raise ValueError("非 loopback 管理 Origin 必须使用 https")
        if len(set(values)) != len(values):
            raise ValueError("admin.origins 不得重复")
        return values


class RuntimeConfig(_Section):
    pool_timeout_seconds: float = Field(default=5.0, gt=0)


class AppConfig(_Section):
    """settings.toml 中的非敏感配置；policy 只在空库初始化时写入 policy_json。"""

    admin: AdminConfig
    policy: ResourcePolicy
    deployment: DeploymentScale = DeploymentScale()
    runtime: RuntimeConfig = RuntimeConfig()


def load_config(path: Path | None = None) -> AppConfig:
    path = path or Path(os.environ.get(SETTINGS_ENV, DEFAULT_SETTINGS_PATH))
    try:
        with path.open("rb") as f:
            raw = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"{SETTINGS_ENV} 指向的配置文件无法读取或格式错误") from exc
    try:
        return AppConfig.model_validate(raw)
    except ValidationError as exc:
        fields = sorted({".".join(str(p) for p in e["loc"]) for e in exc.errors()})
        raise ConfigError(f"settings.toml 校验失败: {fields}") from None


def read_secret(path: Path, setting_name: str) -> str:
    try:
        value = path.read_text(encoding="utf-8").removesuffix("\n")
    except OSError:
        raise ConfigError(f"{setting_name} 指向的文件不可读") from None
    if not value:
        raise ConfigError(f"{setting_name} 指向的文件为空")
    return value


def connection_budget(scale: DeploymentScale) -> int:
    return (
        scale.api_admin_instances * API_ADMIN_CONNECTIONS
        + scale.worker_concurrency * WORKER_CHILD_CONNECTIONS
        + scale.control_instances * CONTROL_CONNECTIONS
        + OPS_RESERVED_CONNECTIONS
    )


class _SecretFiles(BaseSettings):
    """各进程只声明自己需要的 *_FILE；缺失即启动失败（D01）。"""

    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    def secret(self, field: str) -> str:
        return read_secret(Path(getattr(self, field)), field.upper())


class ServiceSecrets(_SecretFiles):
    """worker 与 control：应用 DML 角色、Redis、根密钥（D01 矩阵）。"""

    database_dsn_file: str
    redis_url_file: str
    master_key_file: str


class AdminSecrets(ServiceSecrets):
    """api-admin 独占管理员密码 hash secret。"""

    admin_password_hash_file: str


class MigrateSecrets(_SecretFiles):
    database_dsn_file: str
    master_key_file: str


def load_secrets[T: _SecretFiles](cls: type[T]) -> T:
    try:
        return cls()
    except ValidationError as exc:
        names = sorted({str(e["loc"][0]).upper() for e in exc.errors()})
        raise ConfigError(f"缺少环境变量: {names}") from None

import os
import secrets as pysecrets
from pathlib import Path

import typer

from frameread.security.crypto import ROOT_KEY_BYTES

app = typer.Typer(no_args_is_help=True, help="实例密钥与连接凭据")

# Compose 内网服务名；DSN 只在 secret 文件中出现，不进入配置或日志
PG_HOST = "postgres"
PG_DB = "frameread"
REDIS_HOST = "redis"


def _password() -> str:
    return pysecrets.token_urlsafe(32)


def build_secret_files() -> dict[str, str]:
    migrate_pw, app_pw, redis_pw = _password(), _password(), _password()
    return {
        "master_key": pysecrets.token_bytes(ROOT_KEY_BYTES).hex(),
        "pg_superuser_password": _password(),
        "pg_migrate_password": migrate_pw,
        "pg_app_password": app_pw,
        "redis_password": redis_pw,
        "database_dsn_migrate": f"postgresql+psycopg://frameread_migrate:{migrate_pw}@{PG_HOST}:5432/{PG_DB}",
        "database_dsn_app": f"postgresql+psycopg://frameread_app:{app_pw}@{PG_HOST}:5432/{PG_DB}",
        "redis_url": f"redis://:{redis_pw}@{REDIS_HOST}:6379/0",
    }


@app.command("init")
def init(directory: Path = typer.Option(Path("deploy/secrets"), "--dir", help="secret 文件目录")) -> None:
    """生成根密钥与连接凭据；目录内已有任一文件时拒绝执行，不覆盖。"""
    files = build_secret_files()
    if directory.exists() and any(directory.iterdir()):
        typer.echo(f"拒绝执行：{directory} 中已有文件，不覆盖现有密钥", err=True)
        raise typer.Exit(1)
    # 目录 0700 阻止宿主机其他用户访问；文件 0644 供容器内非 root 用户经 bind mount 读取
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory.chmod(0o700)
    for name, value in files.items():
        path = directory / name
        # O_EXCL 保证并发或竞态下也不覆盖
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(value + "\n")
    typer.echo(f"已生成 {len(files)} 个 secret 文件到 {directory}")

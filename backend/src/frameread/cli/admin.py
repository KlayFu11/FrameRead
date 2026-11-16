import os
import sys
import tempfile
from pathlib import Path

import typer
from argon2 import PasswordHasher

app = typer.Typer(no_args_is_help=True, help="管理员凭据")


@app.command("set-password")
def set_password(
    out: Path = typer.Option(Path("deploy/secrets/admin_password_hash"), "--out"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    if out.exists() and not force:
        typer.echo("目标已存在；轮换密码须显式指定 --force", err=True)
        raise typer.Exit(1)
    if sys.stdin.isatty():
        first = typer.prompt("管理员密码", hide_input=True, default="", show_default=False)
        second = typer.prompt("再次输入密码", hide_input=True, default="", show_default=False)
    else:
        # Windows getpass 会绕过重定向的 stdin 读取控制台；管道输入需直接读取且不回显。
        first = sys.stdin.readline().rstrip("\r\n")
        second = sys.stdin.readline().rstrip("\r\n")
    if not first or first != second:
        typer.echo("密码不能为空且两次输入必须一致", err=True)
        raise typer.Exit(1)
    encoded = PasswordHasher().hash(first)
    out.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".admin-", dir=out.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(encoded + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        # Docker bind secret 需供非 root 的 api-admin 读取；目录限制访问范围。
        os.chmod(temporary, 0o644)
        if force:
            os.replace(temporary, out)
        else:
            # link 的排他创建保证并发设置不会覆盖另一部署者已写入的文件。
            os.link(temporary, out)
    finally:
        Path(temporary).unlink(missing_ok=True)
    typer.echo("管理员凭据已写入；重启 api-admin 后生效")

import uuid
from typing import Any

import typer
from typer import _click
from typer.core import TyperGroup

from frameread.cli import admin, maintenance, policy, secrets, services


class RequestIdTyperGroup(TyperGroup):
    """为 Click/Typer 解析阶段的用法错误补充统一 request_id。"""

    def main(self, *args: Any, standalone_mode: bool = True, **kwargs: Any) -> Any:
        kwargs["standalone_mode"] = False
        try:
            result = super().main(*args, **kwargs)
        except _click.ClickException as exc:
            typer.echo(f"{exc.format_message()}，request_id={uuid.uuid4()}", err=True)
            if standalone_mode:
                raise SystemExit(exc.exit_code) from None
            raise
        if standalone_mode:
            raise SystemExit(0 if result is None else result)
        return result


app = typer.Typer(cls=RequestIdTyperGroup, no_args_is_help=True, help="FrameRead 维护命令")
app.add_typer(secrets.app, name="secrets")
app.add_typer(admin.app, name="admin")
app.add_typer(policy.app, name="policy")
app.add_typer(maintenance.app, name="maintenance")
app.add_typer(services.openapi_app, name="openapi")
app.add_typer(services.worker_app, name="worker")
app.add_typer(services.control_app, name="control")
health_app = typer.Typer(no_args_is_help=True, help="内部进程健康检查")
app.add_typer(health_app, name="health")
app.command("migrate")(services.migrate)


@health_app.command("live")
def health_live(
    name: str = typer.Option(..., "--name"),
    max_age: float = typer.Option(30.0, "--max-age"),
) -> None:
    from frameread.observability.liveness import main

    raise typer.Exit(main(["--name", name, "--max-age", str(max_age)], prog="frameread health live"))


def run() -> None:
    app()

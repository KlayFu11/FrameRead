import typer

from frameread.cli import secrets, services

app = typer.Typer(no_args_is_help=True, help="FrameRead 维护命令")
app.add_typer(secrets.app, name="secrets")
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

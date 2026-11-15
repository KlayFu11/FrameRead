import typer

from frameread.cli import secrets, services

app = typer.Typer(no_args_is_help=True, help="FrameRead 维护命令")
app.add_typer(secrets.app, name="secrets")
app.add_typer(services.openapi_app, name="openapi")
app.add_typer(services.worker_app, name="worker")
app.add_typer(services.control_app, name="control")
app.command("migrate")(services.migrate)


def run() -> None:
    app()

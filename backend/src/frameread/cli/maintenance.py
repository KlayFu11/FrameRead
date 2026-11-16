import uuid

import typer
from sqlalchemy.exc import DBAPIError

from frameread.cli.runtime import is_dependency_error, run_database_transaction
from frameread.domain.gate import MaintenanceMode
from frameread.services.maintenance import MaintenanceChangeRejected, set_maintenance_mode

app = typer.Typer(no_args_is_help=True, help="维护模式")


def _error(message: str, *, request_id: str, exit_code: int) -> None:
    typer.echo(f"{message}，request_id={request_id}", err=True)
    raise typer.Exit(exit_code)


@app.command("set")
def set_mode(mode: str = typer.Argument(..., help="normal、draining 或 frozen")) -> None:
    request_id = str(uuid.uuid4())
    try:
        maintenance = MaintenanceMode(mode)
    except ValueError:
        _error("维护模式必须是 normal、draining 或 frozen", request_id=request_id, exit_code=2)

    try:
        run_database_transaction(lambda uow: set_maintenance_mode(uow, maintenance))
    except MaintenanceChangeRejected as exc:
        _error(str(exc), request_id=request_id, exit_code=1)
    except (DBAPIError, OSError) as exc:
        _error(f"维护模式更新失败：{type(exc).__name__}", request_id=request_id, exit_code=1)
    except Exception as exc:
        if is_dependency_error(exc):
            _error(f"维护模式更新失败：{type(exc).__name__}", request_id=request_id, exit_code=1)
        raise
    typer.echo(f"维护模式已设置为 {maintenance.value}，request_id={request_id}")

import uuid

import typer
from sqlalchemy.exc import DBAPIError

from frameread.cli.runtime import is_dependency_error, run_database_transaction
from frameread.domain.policy import Pool
from frameread.services.policy import PolicyValidationError, update_policy

app = typer.Typer(no_args_is_help=True, help="运行资源策略")


def _error(message: str, *, request_id: str, exit_code: int) -> None:
    typer.echo(f"{message}，request_id={request_id}", err=True)
    raise typer.Exit(exit_code)


@app.command("set")
def set_policy(
    pool: str = typer.Option("video", "--pool", help="策略池：video、qa 或 utility"),
    execution_slots: int | None = typer.Option(
        None, "--execution-slots", "--video-execution-slots", help="执行槽数量（默认池为 video）"
    ),
    waiting_slots: int | None = typer.Option(
        None, "--waiting-slots", "--video-waiting-slots", help="等待位数量（默认池为 video）"
    ),
    video_total_timeout_seconds: int | None = typer.Option(
        None, "--video-total-timeout-seconds", "--total-timeout-seconds", help="video 任务总期限（秒）"
    ),
    lease_seconds: int | None = typer.Option(None, "--lease-seconds", help="执行租约期限（秒）"),
    heartbeat_seconds: int | None = typer.Option(None, "--heartbeat-seconds", help="Worker 心跳周期（秒）"),
    dispatcher_batch: int | None = typer.Option(None, "--dispatcher-batch", help="dispatcher 批量大小"),
    dispatch_retry_budget: int | None = typer.Option(None, "--dispatch-retry-budget", help="投递重试预算"),
    dispatch_generation_limit: int | None = typer.Option(
        None, "--dispatch-generation-limit", help="投递 generation 上限"
    ),
    event_retention_days: int | None = typer.Option(None, "--event-retention-days", help="关键事件保留天数"),
) -> None:
    request_id = str(uuid.uuid4())
    try:
        pool_value = Pool(pool)
    except ValueError:
        _error("策略池必须是 video、qa 或 utility", request_id=request_id, exit_code=2)

    try:
        result = run_database_transaction(
            lambda uow: update_policy(
                uow,
                pool=pool_value,
                execution_slots=execution_slots,
                waiting_slots=waiting_slots,
                video_total_timeout_seconds=video_total_timeout_seconds,
                lease_seconds=lease_seconds,
                heartbeat_seconds=heartbeat_seconds,
                dispatcher_batch=dispatcher_batch,
                dispatch_retry_budget=dispatch_retry_budget,
                dispatch_generation_limit=dispatch_generation_limit,
                event_retention_days=event_retention_days,
            )
        )
    except PolicyValidationError as exc:
        _error(f"策略无效：{exc}", request_id=request_id, exit_code=2)
    except (DBAPIError, OSError) as exc:
        _error(f"策略更新失败：{type(exc).__name__}", request_id=request_id, exit_code=1)
    except Exception as exc:
        if is_dependency_error(exc):
            _error(f"策略更新失败：{type(exc).__name__}", request_id=request_id, exit_code=1)
        raise
    typer.echo(f"策略已更新，config_revision={result.config_revision}，request_id={request_id}")

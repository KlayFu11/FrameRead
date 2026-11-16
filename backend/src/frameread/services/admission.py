from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel
from sqlalchemy import Connection, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as SQLTimeoutError
from sqlalchemy.ext.asyncio import AsyncEngine

from frameread.db.models import instance_state, resource_slots, task_events, task_outbox, tasks
from frameread.db.uow import AsyncUnitOfWork, CommitOutcomeUnknown, LockMode, UnitOfWork, run_transaction_async
from frameread.domain.errors import AppError, ErrorCode
from frameread.domain.gate import GateOp
from frameread.domain.policy import Pool, ResourcePolicy

ACTIVE_STATUSES = ("queued", "running", "cancel_requested", "retry_wait")
TaskStatus = Literal["queued", "running", "cancel_requested", "retry_wait", "succeeded", "failed", "canceled"]


class TaskAccepted(BaseModel):
    task_id: UUID
    kind: str
    status: TaskStatus
    accepted_at: datetime
    deadline_at: datetime
    snapshot_url: str
    replayed: bool
    operation_scope: str


@dataclass(frozen=True)
class AdmissionRequest:
    key: UUID
    request_digest: str
    effective_input: dict[str, Any]
    kind: str = "video"
    pool: Pool = Pool.VIDEO
    intent: str = "new"
    scope: str = "video:new"
    input_hash: str | None = None
    total_timeout: timedelta | None = None
    retry_of_task_id: UUID | None = None
    budget: dict[str, Any] = field(default_factory=lambda: {"version": 1, "limits": {}})


def sync_execution_slots(uow: UnitOfWork | Connection, pool: Pool = Pool.VIDEO) -> None:
    # 入口可以传入迁移初始化事务；策略 CLI 复用已有 UoW，不开启或提交子事务。
    conn = uow.conn if isinstance(uow, UnitOfWork) else uow
    policy_json = conn.execute(
        select(instance_state.c.policy_json).where(instance_state.c.singleton_key == 1).with_for_update()
    ).scalar_one()
    capacity = ResourcePolicy.model_validate(policy_json).pools[pool].execution_slots
    key = f"execution:{pool.value}"
    for number in range(1, capacity + 1):
        conn.execute(
            pg_insert(resource_slots)
            .values(resource_key=key, slot_no=number, slot_state="active")
            .on_conflict_do_nothing(index_elements=["resource_key", "slot_no"])
        )
    c = resource_slots.c
    # 只修改实际改变的槽，重复 migrate 不推进 version。
    for active, state in ((True, "active"), (False, "retired")):
        conn.execute(
            update(resource_slots)
            .where(
                c.resource_key == key,
                (c.slot_no <= capacity) if active else (c.slot_no > capacity),
                c.slot_state != state,
            )
            .values(slot_state=state, version=c.version + 1)
        )


def _accepted(row: Any, *, replayed: bool) -> TaskAccepted:
    return TaskAccepted(
        task_id=row.id,
        kind=row.kind,
        status=row.status,
        accepted_at=row.created_at,
        deadline_at=row.deadline_at,
        snapshot_url=f"/api/v1/admin/tasks/{row.id}",
        replayed=replayed,
        operation_scope=row.operation_scope,
    )


def _operation_query(scope: str, key: UUID) -> Any:
    # 幂等身份不能因软删除失效。
    return select(tasks).where(tasks.c.operation_scope == scope, tasks.c.idempotency_key == key)


def _replay(row: Any, digest: str) -> TaskAccepted:
    if row.request_digest != digest:
        raise AppError(ErrorCode.IDEMPOTENCY_CONFLICT, task_id=row.id)
    return _accepted(row, replayed=True)


async def admit(uow: AsyncUnitOfWork, request: AdmissionRequest) -> TaskAccepted:
    instance = await uow.lock_instance(LockMode.UPDATE)
    existing = (await uow.execute(_operation_query(request.scope, request.key))).first()
    if existing is not None:
        return _replay(existing, request.request_digest)
    uow.gate.require(GateOp.ADMIT)
    capacity = instance.policy.pools[request.pool]
    c = resource_slots.c
    slot = (
        await uow.execute(
            select(c.id)
            .where(
                c.resource_key == f"execution:{request.pool.value}",
                c.slot_state == "active",
                c.deleted_at.is_(None),
                c.assigned_task_id.is_(None),
            )
            .order_by(c.slot_no)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
    ).first()
    if slot is None:
        waiting = (
            await uow.execute(
                select(func.count())
                .select_from(tasks)
                .where(
                    tasks.c.pool == request.pool.value,
                    tasks.c.admission_class == "waiting",
                    tasks.c.status.in_(ACTIVE_STATUSES),
                    tasks.c.deleted_at.is_(None),
                )
            )
        ).scalar_one()
        if waiting >= capacity.waiting_slots:
            raise AppError(ErrorCode.QUEUE_FULL)
    now = await uow.db_now()
    timeout = request.total_timeout or timedelta(seconds=instance.policy.video_total_timeout_seconds)
    task_id = uuid4()
    admission_class = "execution" if slot is not None else "waiting"
    row = (
        await uow.execute(
            insert(tasks)
            .values(
                id=task_id,
                created_at=now,
                kind=request.kind,
                pool=request.pool.value,
                intent=request.intent,
                status="queued",
                stage=None,
                accepted_instance_epoch=instance.instance_epoch,
                operation_scope=request.scope,
                idempotency_key=request.key,
                request_digest=request.request_digest,
                effective_input_json=request.effective_input,
                input_hash=request.input_hash or request.request_digest,
                retry_of_task_id=request.retry_of_task_id,
                deadline_at=now + timeout,
                not_before_at=now,
                admission_class=admission_class,
                dispatch_generation=1,
                attempt_no=0,
                fence=0,
                state_revision=1,
                event_seq=1,
                progress_json={"stage": None, "observed_at": now.isoformat()},
                budget_json=request.budget,
                reserved_usage_json={},
                known_usage_json={},
            )
            .returning(tasks)
        )
    ).one()
    await uow.execute(
        insert(task_outbox).values(
            task_id=task_id,
            instance_epoch=instance.instance_epoch,
            generation=1,
            queue="fr.video",
            available_at=now,
            delivery_status="pending" if slot is not None else "blocked",
            publish_attempts=0,
        )
    )
    await uow.execute(
        insert(task_events).values(
            task_id=task_id,
            seq=1,
            state_revision=1,
            instance_epoch=instance.instance_epoch,
            event_type="accepted",
            payload_json={"status": "queued", "stage": None, "error_code": None},
            occurred_at=now,
        )
    )
    if slot is not None:
        await uow.execute_one(
            update(resource_slots)
            .where(c.id == slot.id, c.assigned_task_id.is_(None))
            .values(
                assigned_task_id=task_id,
                assigned_fence=0,
                version=c.version + 1,
            )
        )
    return _accepted(row, replayed=False)


async def find_operation(engine: AsyncEngine, scope: str, key: UUID) -> TaskAccepted:
    try:
        async with engine.connect() as conn:
            row = (await conn.execute(_operation_query(scope, key))).first()
    except (DBAPIError, SQLTimeoutError, OSError):
        raise AppError(ErrorCode.DEPENDENCY_UNAVAILABLE) from None
    if row is None:
        raise AppError(ErrorCode.NOT_FOUND)
    return _accepted(row, replayed=True)


async def submit_admission(engine: AsyncEngine, request: AdmissionRequest) -> TaskAccepted:
    async def operation(uow: AsyncUnitOfWork) -> TaskAccepted:
        return await admit(uow, request)

    try:
        return await run_transaction_async(engine, operation)
    except CommitOutcomeUnknown:
        # 新连接只查询一次；未知结果不得重放写事务。
        try:
            async with engine.connect() as conn:
                row = (await conn.execute(_operation_query(request.scope, request.key))).first()
        except (DBAPIError, SQLTimeoutError, OSError):
            raise AppError(ErrorCode.ADMISSION_UNCONFIRMED) from None
        if row is None:
            raise AppError(ErrorCode.ADMISSION_UNCONFIRMED) from None
        return _replay(row, request.request_digest)
    except (DBAPIError, SQLTimeoutError, OSError):
        raise AppError(ErrorCode.DEPENDENCY_UNAVAILABLE) from None

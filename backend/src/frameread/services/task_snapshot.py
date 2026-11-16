import base64
import hashlib
import hmac
import json
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as SQLTimeoutError
from sqlalchemy.ext.asyncio import AsyncEngine

from frameread.db.models import instance_state, tasks
from frameread.domain.errors import AppError, ErrorCode
from frameread.domain.gate import GateOp, MaintenanceMode, RestoreState, is_allowed
from frameread.security.crypto import KeyPurpose, KeyRing
from frameread.services.admission import TaskStatus


class TaskProgress(BaseModel):
    stage: str | None
    observed_at: datetime


class TaskError(BaseModel):
    code: str
    message: str
    task_id: UUID | None = None


class TaskSnapshot(BaseModel):
    id: UUID
    kind: str
    intent: str
    status: TaskStatus
    stage: str | None
    state_revision: int
    event_seq: int
    cursor: str
    instance_epoch: UUID
    attempt_no: int
    progress: TaskProgress
    deadline_at: datetime
    cancel_requested_at: datetime | None
    result: None = None
    error: TaskError | None
    draft_summary: None = None
    allowed_actions: list[Literal["cancel"]]
    unknown_call_count: Literal[0] = 0


def snapshot_cursor(keyring: KeyRing, *, task_id: UUID, epoch: UUID, seq: int) -> str:
    payload = json.dumps(
        {"schema_version": 1, "scope": "admin", "task_id": str(task_id), "epoch": str(epoch), "seq": seq},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    signature = hmac.new(keyring.derive(KeyPurpose.CURSOR), payload, hashlib.sha256).digest()
    return ".".join(base64.urlsafe_b64encode(part).rstrip(b"=").decode() for part in (payload, signature))


async def read_snapshot(engine: AsyncEngine, task_id: UUID, keyring: KeyRing) -> TaskSnapshot:
    try:
        async with engine.connect() as conn:
            conn = await conn.execution_options(isolation_level="REPEATABLE READ")
            async with conn.begin():
                # 当前 epoch、门禁与 task 在同一个 MVCC 快照中读取，不依赖启动缓存。
                row = (
                    await conn.execute(
                        select(
                            tasks,
                            instance_state.c.instance_epoch.label("current_epoch"),
                            instance_state.c.maintenance_mode,
                            instance_state.c.restore_state,
                        )
                        .join(instance_state, instance_state.c.singleton_key == 1)
                        .where(tasks.c.id == task_id, tasks.c.deleted_at.is_(None))
                    )
                ).first()
    except (DBAPIError, SQLTimeoutError, OSError):
        raise AppError(ErrorCode.DEPENDENCY_UNAVAILABLE) from None
    if row is None:
        raise AppError(ErrorCode.NOT_FOUND)
    can_cancel = is_allowed(
        GateOp.CANCEL_REQUEST, MaintenanceMode(row.maintenance_mode), RestoreState(row.restore_state)
    )
    return TaskSnapshot(
        id=row.id,
        kind=row.kind,
        intent=row.intent,
        status=row.status,
        stage=row.stage,
        state_revision=row.state_revision,
        event_seq=row.event_seq,
        cursor=snapshot_cursor(keyring, task_id=row.id, epoch=row.current_epoch, seq=row.event_seq),
        instance_epoch=row.current_epoch,
        attempt_no=row.attempt_no,
        progress=row.progress_json,
        deadline_at=row.deadline_at,
        cancel_requested_at=row.cancel_requested_at,
        error=row.error_json,
        allowed_actions=["cancel"] if can_cancel and row.status in ("queued", "running", "retry_wait") else [],
    )

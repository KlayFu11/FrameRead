from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from sqlalchemy import update

from frameread.db.models import instance_state
from frameread.db.uow import LockMode, UnitOfWork
from frameread.domain.policy import Pool, ResourcePolicy
from frameread.services.admission import sync_execution_slots


class PolicyValidationError(ValueError):
    """CLI 提交的部分策略无法与当前策略合并为有效 ResourcePolicy。"""


@dataclass(frozen=True)
class PolicyUpdate:
    policy: ResourcePolicy
    config_revision: int


def merge_policy(
    current: ResourcePolicy,
    *,
    pool: Pool,
    execution_slots: int | None = None,
    waiting_slots: int | None = None,
    video_total_timeout_seconds: int | None = None,
    lease_seconds: int | None = None,
    heartbeat_seconds: int | None = None,
    dispatcher_batch: int | None = None,
    dispatch_retry_budget: int | None = None,
    dispatch_generation_limit: int | None = None,
    event_retention_days: int | None = None,
) -> ResourcePolicy:
    changes: dict[str, Any] = {
        name: value
        for name, value in {
            "execution_slots": execution_slots,
            "waiting_slots": waiting_slots,
        }.items()
        if value is not None
    }
    top_level = {
        name: value
        for name, value in {
            "video_total_timeout_seconds": video_total_timeout_seconds,
            "lease_seconds": lease_seconds,
            "heartbeat_seconds": heartbeat_seconds,
            "dispatcher_batch": dispatcher_batch,
            "dispatch_retry_budget": dispatch_retry_budget,
            "dispatch_generation_limit": dispatch_generation_limit,
            "event_retention_days": event_retention_days,
        }.items()
        if value is not None
    }
    if not changes and not top_level:
        raise PolicyValidationError("至少提供一个策略值")

    raw = current.model_dump(mode="json")
    pool_json = raw["pools"].get(pool.value)
    if pool_json is None:
        raise PolicyValidationError(f"当前策略未配置 pool={pool.value}")
    pool_json.update(changes)
    raw.update(top_level)
    try:
        return ResourcePolicy.model_validate(raw)
    except ValidationError as exc:
        fields = "; ".join(f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}" for error in exc.errors())
        raise PolicyValidationError(fields) from None


def update_policy(
    uow: UnitOfWork,
    *,
    pool: Pool,
    execution_slots: int | None = None,
    waiting_slots: int | None = None,
    video_total_timeout_seconds: int | None = None,
    lease_seconds: int | None = None,
    heartbeat_seconds: int | None = None,
    dispatcher_batch: int | None = None,
    dispatch_retry_budget: int | None = None,
    dispatch_generation_limit: int | None = None,
    event_retention_days: int | None = None,
) -> PolicyUpdate:
    instance = uow.lock_instance(LockMode.UPDATE)
    policy = merge_policy(
        instance.policy,
        pool=pool,
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
    c = instance_state.c
    uow.execute_one(
        update(instance_state)
        .where(c.singleton_key == 1)
        .values(
            policy_json=policy.model_dump(mode="json"),
            config_revision=c.config_revision + 1,
            version=c.version + 1,
        )
    )
    # 同一 UoW 内同步槽行；若同步失败，外层事务回滚策略与 config_revision。
    sync_execution_slots(uow, pool=pool)
    return PolicyUpdate(policy=policy, config_revision=instance.config_revision + 1)

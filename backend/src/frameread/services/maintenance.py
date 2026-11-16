from dataclasses import dataclass

from sqlalchemy import update

from frameread.db.models import instance_state
from frameread.db.uow import LockMode, UnitOfWork
from frameread.domain.gate import MaintenanceMode, RestoreState


class MaintenanceChangeRejected(ValueError):
    """维护模式切换违反 restore_state 约束。"""


@dataclass(frozen=True)
class MaintenanceUpdate:
    mode: MaintenanceMode


def set_maintenance_mode(uow: UnitOfWork, mode: MaintenanceMode) -> MaintenanceUpdate:
    instance = uow.lock_instance(LockMode.UPDATE)
    if mode is MaintenanceMode.NORMAL and instance.restore_state is not RestoreState.NORMAL:
        raise MaintenanceChangeRejected("restore_state 非 normal 时不能切换到 normal")
    c = instance_state.c
    uow.execute_one(
        update(instance_state).where(c.singleton_key == 1).values(maintenance_mode=mode.value, version=c.version + 1)
    )
    return MaintenanceUpdate(mode=mode)

from enum import StrEnum


class MaintenanceMode(StrEnum):
    NORMAL = "normal"
    DRAINING = "draining"
    FROZEN = "frozen"


class RestoreState(StrEnum):
    NORMAL = "normal"
    BACKUP_IMAGE = "backup_image"
    RESTORING = "restoring"
    REVIEW_REQUIRED = "review_required"


class GateOp(StrEnum):
    ADMIT = "admit"
    RETRY = "retry"
    CLAIM = "claim"
    CHECKPOINT = "checkpoint"
    SEND_AUTHORIZE = "send_authorize"
    RECEIPT = "receipt"
    PUBLISH = "publish"
    CONFIG_WRITE = "config_write"
    SHARE_WRITE = "share_write"
    DISPATCH = "dispatch"
    SESSION = "session"
    LEASE_RELEASE = "lease_release"
    CONVERGE = "converge"
    CANCEL_REQUEST = "cancel_request"


# draining 只允许既有执行收敛与只减少工作的操作（SPEC §7.1，E5）
_DRAINING_ALLOWED = frozenset(
    {
        GateOp.RECEIPT,
        GateOp.CHECKPOINT,
        GateOp.LEASE_RELEASE,
        GateOp.CONVERGE,
        GateOp.SESSION,
        GateOp.CANCEL_REQUEST,
    }
)
# review_required 即使 maintenance 为 normal 也只允许登录退出（SPEC §9.1，E13）
_REVIEW_REQUIRED_ALLOWED = frozenset({GateOp.SESSION})


def is_allowed(op: GateOp, maintenance: MaintenanceMode, restore: RestoreState) -> bool:
    if maintenance is MaintenanceMode.FROZEN:
        return False
    if restore is RestoreState.REVIEW_REQUIRED:
        allowed_by_restore = op in _REVIEW_REQUIRED_ALLOWED
    else:
        allowed_by_restore = restore is RestoreState.NORMAL
    if maintenance is MaintenanceMode.DRAINING:
        return allowed_by_restore and op in _DRAINING_ALLOWED
    return allowed_by_restore

import pytest

from frameread.domain.gate import GateOp, MaintenanceMode, RestoreState, is_allowed

NORMAL = (MaintenanceMode.NORMAL, RestoreState.NORMAL)


@pytest.mark.parametrize("op", list(GateOp))
def test_normal_allows_everything(op):
    assert is_allowed(op, *NORMAL)


@pytest.mark.parametrize("op", list(GateOp))
def test_frozen_allows_nothing(op):
    assert not is_allowed(op, MaintenanceMode.FROZEN, RestoreState.NORMAL)


@pytest.mark.parametrize(
    ("op", "allowed"),
    [
        (GateOp.ADMIT, False),
        (GateOp.RETRY, False),
        (GateOp.CLAIM, False),
        (GateOp.DISPATCH, False),
        (GateOp.SEND_AUTHORIZE, False),
        (GateOp.PUBLISH, False),
        (GateOp.CONFIG_WRITE, False),
        (GateOp.SHARE_WRITE, False),
        (GateOp.RECEIPT, True),
        (GateOp.CHECKPOINT, True),
        (GateOp.LEASE_RELEASE, True),
        (GateOp.CONVERGE, True),
        (GateOp.SESSION, True),
        (GateOp.CANCEL_REQUEST, True),
    ],
)
def test_draining_table(op, allowed):
    assert is_allowed(op, MaintenanceMode.DRAINING, RestoreState.NORMAL) is allowed


@pytest.mark.parametrize("op", list(GateOp))
def test_review_required_only_allows_session_even_when_normal(op):
    assert is_allowed(op, MaintenanceMode.NORMAL, RestoreState.REVIEW_REQUIRED) is (op is GateOp.SESSION)


@pytest.mark.parametrize("restore", [RestoreState.BACKUP_IMAGE, RestoreState.RESTORING])
@pytest.mark.parametrize("op", list(GateOp))
def test_backup_image_and_restoring_allow_nothing(op, restore):
    assert not is_allowed(op, MaintenanceMode.NORMAL, restore)


def test_draining_with_review_required_takes_stricter_rule():
    assert not is_allowed(GateOp.CHECKPOINT, MaintenanceMode.DRAINING, RestoreState.REVIEW_REQUIRED)
    assert is_allowed(GateOp.SESSION, MaintenanceMode.DRAINING, RestoreState.REVIEW_REQUIRED)

from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, Strict, model_validator


class Pool(StrEnum):
    VIDEO = "video"
    QA = "qa"
    UTILITY = "utility"


class PoolCapacity(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    execution_slots: int = Field(ge=1)
    waiting_slots: int = Field(ge=0)


class ResourcePolicy(BaseModel):
    """运行时资源策略，持久化于 instance_state.policy_json，是所有进程的唯一来源（Q14、D08）。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    # 键来自 JSON/TOML 字符串，需允许 str→Pool；PoolCapacity 自身仍为 strict
    pools: dict[Annotated[Pool, Strict(False)], PoolCapacity]
    video_total_timeout_seconds: int = Field(default=7200, ge=1)
    lease_seconds: int = Field(default=60, ge=1)
    heartbeat_seconds: int = Field(default=10, ge=1)
    dispatcher_batch: int = Field(default=50, ge=1)
    dispatch_retry_budget: int = Field(default=10, ge=1)
    dispatch_generation_limit: int = Field(default=5, ge=1)
    event_retention_days: int = Field(default=7, ge=1)

    @model_validator(mode="after")
    def _check(self) -> Self:
        if Pool.VIDEO not in self.pools:
            raise ValueError("pools 必须包含 video")
        if self.heartbeat_seconds >= self.lease_seconds:
            raise ValueError("heartbeat_seconds 必须小于 lease_seconds")
        return self

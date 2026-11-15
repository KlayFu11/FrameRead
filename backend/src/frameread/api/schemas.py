import uuid

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    """所有请求体的基类：未知字段拒绝，类型不做宽松转换。"""

    model_config = ConfigDict(extra="forbid", strict=True)


class ErrorDetailBody(BaseModel):
    field: str | None = None
    code: str
    message: str


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: uuid.UUID
    task_id: uuid.UUID | None
    action: str
    retry_after_seconds: int | None
    details: list[ErrorDetailBody]


class ErrorEnvelope(BaseModel):
    error: ErrorBody

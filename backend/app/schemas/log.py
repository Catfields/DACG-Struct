from datetime import datetime

from pydantic import BaseModel, ConfigDict


class OperationLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    log_id: int
    user_id: int
    user_name: str
    operation_type: str
    operation_content: str
    operation_time: datetime
    ip_address: str | None = None
    operation_status: int
    system_id: int | None = None


class OperationLogPageOut(BaseModel):
    items: list[OperationLogOut]
    total: int
    page: int
    size: int

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ModelCreate(BaseModel):
    model_name: str
    model_version: str
    model_type: int
    model_path: str
    is_default: int = 0
    model_desc: str | None = None
    system_id: int | None = None


class ModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    model_id: int
    model_name: str
    model_version: str
    model_type: int
    model_path: str
    is_default: int
    create_user_id: int
    create_time: datetime
    model_desc: str | None = None
    system_id: int | None = None

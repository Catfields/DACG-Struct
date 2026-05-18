from pydantic import BaseModel, ConfigDict, Field
from app.schemas.segment import SegmentResultOut


class XrayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    xray_id: int
    patient_id: str
    patient_name: str
    patient_gender: int | None = None
    patient_age: int | None = None
    xray_original_path: str
    xray_format: str
    upload_user_id: int
    upload_time: str
    segment_status: int
    update_time: str | None = None
    system_id: int | None = None
    latest_audit_status: int | None = None
    latest_revise_content: str | None = None


class XrayDetail(BaseModel):
    xray: XrayOut
    segment_result: SegmentResultOut | None = None


class XrayPageOut(BaseModel):
    items: list[XrayOut]
    total: int
    page: int
    size: int


class XrayBatchDeleteRequest(BaseModel):
    xray_ids: list[int] = Field(..., min_length=1)


class XrayDeleteResult(BaseModel):
    deleted_ids: list[int]
    not_found_ids: list[int]
    deleted_count: int

from pydantic import BaseModel, ConfigDict


class SegmentResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    segment_id: int
    xray_id: int
    mask_path: str
    left_lung_view_path: str
    right_lung_view_path: str
    heart_view_path: str
    heart_area: float | None = None
    left_lung_area: float | None = None
    right_lung_area: float | None = None
    model_version: str
    segment_time: str

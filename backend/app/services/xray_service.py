from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models.xray_info import XrayInfo
from app.models.segment_result import SegmentResult
from app.core.exceptions import AppException


def create_record(db: Session, data, path: str, uploader_id: int) -> XrayInfo:
    """Create xray record."""
    existing = db.execute(select(XrayInfo).where(XrayInfo.patient_id == data.patient_id)).scalar_one_or_none()
    if existing:
        raise AppException("PATIENT_ID_EXISTS", "病历号已存在", status_code=400)
    xray = XrayInfo(
        patient_id=data.patient_id,
        patient_name=data.patient_name,
        patient_gender=data.patient_gender,
        patient_age=data.patient_age,
        xray_original_path=path,
        xray_format=data.xray_format,
        upload_user_id=uploader_id,
        segment_status=0,
    )
    db.add(xray)
    db.commit()
    db.refresh(xray)
    return xray


def update_status(db: Session, xray_id: int, status: int) -> None:
    """Update segmentation status."""
    xray = db.get(XrayInfo, xray_id)
    if not xray:
        raise AppException("XRAY_NOT_FOUND", "影像不存在", status_code=404)
    xray.segment_status = status
    db.add(xray)
    db.commit()


def get_xray(db: Session, xray_id: int) -> XrayInfo:
    """Get xray by id."""
    xray = db.get(XrayInfo, xray_id)
    if not xray:
        raise AppException("XRAY_NOT_FOUND", "影像不存在", status_code=404)
    return xray


def get_segment_result(db: Session, xray_id: int) -> SegmentResult | None:
    """Get segment result by xray id."""
    return db.execute(select(SegmentResult).where(SegmentResult.xray_id == xray_id)).scalar_one_or_none()


def list_xrays(db: Session, patient_id: str | None, start_time: str | None, end_time: str | None, page: int, size: int):
    """List xrays with filters."""
    stmt = select(XrayInfo)
    if patient_id:
        stmt = stmt.where(XrayInfo.patient_id == patient_id)
    if start_time:
        stmt = stmt.where(XrayInfo.upload_time >= start_time)
    if end_time:
        stmt = stmt.where(XrayInfo.upload_time <= end_time)
    offset = (page - 1) * size
    return db.execute(stmt.order_by(XrayInfo.upload_time.desc()).offset(offset).limit(size)).scalars().all()

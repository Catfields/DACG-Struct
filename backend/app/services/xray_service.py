from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session
from sqlalchemy import delete, func, or_, select
from app.config import settings
from app.models.report_info import ReportInfo
from app.models.report_history import ReportHistory
from app.models.translate_record import TranslateRecord
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


def _build_xray_conditions(
    patient_id: str | None = None,
    patient_name: str | None = None,
    keyword: str | None = None,
    segment_status: int | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
):
    conditions = []
    patient_id_value = patient_id.strip() if patient_id else ""
    patient_name_value = patient_name.strip() if patient_name else ""
    keyword_value = keyword.strip() if keyword else ""

    if patient_id_value:
        conditions.append(XrayInfo.patient_id.like(f"%{patient_id_value}%"))
    if patient_name_value:
        conditions.append(XrayInfo.patient_name.like(f"%{patient_name_value}%"))
    if segment_status is not None:
        conditions.append(XrayInfo.segment_status == segment_status)
    if start_time:
        conditions.append(XrayInfo.upload_time >= start_time)
    if end_time:
        conditions.append(XrayInfo.upload_time <= end_time)
    if keyword_value:
        pattern = f"%{keyword_value}%"
        conditions.append(
            or_(
                XrayInfo.patient_id.like(pattern),
                XrayInfo.patient_name.like(pattern),
                XrayInfo.xray_format.like(pattern),
            )
        )
    return conditions


def list_xrays(
    db: Session,
    patient_id: str | None,
    start_time: datetime | None,
    end_time: datetime | None,
    page: int,
    size: int,
    patient_name: str | None = None,
    keyword: str | None = None,
    segment_status: int | None = None,
):
    """List xrays with filters and total count."""
    conditions = _build_xray_conditions(
        patient_id=patient_id,
        patient_name=patient_name,
        keyword=keyword,
        segment_status=segment_status,
        start_time=start_time,
        end_time=end_time,
    )
    page = max(page, 1)
    size = min(max(size, 1), 100)
    total = db.execute(
        select(func.count()).select_from(XrayInfo).where(*conditions)
    ).scalar_one()
    offset = (page - 1) * size
    items = db.execute(
        select(XrayInfo)
        .where(*conditions)
        .order_by(XrayInfo.upload_time.desc(), XrayInfo.xray_id.desc())
        .offset(offset)
        .limit(size)
    ).scalars().all()
    return items, total, page, size


def _collect_record_paths(xrays: list[XrayInfo], segments: list[SegmentResult], reports: list[ReportInfo]) -> set[str]:
    paths: set[str] = set()
    for xray in xrays:
        if xray.xray_original_path:
            paths.add(xray.xray_original_path)
        paths.add(str(Path(settings.STORAGE_ROOT) / "visualizations" / f"xray_{xray.xray_id}_visualization.png"))
    for segment in segments:
        for value in (
            segment.mask_path,
            segment.left_lung_view_path,
            segment.right_lung_view_path,
            segment.heart_view_path,
        ):
            if value:
                paths.add(value)
    for report in reports:
        if report.report_pdf_path:
            paths.add(report.report_pdf_path)
    return paths


def _cleanup_storage_files(paths: set[str]) -> None:
    storage_root = Path(settings.STORAGE_ROOT).resolve()
    for raw_path in paths:
        try:
            path = Path(raw_path).resolve()
            path.relative_to(storage_root)
        except (OSError, ValueError):
            continue
        try:
            if path.is_file():
                path.unlink()
        except OSError:
            continue


def delete_xrays(db: Session, xray_ids: list[int], require_all: bool = False):
    """Delete xray records and dependent database rows."""
    normalized_ids = sorted({int(xray_id) for xray_id in xray_ids if int(xray_id) > 0})
    if not normalized_ids:
        raise AppException("INVALID_XRAY_IDS", "请选择要删除的影像记录", status_code=400)

    xrays = db.execute(
        select(XrayInfo).where(XrayInfo.xray_id.in_(normalized_ids))
    ).scalars().all()
    found_ids = sorted(xray.xray_id for xray in xrays)
    not_found_ids = [xray_id for xray_id in normalized_ids if xray_id not in found_ids]

    if require_all and not_found_ids:
        raise AppException("XRAY_NOT_FOUND", "影像不存在", status_code=404)
    if not found_ids:
        return {"deleted_ids": [], "not_found_ids": not_found_ids, "deleted_count": 0}

    segments = db.execute(
        select(SegmentResult).where(SegmentResult.xray_id.in_(found_ids))
    ).scalars().all()
    segment_ids = [segment.segment_id for segment in segments]
    report_conditions = [ReportInfo.xray_id.in_(found_ids)]
    if segment_ids:
        report_conditions.append(ReportInfo.segment_id.in_(segment_ids))
    reports = db.execute(
        select(ReportInfo).where(or_(*report_conditions))
    ).scalars().all()
    report_ids = [report.report_id for report in reports]
    paths = _collect_record_paths(xrays, segments, reports)

    if report_ids:
        db.execute(delete(ReportHistory).where(ReportHistory.report_id.in_(report_ids)))
    db.execute(delete(ReportInfo).where(or_(*report_conditions)))
    if segment_ids:
        db.execute(delete(TranslateRecord).where(TranslateRecord.segment_id.in_(segment_ids)))
        db.execute(delete(SegmentResult).where(SegmentResult.segment_id.in_(segment_ids)))
    db.execute(delete(XrayInfo).where(XrayInfo.xray_id.in_(found_ids)))
    db.commit()

    _cleanup_storage_files(paths)
    return {
        "deleted_ids": found_ids,
        "not_found_ids": not_found_ids,
        "deleted_count": len(found_ids),
    }

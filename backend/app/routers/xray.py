import asyncio
import logging
from datetime import date, datetime, time
from pathlib import Path
from fastapi import APIRouter, Depends, UploadFile, File, Form, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.dependencies import get_db
from app.core.permissions import require_roles, RoleName
from app.schemas.xray import XrayBatchDeleteRequest, XrayDeleteResult, XrayDetail, XrayOut, XrayPageOut
from app.services import xray_service, log_service, generation_service, translation_service, model_service
from app.services import segmentation_service
from app.database import SessionLocal
from app.models.segment_result import SegmentResult
from app.models.translate_record import TranslateRecord
from app.core.exceptions import AppException
from app.utils.file_storage import build_visualization_path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/xray", tags=["xray"])

OVERLAY_SAMPLE_PATH = Path("/data/home/zyx/Ir-UNet/DACG/DACG-Struct/backend/tests/output/visualization_validation_overlay.png")


def _format_datetime_value(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _parse_xray_time(value: str | None, label: str, is_end: bool = False) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        if len(raw) == 10:
            parsed_date = date.fromisoformat(raw)
            return datetime.combine(parsed_date, time.max if is_end else time.min)
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AppException(
            "INVALID_XRAY_TIME",
            f"{label}格式无效",
            detail="请使用 ISO 日期时间格式，例如 2026-03-17T08:00:00",
            status_code=400,
        ) from exc
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return parsed


def _serialize_xray_out(xray):
    return {
        "xray_id": xray.xray_id,
        "patient_id": xray.patient_id,
        "patient_name": xray.patient_name,
        "patient_gender": xray.patient_gender,
        "patient_age": xray.patient_age,
        "xray_original_path": xray.xray_original_path,
        "xray_format": xray.xray_format,
        "upload_user_id": xray.upload_user_id,
        "upload_time": _format_datetime_value(xray.upload_time),
        "segment_status": xray.segment_status,
        "update_time": _format_datetime_value(xray.update_time),
        "system_id": xray.system_id,
    }


def _serialize_segment_result(segment):
    if segment is None:
        return None
    return {
        "segment_id": segment.segment_id,
        "xray_id": segment.xray_id,
        "mask_path": segment.mask_path,
        "left_lung_view_path": segment.left_lung_view_path,
        "right_lung_view_path": segment.right_lung_view_path,
        "heart_view_path": segment.heart_view_path,
        "heart_area": segment.heart_area,
        "left_lung_area": segment.left_lung_area,
        "right_lung_area": segment.right_lung_area,
        "model_version": segment.model_version,
        "segment_time": _format_datetime_value(segment.segment_time),
    }


def _is_placeholder_segment(segment) -> bool:
    return segment is not None and segment.model_version == "manual-mock"


def _is_real_segment(segment) -> bool:
    return segment is not None and not _is_placeholder_segment(segment)


def _require_real_segment(segment):
    if not segment or _is_placeholder_segment(segment):
        raise AppException("SEGMENT_NOT_READY", "真实分割结果尚未生成", status_code=404)
    return segment


def _build_mask_coordinates_payload(xray_id: int, segment):
    _require_real_segment(segment)
    mask_path = Path(segment.mask_path)
    if not mask_path.exists():
        raise AppException("MASK_NOT_FOUND", "Mask 图片不存在", status_code=404)

    metadata = segmentation_service.build_mask_coordinate_metadata(str(mask_path))
    return {
        "xray_id": xray_id,
        "mask_path": segment.mask_path,
        **metadata,
    }


async def _run_segmentation_pipeline(xray_id: int, xray_path: str, app):
    db = SessionLocal()
    try:
        xray_service.update_status(db, xray_id, 1)

        tensor = segmentation_service.preprocess(xray_path)
        model = app.state.seg_model
        mask = await segmentation_service.run_inference(model, tensor)

        cv2 = segmentation_service._require_cv2()
        original_img = cv2.imread(xray_path, cv2.IMREAD_GRAYSCALE)
        if original_img is None:
            raise RuntimeError("影像读取失败")

        post = segmentation_service.post_process(mask, original_img, xray_id)

        areas = {
            "heart_area": post["heart_area"],
            "left_lung_area": post["left_lung_area"],
            "right_lung_area": post["right_lung_area"],
            "image_total_area": float(original_img.shape[0] * original_img.shape[1]),
        }
        english_text = generation_service.generate_findings(areas)

        default_model = model_service.get_default_model(db)
        model_version = default_model.model_version if default_model else "unknown"

        # Check if placeholder segment exists (from manual-save)
        existing_segment = xray_service.get_segment_result(db, xray_id)
        if existing_segment and existing_segment.model_version == "manual-mock":
            # Update the placeholder with real segmentation results
            existing_segment.mask_path = post["mask_path"]
            existing_segment.left_lung_view_path = post["left_lung_view_path"]
            existing_segment.right_lung_view_path = post["right_lung_view_path"]
            existing_segment.heart_view_path = post["heart_view_path"]
            existing_segment.heart_area = post["heart_area"]
            existing_segment.left_lung_area = post["left_lung_area"]
            existing_segment.right_lung_area = post["right_lung_area"]
            existing_segment.model_version = model_version
            db.add(existing_segment)
            db.commit()
            db.refresh(existing_segment)
            segment = existing_segment
        else:
            # Create new segment record
            segment = SegmentResult(
                xray_id=xray_id,
                mask_path=post["mask_path"],
                left_lung_view_path=post["left_lung_view_path"],
                right_lung_view_path=post["right_lung_view_path"],
                heart_view_path=post["heart_view_path"],
                heart_area=post["heart_area"],
                left_lung_area=post["left_lung_area"],
                right_lung_area=post["right_lung_area"],
                model_version=model_version,
            )
            db.add(segment)
            db.commit()
            db.refresh(segment)

        chinese_text, status = await translation_service.translate(english_text)
        trans = TranslateRecord(
            segment_id=segment.segment_id,
            english_original=english_text,
            chinese_translate=chinese_text,
            translate_status=status,
        )
        db.add(trans)
        db.commit()

        xray_service.update_status(db, xray_id, 2)
    except Exception:
        logger.exception("Segmentation pipeline failed for xray_id=%s", xray_id)
        try:
            xray_service.update_status(db, xray_id, 3)
        except Exception:
            pass
    finally:
        db.close()


@router.post("/upload", response_model=XrayOut)
async def upload_xray(
    request: Request,
    patient_id: str = Form(...),
    patient_name: str = Form(...),
    patient_gender: int | None = Form(None),
    patient_age: int | None = Form(None),
    xray_format: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(RoleName.RADIOLOGIST, RoleName.ADMIN)),
):
    from app.utils.file_storage import save_upload

    class _Form:
        def __init__(self):
            self.patient_id = patient_id
            self.patient_name = patient_name
            self.patient_gender = patient_gender
            self.patient_age = patient_age
            self.xray_format = xray_format

    path = save_upload(file, patient_id)
    xray = xray_service.create_record(db, _Form(), path, current_user.user_id)

    await log_service.write(
        db=db,
        user_id=current_user.user_id,
        user_name=current_user.real_name,
        operation_type="X光片上传",
        operation_content=f"医生 {current_user.real_name} 上传患者 {patient_name}（{patient_id}）的X光片",
        ip_address=request.client.host if request.client else None,
        operation_status=1,
    )

    xray_service.update_status(db, xray.xray_id, 1)
    db.refresh(xray)
    asyncio.create_task(_run_segmentation_pipeline(xray.xray_id, xray.xray_original_path, request.app))
    return _serialize_xray_out(xray)


@router.get("/overlay-sample")
async def get_overlay_sample():
    if not OVERLAY_SAMPLE_PATH.exists():
        raise AppException("OVERLAY_NOT_FOUND", "遮罩样例不存在", status_code=404)
    return FileResponse(str(OVERLAY_SAMPLE_PATH))


@router.delete("/batch", response_model=XrayDeleteResult)
async def batch_delete_xrays(
    payload: XrayBatchDeleteRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(RoleName.RADIOLOGIST, RoleName.ADMIN)),
):
    result = xray_service.delete_xrays(db, payload.xray_ids)
    await log_service.write(
        db=db,
        user_id=current_user.user_id,
        user_name=current_user.real_name,
        operation_type="影像记录删除",
        operation_content=f"批量删除影像记录 {result['deleted_ids']}",
        ip_address=request.client.host if request.client else None,
        operation_status=1,
    )
    return result


@router.delete("/{xray_id}", response_model=XrayDeleteResult)
async def delete_xray(
    xray_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(RoleName.RADIOLOGIST, RoleName.ADMIN)),
):
    result = xray_service.delete_xrays(db, [xray_id], require_all=True)
    await log_service.write(
        db=db,
        user_id=current_user.user_id,
        user_name=current_user.real_name,
        operation_type="影像记录删除",
        operation_content=f"删除影像记录 {xray_id}",
        ip_address=request.client.host if request.client else None,
        operation_status=1,
    )
    return result


@router.get("/{xray_id}", response_model=XrayDetail)
async def get_xray_detail(xray_id: int, db: Session = Depends(get_db), current_user=Depends(require_roles(RoleName.RADIOLOGIST, RoleName.ADMIN))):
    xray = xray_service.get_xray(db, xray_id)
    segment = xray_service.get_segment_result(db, xray_id)
    return {"xray": _serialize_xray_out(xray), "segment_result": _serialize_segment_result(segment)}


@router.get("/{xray_id}/mask")
async def get_mask(xray_id: int, db: Session = Depends(get_db), current_user=Depends(require_roles(RoleName.RADIOLOGIST, RoleName.ADMIN))):
    segment = xray_service.get_segment_result(db, xray_id)
    _require_real_segment(segment)
    return FileResponse(segment.mask_path)


@router.get("/{xray_id}/views")
async def get_views(xray_id: int, db: Session = Depends(get_db), current_user=Depends(require_roles(RoleName.RADIOLOGIST, RoleName.ADMIN))):
    segment = xray_service.get_segment_result(db, xray_id)
    _require_real_segment(segment)
    mask_coordinates = _build_mask_coordinates_payload(xray_id, segment)
    return {
        "mask_path": segment.mask_path,
        "visualization_path": build_visualization_path(xray_id),
        "left_lung_view_path": segment.left_lung_view_path,
        "right_lung_view_path": segment.right_lung_view_path,
        "heart_view_path": segment.heart_view_path,
        "mask_coordinates": mask_coordinates,
    }


@router.get("/{xray_id}/mask-coordinates")
async def get_mask_coordinates(
    xray_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(RoleName.RADIOLOGIST, RoleName.ADMIN, RoleName.ATTENDING)),
):
    segment = xray_service.get_segment_result(db, xray_id)
    _require_real_segment(segment)
    return _build_mask_coordinates_payload(xray_id, segment)


@router.get("/{xray_id}/segment-status")
async def get_segment_status(
    xray_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(RoleName.RADIOLOGIST, RoleName.ADMIN, RoleName.ATTENDING)),
):
    xray = xray_service.get_xray(db, xray_id)
    segment = xray_service.get_segment_result(db, xray_id)
    segment_status = xray.segment_status
    if segment_status == 2 and not _is_real_segment(segment):
        segment_status = 0
    return {"segment_status": segment_status}


@router.post("/{xray_id}/segment")
async def trigger_segmentation(
    xray_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(RoleName.RADIOLOGIST, RoleName.ADMIN)),
):
    xray = xray_service.get_xray(db, xray_id)
    if xray.segment_status == 1:
        raise AppException("SEGMENT_IN_PROGRESS", "分割正在进行中", status_code=400)
    if xray.segment_status == 2:
        segment = xray_service.get_segment_result(db, xray_id)
        # Only block if real segmentation exists (not placeholder)
        if segment and segment.model_version != "manual-mock":
            raise AppException("SEGMENT_ALREADY_EXISTS", "分割结果已存在", status_code=400)

    xray_service.update_status(db, xray_id, 1)
    asyncio.create_task(_run_segmentation_pipeline(xray_id, xray.xray_original_path, request.app))
    return {"message": "分割任务已启动", "xray_id": xray_id}


@router.get("/{xray_id}/visualization")
async def get_visualization(
    xray_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(RoleName.RADIOLOGIST, RoleName.ADMIN)),
):
    segment = xray_service.get_segment_result(db, xray_id)
    _require_real_segment(segment)

    visualization_path = Path(build_visualization_path(xray_id))
    if not visualization_path.exists():
        raise AppException("VISUALIZATION_NOT_FOUND", "可视化样例不存在", status_code=404)
    return FileResponse(str(visualization_path))


@router.get("/{xray_id}/original")
async def get_original_xray(
    xray_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(RoleName.RADIOLOGIST, RoleName.ADMIN, RoleName.ATTENDING)),
):
    xray = xray_service.get_xray(db, xray_id)
    original_path = Path(xray.xray_original_path)
    if not original_path.exists():
        raise AppException("XRAY_FILE_NOT_FOUND", "原始影像文件不存在", status_code=404)
    return FileResponse(str(original_path))


@router.get("/", response_model=XrayPageOut)
async def list_xrays(
    patient_id: str | None = None,
    patient_name: str | None = None,
    keyword: str | None = None,
    segment_status: int | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    page: int = 1,
    size: int = 20,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(RoleName.RADIOLOGIST, RoleName.ADMIN, RoleName.ATTENDING)),
):
    page = max(page, 1)
    size = min(max(size, 1), 100)
    start_dt = _parse_xray_time(start_time, "开始时间")
    end_dt = _parse_xray_time(end_time, "结束时间", is_end=True)
    if start_dt and end_dt and start_dt > end_dt:
        raise AppException("INVALID_XRAY_TIME_RANGE", "开始时间不能晚于结束时间", status_code=400)
    xrays, total, page, size = xray_service.list_xrays(
        db,
        patient_id=patient_id,
        patient_name=patient_name,
        keyword=keyword,
        segment_status=segment_status,
        start_time=start_dt,
        end_time=end_dt,
        page=page,
        size=size,
    )
    return {
        "items": [_serialize_xray_out(xray) for xray in xrays],
        "total": total,
        "page": page,
        "size": size,
    }

import asyncio
from pathlib import Path
from fastapi import APIRouter, Depends, UploadFile, File, Form, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.dependencies import get_db
from app.core.permissions import require_roles, RoleName
from app.schemas.xray import XrayDetail, XrayOut
from app.services import xray_service, log_service, generation_service, translation_service, model_service
from app.services import segmentation_service
from app.database import SessionLocal
from app.models.segment_result import SegmentResult
from app.models.translate_record import TranslateRecord
from app.core.exceptions import AppException
from app.utils.file_storage import build_visualization_path

router = APIRouter(prefix="/xray", tags=["xray"])

OVERLAY_SAMPLE_PATH = Path(__file__).resolve().parents[2] / "tests" / "output" / "visualization_validation_overlay.png"


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

    asyncio.create_task(_run_segmentation_pipeline(xray.xray_id, xray.xray_original_path, request.app))
    return xray


@router.get("/overlay-sample")
async def get_overlay_sample():
    if not OVERLAY_SAMPLE_PATH.exists():
        raise AppException("OVERLAY_NOT_FOUND", "遮罩样例不存在", status_code=404)
    return FileResponse(str(OVERLAY_SAMPLE_PATH))


@router.get("/{xray_id}", response_model=XrayDetail)
async def get_xray_detail(xray_id: int, db: Session = Depends(get_db), current_user=Depends(require_roles(RoleName.RADIOLOGIST, RoleName.ADMIN))):
    xray = xray_service.get_xray(db, xray_id)
    segment = xray_service.get_segment_result(db, xray_id)
    return {"xray": xray, "segment_result": segment}


@router.get("/{xray_id}/mask")
async def get_mask(xray_id: int, db: Session = Depends(get_db), current_user=Depends(require_roles(RoleName.RADIOLOGIST, RoleName.ADMIN))):
    segment = xray_service.get_segment_result(db, xray_id)
    if not segment:
        raise AppException("SEGMENT_NOT_FOUND", "分割结果不存在", status_code=404)
    return FileResponse(segment.mask_path)


@router.get("/{xray_id}/views")
async def get_views(xray_id: int, db: Session = Depends(get_db), current_user=Depends(require_roles(RoleName.RADIOLOGIST, RoleName.ADMIN))):
    segment = xray_service.get_segment_result(db, xray_id)
    if not segment:
        raise AppException("SEGMENT_NOT_FOUND", "分割结果不存在", status_code=404)
    return {
        "mask_path": segment.mask_path,
        "visualization_path": build_visualization_path(xray_id),
        "left_lung_view_path": segment.left_lung_view_path,
        "right_lung_view_path": segment.right_lung_view_path,
        "heart_view_path": segment.heart_view_path,
    }


@router.get("/{xray_id}/visualization")
async def get_visualization(
    xray_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(RoleName.RADIOLOGIST, RoleName.ADMIN)),
):
    segment = xray_service.get_segment_result(db, xray_id)
    if not segment:
        raise AppException("SEGMENT_NOT_FOUND", "分割结果不存在", status_code=404)

    visualization_path = Path(build_visualization_path(xray_id))
    if not visualization_path.exists():
        raise AppException("VISUALIZATION_NOT_FOUND", "可视化样例不存在", status_code=404)
    return FileResponse(str(visualization_path))


@router.get("/", response_model=list[XrayOut])
async def list_xrays(
    patient_id: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    page: int = 1,
    size: int = 20,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(RoleName.RADIOLOGIST, RoleName.ADMIN)),
):
    return xray_service.list_xrays(db, patient_id, start_time, end_time, page, size)

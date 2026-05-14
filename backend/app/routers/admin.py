from datetime import datetime
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, select
from app.dependencies import get_db
from app.core.permissions import require_roles, RoleName
from app.schemas.log import OperationLogPageOut
from app.schemas.model import ModelCreate, ModelOut
from app.models.operation_log import OperationLog
from app.services import model_service, log_service
from app.services import segmentation_service
from app.core.exceptions import AppException

router = APIRouter(prefix="/admin", tags=["admin"])


def _parse_log_time(value: str | None, label: str) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AppException(
            "INVALID_LOG_TIME",
            f"{label}格式无效",
            detail="请使用 ISO 日期时间格式，例如 2026-03-17T08:00:00",
            status_code=400,
        ) from exc
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return parsed


@router.get("/logs", response_model=OperationLogPageOut)
async def list_logs(
    user_id: int | None = None,
    user_name: str | None = None,
    operation_type: str | None = None,
    operation_status: int | None = None,
    keyword: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    page: int = 1,
    size: int = 20,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(RoleName.ADMIN)),
):
    page = max(page, 1)
    size = min(max(size, 1), 100)
    start_dt = _parse_log_time(start_time, "开始时间")
    end_dt = _parse_log_time(end_time, "结束时间")

    conditions = []
    if user_id is not None:
        conditions.append(OperationLog.user_id == user_id)
    user_name_value = user_name.strip() if user_name else ""
    operation_type_value = operation_type.strip() if operation_type else ""
    keyword_value = keyword.strip() if keyword else ""

    if user_name_value:
        conditions.append(OperationLog.user_name.like(f"%{user_name_value}%"))
    if operation_type_value:
        conditions.append(OperationLog.operation_type == operation_type_value)
    if operation_status is not None:
        conditions.append(OperationLog.operation_status == operation_status)
    if start_dt:
        conditions.append(OperationLog.operation_time >= start_dt)
    if end_dt:
        conditions.append(OperationLog.operation_time <= end_dt)
    if keyword_value:
        pattern = f"%{keyword_value}%"
        conditions.append(
            or_(
                OperationLog.user_name.like(pattern),
                OperationLog.operation_type.like(pattern),
                OperationLog.operation_content.like(pattern),
                OperationLog.ip_address.like(pattern),
            )
        )

    stmt = select(OperationLog).where(*conditions)
    total = db.execute(
        select(func.count()).select_from(OperationLog).where(*conditions)
    ).scalar_one()
    offset = (page - 1) * size
    logs = db.execute(
        stmt.order_by(OperationLog.operation_time.desc()).offset(offset).limit(size)
    ).scalars().all()
    return {"items": logs, "total": total, "page": page, "size": size}


@router.get("/models", response_model=list[ModelOut])
async def list_models(db: Session = Depends(get_db), current_user=Depends(require_roles(RoleName.ADMIN))):
    return model_service.list_models(db)


@router.post("/models", response_model=ModelOut)
async def create_model(payload: ModelCreate, request: Request, db: Session = Depends(get_db), current_user=Depends(require_roles(RoleName.ADMIN))):
    model = model_service.create_model(db, payload, current_user.user_id)
    await log_service.write(
        db=db,
        user_id=current_user.user_id,
        user_name=current_user.real_name,
        operation_type="模型更新",
        operation_content=f"新增模型 {model.model_version}",
        ip_address=request.client.host if request.client else None,
        operation_status=1,
    )
    return model


@router.patch("/models/{model_id}/default", response_model=ModelOut)
async def set_default_model(model_id: int, request: Request, db: Session = Depends(get_db), current_user=Depends(require_roles(RoleName.ADMIN))):
    model = model_service.set_default(db, model_id)

    # Hot-reload based on model type
    if model.model_type == 1:
        # Segmentation model: reload into app.state
        try:
            new_model = segmentation_service.load_model(model.model_path)
            request.app.state.seg_model = new_model
            request.app.state.model_version = model.model_version
        except Exception as exc:
            raise AppException("MODEL_RELOAD_FAILED", "分割模型热重载失败", detail=str(exc), status_code=500) from exc
    elif model.model_type == 2:
        # Generation model: update app.state reference
        request.app.state.gen_model_version = model.model_version
        request.app.state.gen_model_path = model.model_path

    await log_service.write(
        db=db,
        user_id=current_user.user_id,
        user_name=current_user.real_name,
        operation_type="模型更新",
        operation_content=f"设置默认模型 {model.model_version}",
        ip_address=request.client.host if request.client else None,
        operation_status=1,
    )
    return model


@router.delete("/models/{model_id}")
async def delete_model(model_id: int, request: Request, db: Session = Depends(get_db), current_user=Depends(require_roles(RoleName.ADMIN))):
    model_service.delete_model(db, model_id)
    await log_service.write(
        db=db,
        user_id=current_user.user_id,
        user_name=current_user.real_name,
        operation_type="模型更新",
        operation_content=f"删除模型 {model_id}",
        ip_address=request.client.host if request.client else None,
        operation_status=1,
    )
    return {"status": "ok"}

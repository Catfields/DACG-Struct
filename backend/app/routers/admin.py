from datetime import datetime
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.dependencies import get_db
from app.core.permissions import require_roles, RoleName
from app.schemas.model import ModelCreate, ModelOut
from app.models.operation_log import OperationLog
from app.services import model_service, log_service
from app.services import segmentation_service
from app.core.exceptions import AppException

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/logs")
async def list_logs(
    user_id: int | None = None,
    operation_type: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    page: int = 1,
    size: int = 20,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(RoleName.ADMIN)),
):
    stmt = select(OperationLog)
    if user_id:
        stmt = stmt.where(OperationLog.user_id == user_id)
    if operation_type:
        stmt = stmt.where(OperationLog.operation_type == operation_type)
    if start_time:
        stmt = stmt.where(OperationLog.operation_time >= start_time)
    if end_time:
        stmt = stmt.where(OperationLog.operation_time <= end_time)
    offset = (page - 1) * size
    logs = db.execute(stmt.order_by(OperationLog.operation_time.desc()).offset(offset).limit(size)).scalars().all()
    return logs


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
    try:
        new_model = segmentation_service.load_model(model.model_path)
        request.app.state.seg_model = new_model
        request.app.state.model_version = model.model_version
    except Exception as exc:
        raise AppException("MODEL_RELOAD_FAILED", "模型热重载失败", detail=str(exc), status_code=500) from exc

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

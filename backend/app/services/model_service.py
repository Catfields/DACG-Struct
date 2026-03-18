from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models.model_manage import ModelManage
from app.core.exceptions import AppException


def list_models(db: Session):
    """List all models."""
    return db.execute(select(ModelManage).order_by(ModelManage.create_time.desc())).scalars().all()


def create_model(db: Session, data, create_user_id: int) -> ModelManage:
    """Create model record."""
    existing = db.execute(select(ModelManage).where(ModelManage.model_version == data.model_version)).scalar_one_or_none()
    if existing:
        raise AppException("MODEL_EXISTS", "模型版本已存在", status_code=400)
    model = ModelManage(
        model_name=data.model_name,
        model_version=data.model_version,
        model_type=data.model_type,
        model_path=data.model_path,
        is_default=data.is_default,
        create_user_id=create_user_id,
        model_desc=data.model_desc,
        system_id=data.system_id,
    )
    db.add(model)
    db.commit()
    db.refresh(model)
    return model


def set_default(db: Session, model_id: int) -> ModelManage:
    """Set model as default in a transaction."""
    model = db.get(ModelManage, model_id)
    if not model:
        raise AppException("MODEL_NOT_FOUND", "模型不存在", status_code=404)
    if model.model_type != 1:
        raise AppException("MODEL_TYPE_INVALID", "仅支持语义分割模型设为默认", status_code=400)

    current = db.execute(select(ModelManage).where(ModelManage.is_default == 1, ModelManage.model_type == 1)).scalar_one_or_none()
    if current and current.model_id != model_id:
        current.is_default = 0
        db.add(current)

    model.is_default = 1
    db.add(model)
    db.commit()
    db.refresh(model)
    return model


def delete_model(db: Session, model_id: int) -> None:
    """Delete model record."""
    model = db.get(ModelManage, model_id)
    if not model:
        raise AppException("MODEL_NOT_FOUND", "模型不存在", status_code=404)
    db.delete(model)
    db.commit()


def get_default_model(db: Session) -> ModelManage | None:
    """Get default segmentation model."""
    return db.execute(select(ModelManage).where(ModelManage.is_default == 1, ModelManage.model_type == 1)).scalar_one_or_none()

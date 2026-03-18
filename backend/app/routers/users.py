from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from app.dependencies import get_db
from app.core.permissions import require_roles, RoleName
from app.schemas.user import UserCreate, UserOut, UserUpdate
from app.services import user_service, log_service

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/", response_model=UserOut, dependencies=[Depends(require_roles(RoleName.ADMIN))])
async def create_user(payload: UserCreate, request: Request, db: Session = Depends(get_db), current_user=Depends(require_roles(RoleName.ADMIN))):
    user = user_service.create_user(db, payload)
    await log_service.write(
        db=db,
        user_id=current_user.user_id,
        user_name=current_user.real_name,
        operation_type="用户管理",
        operation_content=f"创建用户 {user.login_name}",
        ip_address=request.client.host if request.client else None,
        operation_status=1,
    )
    return user


@router.get("/", response_model=list[UserOut], dependencies=[Depends(require_roles(RoleName.ADMIN))])
async def list_users(page: int = 1, size: int = 20, db: Session = Depends(get_db)):
    return user_service.list_users(db, page, size)


@router.get("/{user_id}", response_model=UserOut, dependencies=[Depends(require_roles(RoleName.ADMIN))])
async def get_user(user_id: int, db: Session = Depends(get_db)):
    return user_service.get_user(db, user_id)


@router.patch("/{user_id}", response_model=UserOut, dependencies=[Depends(require_roles(RoleName.ADMIN))])
async def update_user(user_id: int, payload: UserUpdate, request: Request, db: Session = Depends(get_db), current_user=Depends(require_roles(RoleName.ADMIN))):
    user = user_service.update_user(db, user_id, payload)
    await log_service.write(
        db=db,
        user_id=current_user.user_id,
        user_name=current_user.real_name,
        operation_type="用户管理",
        operation_content=f"更新用户 {user.login_name}",
        ip_address=request.client.host if request.client else None,
        operation_status=1,
    )
    return user


@router.delete("/{user_id}", dependencies=[Depends(require_roles(RoleName.ADMIN))])
async def delete_user(user_id: int, request: Request, db: Session = Depends(get_db), current_user=Depends(require_roles(RoleName.ADMIN))):
    user = user_service.get_user(db, user_id)
    user_service.delete_user(db, user_id)
    await log_service.write(
        db=db,
        user_id=current_user.user_id,
        user_name=current_user.real_name,
        operation_type="用户管理",
        operation_content=f"删除用户 {user.login_name}",
        ip_address=request.client.host if request.client else None,
        operation_status=1,
    )
    return {"status": "ok"}

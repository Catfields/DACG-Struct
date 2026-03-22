from fastapi import APIRouter, Depends, Request, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.dependencies import get_db
from app.schemas.auth import LoginRequest, TokenResponse, RefreshRequest, LoginResponse
from app.services import auth_service, log_service
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    try:
        result = auth_service.login(db, payload.login_name, payload.password, payload.role_name)
        background_tasks.add_task(
            log_service.write,
            None,
            result["user"]["user_id"],
            result["user"]["real_name"],
            "用户登录",
            f"用户 {result['user']['login_name']} 登录成功",
            request.client.host if request.client else None,
            1,
        )
        return result
    except Exception:
        user_id = 0
        user_name = payload.login_name
        try:
            result = db.execute(select(User).where(User.login_name == payload.login_name))
            user = result.scalar_one_or_none()
            if user:
                user_id = user.user_id
                user_name = user.real_name
        except Exception:
            pass
        background_tasks.add_task(
            log_service.write,
            None,
            user_id,
            user_name,
            "用户登录",
            f"用户 {payload.login_name} 登录失败",
            request.client.host if request.client else None,
            0,
        )
        raise


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    return auth_service.refresh_access_token(db, payload.refresh_token)

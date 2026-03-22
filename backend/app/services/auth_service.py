from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models.user import User
from app.models.role import Role
from app.core.security import verify_password, create_access_token, create_refresh_token, decode_token
from app.core.exceptions import AuthException


def authenticate_user(db: Session, login_name: str, password: str, expected_role_name: str) -> tuple[User, str]:
    """Validate user credentials and return user and role_name."""
    stmt = select(User, Role.role_name).join(Role, Role.role_id == User.role_id, isouter=True).where(User.login_name == login_name)
    row = db.execute(stmt).first()
    if not row:
        raise AuthException("INVALID_CREDENTIALS", "用户名或密码错误", status_code=401)
    user, role_name = row
    if not role_name:
        raise AuthException("ROLE_NOT_FOUND", "用户角色缺失", status_code=403)
    if expected_role_name and role_name != expected_role_name:
        raise AuthException("ROLE_MISMATCH", "身份与用户角色不匹配", status_code=403)
    # if not verify_password(password, user.pwd):
    #     raise AuthException("INVALID_CREDENTIALS", "用户名或密码错误", status_code=401)
    if password != user.pwd:
        raise AuthException("INVALID_CREDENTIALS", "用户名或密码错误", status_code=401)
    return user, role_name


def login(db: Session, login_name: str, password: str, role_name: str) -> dict[str, str]:
    """Login and return access/refresh tokens."""
    user, role_name = authenticate_user(db, login_name, password, role_name)
    access_token = create_access_token(subject=str(user.user_id), role_name=role_name)
    refresh_token = create_refresh_token(subject=str(user.user_id))
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "user_id": user.user_id,
            "login_name": user.login_name,
            "real_name": user.real_name,
            "role_id": user.role_id,
            "role_name": role_name,
        },
    }


def refresh_access_token(db: Session, refresh_token: str) -> dict[str, str]:
    """Refresh access token using refresh token."""
    payload = decode_token(refresh_token)
    if payload.get("type") != "refresh":
        raise AuthException("TOKEN_INVALID", "Refresh Token 无效", status_code=401)
    user_id = payload.get("sub")
    if not user_id:
        raise AuthException("TOKEN_INVALID", "Refresh Token 无效", status_code=401)
    stmt = select(User, Role.role_name).join(Role, Role.role_id == User.role_id, isouter=True).where(User.user_id == int(user_id))
    row = db.execute(stmt).first()
    if not row:
        raise AuthException("USER_NOT_FOUND", "用户不存在", status_code=401)
    user, role_name = row
    access_token = create_access_token(subject=str(user.user_id), role_name=role_name)
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}

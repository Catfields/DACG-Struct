from dataclasses import dataclass
from typing import Generator
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.database import SessionLocal
from app.core.security import decode_token
from app.core.exceptions import AuthException
from app.models.user import User
from app.models.role import Role


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


@dataclass
class CurrentUser:
    user_id: int
    login_name: str
    real_name: str
    role_name: str


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> CurrentUser:
    payload = decode_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise AuthException("TOKEN_INVALID", "Token 无效或已过期", status_code=401)

    stmt = select(User, Role.role_name).join(Role, Role.role_id == User.role_id, isouter=True).where(User.user_id == int(user_id))
    row = db.execute(stmt).first()
    if not row:
        raise AuthException("USER_NOT_FOUND", "用户不存在", status_code=401)

    user, role_name = row
    if not role_name:
        raise AuthException("ROLE_NOT_FOUND", "用户角色缺失", status_code=403)

    return CurrentUser(user_id=user.user_id, login_name=user.login_name, real_name=user.real_name, role_name=role_name)

from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models.user import User
from app.core.security import get_password_hash
from app.core.exceptions import AppException


def create_user(db: Session, data) -> User:
    """Create a user with hashed password."""
    existing = db.execute(select(User).where(User.login_name == data.login_name)).scalar_one_or_none()
    if existing:
        raise AppException("USER_EXISTS", "登录名已存在", status_code=400)
    user = User(
        login_name=data.login_name,
        login_flag=data.login_flag,
        pwd=get_password_hash(data.password),
        real_name=data.real_name,
        role_id=data.role_id,
        phone=data.phone,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def list_users(db: Session, page: int, size: int) -> list[User]:
    """List users with pagination."""
    offset = (page - 1) * size
    return db.execute(select(User).offset(offset).limit(size)).scalars().all()


def get_user(db: Session, user_id: int) -> User:
    """Get user by id."""
    user = db.get(User, user_id)
    if not user:
        raise AppException("USER_NOT_FOUND", "用户不存在", status_code=404)
    return user


def update_user(db: Session, user_id: int, data) -> User:
    """Update user info."""
    user = get_user(db, user_id)
    if data.real_name is not None:
        user.real_name = data.real_name
    if data.role_id is not None:
        user.role_id = data.role_id
    if data.phone is not None:
        user.phone = data.phone
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def delete_user(db: Session, user_id: int) -> None:
    """Delete user."""
    user = get_user(db, user_id)
    db.delete(user)
    db.commit()

from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models.user import User
from app.core.security import get_password_hash
from app.core.exceptions import AppException
import secrets
import string


def create_user(db: Session, data) -> User:
    """Create a user with hashed password.
    
    Login flag is automatically set based on phone presence:
    - 1 = username only (no phone)
    - 3 = both username and phone (has phone)
    """
    existing = db.execute(select(User).where(User.login_name == data.login_name)).scalar_one_or_none()
    if existing:
        raise AppException("USER_EXISTS", "登录名已存在", status_code=400)
    
    # Automatically determine login_flag based on phone presence
    has_phone = bool(data.phone and str(data.phone).strip())
    login_flag = 3 if has_phone else 1  # 3 = both, 1 = username only
    
    user = User(
        login_name=data.login_name,
        login_flag=login_flag,
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
    """Update user info.
    
    If phone is added/removed, automatically update login_flag:
    - 1 = username only (no phone)
    - 3 = both username and phone (has phone)
    """
    user = get_user(db, user_id)
    if data.real_name is not None:
        user.real_name = data.real_name
    if data.role_id is not None:
        user.role_id = data.role_id
    if data.phone is not None:
        user.phone = data.phone
        # Automatically update login_flag based on phone presence
        has_phone = bool(data.phone and str(data.phone).strip())
        user.login_flag = 3 if has_phone else 1  # 3 = both, 1 = username only
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def delete_user(db: Session, user_id: int) -> None:
    """Delete user."""
    user = get_user(db, user_id)
    db.delete(user)
    db.commit()


def _generate_temp_password(length: int = 10) -> str:
    """Generate a random temporary password with guaranteed complexity."""
    alphabet = string.ascii_letters + string.digits
    # Ensure at least one uppercase, one lowercase, one digit
    while True:
        pwd = ''.join(secrets.choice(alphabet) for _ in range(length))
        if (any(c.isupper() for c in pwd)
                and any(c.islower() for c in pwd)
                and any(c.isdigit() for c in pwd)):
            return pwd


def reset_password(db: Session, user_id: int) -> dict:
    """Reset a user's password to a random temporary password.
    
    Returns a dict with user info and the new plaintext password
    (only available at this moment).
    """
    user = get_user(db, user_id)
    new_password = _generate_temp_password()
    user.pwd = get_password_hash(new_password)
    db.add(user)
    db.commit()
    db.refresh(user)
    return {
        "user": {
            "user_id": user.user_id,
            "login_name": user.login_name,
            "real_name": user.real_name,
        },
        "new_password": new_password,
    }


def change_password(db: Session, user_id: int, old_password: str, new_password: str) -> None:
    """Change a user's password after verifying the old password.
    
    Args:
        db: Database session.
        user_id: ID of the user changing password.
        old_password: Current password for verification.
        new_password: New password to set.
    
    Raises:
        AppException: If user not found or old password is incorrect.
    """
    from app.core.security import verify_password, get_password_hash
    
    user = get_user(db, user_id)
    if not verify_password(old_password, user.pwd):
        raise AppException("INVALID_PASSWORD", "旧密码错误", status_code=400)
    
    user.pwd = get_password_hash(new_password)
    db.add(user)
    db.commit()
    db.refresh(user)

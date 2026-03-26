from datetime import datetime, timedelta, timezone
from typing import Any
from jose import jwt, JWTError
from passlib.context import CryptContext
from app.config import settings
from app.core.exceptions import AppException, AuthException

#
# NOTE:
# - Some bcrypt backends hard-fail when the password is longer than 72 bytes.
# - This project previously used bcrypt, so we keep it for verifying existing
#   password hashes.
# - For *new* hashes, use pbkdf2_sha256 to avoid the 72-byte bcrypt limit.
pwd_context = CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], deprecated="auto")
ALGORITHM = "HS256"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    # Backward compatibility:
    # - some environments may have stored plaintext passwords during early dev.
    # - new users use passlib hashes (pbkdf2_sha256 / bcrypt).
    stored = hashed_password or ""
    if stored.startswith("$"):
        try:
            return pwd_context.verify(plain_password, stored)
        except Exception:
            return False
    return plain_password == stored


def get_password_hash(password: str) -> str:
    try:
        return pwd_context.hash(password)
    except ValueError as exc:
        # Should be rare with bcrypt_sha256, but keep error actionable for clients.
        raise AppException(
            "PASSWORD_INVALID",
            "密码不符合要求（可能过长），请缩短后重试",
            detail=str(exc),
            status_code=400,
        ) from exc


def create_access_token(subject: str, role_name: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    to_encode = {"sub": subject, "role_name": role_name, "exp": expire}
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = {"sub": subject, "exp": expire, "type": "refresh"}
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise AuthException("TOKEN_INVALID", "Token 无效或已过期", status_code=401) from exc
    return payload

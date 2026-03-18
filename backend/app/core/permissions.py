from typing import Callable
from fastapi import Depends
from app.dependencies import get_current_user
from app.core.exceptions import AuthException


class RoleName:
    ADMIN = "管理员"
    RADIOLOGIST = "影像科医生"
    ATTENDING = "主治医生"


def require_roles(*role_names: str) -> Callable:
    async def _require_roles(current_user=Depends(get_current_user)):
        if current_user.role_name not in role_names:
            raise AuthException("FORBIDDEN", "权限不足", status_code=403)
        return current_user

    return _require_roles

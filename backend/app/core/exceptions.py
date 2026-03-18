from typing import Any


class AppException(Exception):
    def __init__(self, error_code: str, message: str, detail: Any = None, status_code: int = 400):
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.detail = detail
        self.status_code = status_code


class AuthException(AppException):
    def __init__(self, error_code: str, message: str, detail: Any = None, status_code: int = 401):
        super().__init__(error_code=error_code, message=message, detail=detail, status_code=status_code)

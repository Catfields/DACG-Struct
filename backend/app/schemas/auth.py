from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    login_name: str
    password: str = Field(..., min_length=4)
    role_name: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class LoginUserInfo(BaseModel):
    user_id: int
    login_name: str
    real_name: str
    role_id: int | None = None
    role_name: str


class LoginResponse(TokenResponse):
    user: LoginUserInfo

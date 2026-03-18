from pydantic import BaseModel, ConfigDict


class UserCreate(BaseModel):
    login_name: str
    login_flag: int
    password: str
    real_name: str
    role_id: int | None = None
    phone: str | None = None


class UserUpdate(BaseModel):
    real_name: str | None = None
    role_id: int | None = None
    phone: str | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    login_name: str
    login_flag: int
    real_name: str
    role_id: int | None = None
    phone: str | None = None

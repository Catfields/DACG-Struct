from pydantic_settings import BaseSettings
from pydantic import ConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    JWT_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    FALLBACK_MODEL_PATH: str = "./ml_models/unet_dacg.pth"
    STORAGE_ROOT: str = "./storage"
    DOUBAO_API_KEY: str
    DOUBAO_BASE_URL: str
    HOSPITAL_NAME: str = "医院名称"
    FONT_PATH: str = "./fonts/NotoSansSC-Regular.ttf"

    model_config = ConfigDict(env_file=".env")


settings = Settings()

from sqlalchemy import Column, BigInteger, String, SmallInteger, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class ModelManage(Base):
    __tablename__ = "model_manage"

    model_id = Column(BigInteger, primary_key=True, autoincrement=True)
    model_name = Column(String(100), nullable=False)
    model_version = Column(String(50), nullable=False, unique=True)
    model_type = Column(SmallInteger, nullable=False)
    model_path = Column(String(255), nullable=False)
    is_default = Column(SmallInteger, nullable=False, default=0)
    create_user_id = Column(BigInteger, ForeignKey("user.user_id"), nullable=False)
    create_time = Column(DateTime, nullable=False, default=func.now())
    model_desc = Column(String(500), nullable=True)
    system_id = Column(BigInteger, nullable=True)

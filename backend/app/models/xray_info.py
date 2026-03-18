from sqlalchemy import Column, BigInteger, String, SmallInteger, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class XrayInfo(Base):
    __tablename__ = "xray_info"

    xray_id = Column(BigInteger, primary_key=True, autoincrement=True)
    patient_id = Column(String(30), nullable=False, unique=True)
    patient_name = Column(String(50), nullable=False)
    patient_gender = Column(SmallInteger, nullable=True)
    patient_age = Column(SmallInteger, nullable=True)
    xray_original_path = Column(String(255), nullable=False)
    xray_format = Column(String(10), nullable=False)
    upload_user_id = Column(BigInteger, ForeignKey("user.user_id"), nullable=False)
    upload_time = Column(DateTime, nullable=False, default=func.now())
    segment_status = Column(SmallInteger, nullable=False, default=0)
    update_time = Column(DateTime, nullable=True, onupdate=func.now())
    system_id = Column(BigInteger, nullable=True)

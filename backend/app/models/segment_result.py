from sqlalchemy import Column, BigInteger, String, DateTime, Float, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class SegmentResult(Base):
    __tablename__ = "segment_result"

    segment_id = Column(BigInteger, primary_key=True, autoincrement=True)
    xray_id = Column(BigInteger, ForeignKey("xray_info.xray_id"), nullable=False)
    mask_path = Column(String(255), nullable=False)
    left_lung_view_path = Column(String(255), nullable=False)
    right_lung_view_path = Column(String(255), nullable=False)
    heart_view_path = Column(String(255), nullable=False)
    heart_area = Column(Float, nullable=True)
    left_lung_area = Column(Float, nullable=True)
    right_lung_area = Column(Float, nullable=True)
    model_version = Column(String(50), nullable=False)
    segment_time = Column(DateTime, nullable=False, default=func.now())
    system_id = Column(BigInteger, nullable=True)

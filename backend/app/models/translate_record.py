from sqlalchemy import Column, BigInteger, Text, DateTime, SmallInteger, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class TranslateRecord(Base):
    __tablename__ = "translate_record"

    translate_id = Column(BigInteger, primary_key=True, autoincrement=True)
    segment_id = Column(BigInteger, ForeignKey("segment_result.segment_id"), nullable=False)
    english_original = Column(Text, nullable=False)
    chinese_translate = Column(Text, nullable=False)
    translate_time = Column(DateTime, nullable=False, default=func.now())
    translate_status = Column(SmallInteger, nullable=False)
    system_id = Column(BigInteger, nullable=True)

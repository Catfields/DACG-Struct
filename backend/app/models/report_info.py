from sqlalchemy import Column, BigInteger, Text, String, DateTime, SmallInteger, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class ReportInfo(Base):
    __tablename__ = "report_info"

    report_id = Column(BigInteger, primary_key=True, autoincrement=True)
    xray_id = Column(BigInteger, ForeignKey("xray_info.xray_id"), nullable=False)
    segment_id = Column(BigInteger, ForeignKey("segment_result.segment_id"), nullable=False)
    report_content = Column(Text, nullable=False)
    report_pdf_path = Column(String(255), nullable=True)
    generate_time = Column(DateTime, nullable=False, default=func.now())
    audit_status = Column(SmallInteger, nullable=False, default=0)
    audit_user_id = Column(BigInteger, ForeignKey("user.user_id"), nullable=True)
    audit_time = Column(DateTime, nullable=True)
    revise_content = Column(Text, nullable=True)
    system_id = Column(BigInteger, nullable=True)

from sqlalchemy import Column, BigInteger, Text, String, DateTime, SmallInteger, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class ReportHistory(Base):
    __tablename__ = "report_history"

    history_id = Column(BigInteger, primary_key=True, autoincrement=True)
    report_id = Column(BigInteger, ForeignKey("report_info.report_id", ondelete="CASCADE"), nullable=False)
    xray_id = Column(BigInteger, ForeignKey("xray_info.xray_id"), nullable=False)
    segment_id = Column(BigInteger, ForeignKey("segment_result.segment_id"), nullable=False)
    parent_history_id = Column(BigInteger, ForeignKey("report_history.history_id", ondelete="SET NULL"), nullable=True)
    action_type = Column(String(50), nullable=False)
    action_user_id = Column(BigInteger, ForeignKey("user.user_id", ondelete="SET NULL"), nullable=True)
    action_time = Column(DateTime, nullable=False, default=func.now())
    action_note = Column(String(255), nullable=True)
    report_content = Column(Text, nullable=False)
    revise_content = Column(Text, nullable=True)
    report_pdf_path = Column(String(255), nullable=True)
    generate_time = Column(DateTime, nullable=True)
    audit_status = Column(SmallInteger, nullable=False, default=0)
    audit_user_id = Column(BigInteger, ForeignKey("user.user_id", ondelete="SET NULL"), nullable=True)
    audit_time = Column(DateTime, nullable=True)
    system_id = Column(BigInteger, nullable=True)

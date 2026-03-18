from sqlalchemy import Column, BigInteger, String, DateTime, SmallInteger, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class OperationLog(Base):
    __tablename__ = "operation_log"

    log_id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("user.user_id"), nullable=False)
    user_name = Column(String(50), nullable=False)
    operation_type = Column(String(50), nullable=False)
    operation_content = Column(String(500), nullable=False)
    operation_time = Column(DateTime, nullable=False, default=func.now())
    ip_address = Column(String(50), nullable=True)
    operation_status = Column(SmallInteger, nullable=False)
    system_id = Column(BigInteger, nullable=True)

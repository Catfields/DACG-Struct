from sqlalchemy import Column, BigInteger, String, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Role(Base):
    __tablename__ = "role"

    role_id = Column(BigInteger, primary_key=True, autoincrement=True)
    role_name = Column(String(50), nullable=False)
    role_desc = Column(String(200), nullable=True)
    create_time = Column(DateTime, nullable=False, default=func.now())
    system_id = Column(BigInteger, nullable=True)

    users = relationship("User", back_populates="role")

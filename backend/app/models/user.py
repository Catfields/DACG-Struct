from sqlalchemy import Column, BigInteger, String, SmallInteger, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class User(Base):
    __tablename__ = "user"

    user_id = Column(BigInteger, primary_key=True, autoincrement=True)
    login_name = Column(String(50), nullable=False, unique=True)
    login_flag = Column(SmallInteger, nullable=False)
    pwd = Column(String(100), nullable=False)
    real_name = Column(String(50), nullable=False)
    role_id = Column(BigInteger, ForeignKey("role.role_id"), nullable=True)
    phone = Column(String(20), nullable=True)

    role = relationship("Role", back_populates="users")

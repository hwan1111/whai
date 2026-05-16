import enum
from sqlalchemy import Column, String, SmallInteger, Enum, DateTime
from sqlalchemy.sql import func
from backend.db import Base


class GenderEnum(str, enum.Enum):
    M = "M"
    F = "F"
    OTHER = "OTHER"


class User(Base):
    __tablename__ = "member"

    user_id = Column(String(50), primary_key=True)
    name = Column(String(100), nullable=False)
    password_hash = Column(String(255), nullable=False)
    birth_year = Column(SmallInteger, nullable=True)
    gender = Column(Enum(GenderEnum), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.sql import func
from backend.db import Base


class UserReport(Base):
    __tablename__ = "user_report"

    id = Column(String(50), primary_key=True)
    user_id = Column(String(50), nullable=False, index=True)
    content = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

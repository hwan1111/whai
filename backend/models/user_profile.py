from sqlalchemy import Column, String, ForeignKey, DateTime
from sqlalchemy.sql import func
from backend.db import Base


class UserProfile(Base):
    __tablename__ = "user_profile"

    user_id = Column(String(20), ForeignKey("member.user_id", ondelete="CASCADE", onupdate="CASCADE"), primary_key=True)
    profile_image_url = Column(String(500), nullable=True)
    original_file_name = Column(String(255), nullable=True)
    age_group = Column(String(50), nullable=True)
    invest_type = Column(String(10), nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

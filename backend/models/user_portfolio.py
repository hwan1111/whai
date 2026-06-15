from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.sql import func
from backend.db import Base


class UserPortfolio(Base):
    __tablename__ = "user_portfolio"

    id = Column(String(50), primary_key=True)
    user_id = Column(String(50), nullable=False, index=True)
    content = Column(Text, nullable=True)
    # 시스템이 생성한 LLM 포트폴리오 분석 결과(JSON 문자열). 사용자 원본 스냅샷인
    # content와 분리해 저장하여 재생성/백필 시 `WHERE ai_analysis IS NULL` 조회가 쉽다.
    ai_analysis = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

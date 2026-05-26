from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.sql import func
from backend.db import Base


class NewsEs(Base):
    __tablename__ = "news_es"

    es_doc_id = Column(String(255), primary_key=True)
    content = Column(Text, nullable=False)
    indexed_at = Column(DateTime, server_default=func.now())

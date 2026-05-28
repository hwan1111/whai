from sqlalchemy import Column, Integer, String, Text, Float, Date, DateTime
from sqlalchemy.sql import func
from backend.db import Base


class Regime(Base):
    __tablename__ = "regime"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(20), nullable=False, index=True)
    regime_id = Column(Integer, nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    days = Column(Integer)
    direction = Column(String(10))
    cum_return = Column(Float)
    vol_trend = Column(String(20))
    news_count = Column(Integer)
    tokens_in = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())


class RegimeSummary(Base):
    __tablename__ = "regime_summary"

    id = Column(Integer, primary_key=True, autoincrement=True)
    regime_pk = Column(Integer, unique=True, nullable=False)
    cause = Column(Text)
    vol_insight = Column(Text)
    confidence = Column(String(10))
    reasoning = Column(Text)
    tokens_out = Column(Integer)
    coverage = Column(Float)
    novelty = Column(Float)
    sem_max = Column(Float)
    sem_mean = Column(Float)
    created_at = Column(DateTime, server_default=func.now())

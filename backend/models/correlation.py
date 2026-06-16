from datetime import datetime

from sqlalchemy import BigInteger, Column, String, Date, Float, DateTime, Text
from sqlalchemy.sql import func

from backend.db import Base


class Correlation(Base):
    __tablename__ = "correlation"

    ticker_a          = Column(String(20), primary_key=True)
    ticker_b          = Column(String(20), primary_key=True)
    period            = Column(String(5),  primary_key=True)   # 1W/1M/3M/6M/1Y/3Y/ALL
    computed_date     = Column(Date,       primary_key=True)
    correlation_coeff = Column(Float, nullable=False)
    created_at        = Column(DateTime, default=datetime.utcnow)


class CorrelationInsight(Base):
    __tablename__ = "correlation_insight"

    id          = Column(BigInteger, primary_key=True, autoincrement=True)
    pair_key    = Column(String(50), nullable=False)     # "{ticker_a}|{ticker_b}"
    date        = Column(Date,       nullable=False)
    description = Column(Text,       nullable=False)
    created_at  = Column(DateTime,   server_default=func.now())

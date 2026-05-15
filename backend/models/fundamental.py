from sqlalchemy import Column, String, Date, Float, BigInteger
from backend.db import Base


class Fundamental(Base):
    __tablename__ = "fundamental"

    ticker = Column(String(20), primary_key=True)
    date   = Column(Date, nullable=False)
    per    = Column(Float, nullable=True)
    pbr    = Column(Float, nullable=True)
    market_cap = Column(BigInteger, nullable=True)  # 단위: 백만원

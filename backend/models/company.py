from sqlalchemy import Column, String
from backend.db import Base


class Company(Base):
    __tablename__ = "company"

    ticker = Column(String(20), primary_key=True)
    name = Column(String(255), nullable=False)
    sector = Column(String(100))
    currency_code = Column(String(3), nullable=False)
    market = Column(String(20))

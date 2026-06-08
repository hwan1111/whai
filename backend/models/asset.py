from sqlalchemy import Column, String
from backend.db import Base


class Asset(Base):
    __tablename__ = "asset"

    ticker = Column(String(20), primary_key=True)
    name = Column(String(255), nullable=False)
    sector = Column(String(100))

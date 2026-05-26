from sqlalchemy import Column, ForeignKey, String
from backend.db import Base


class FavoriteTicker(Base):
    __tablename__ = "favorite_ticker"

    user_id = Column(String(50), ForeignKey("user.user_id", ondelete="CASCADE"), primary_key=True)
    ticker  = Column(String(20), ForeignKey("company.ticker", ondelete="CASCADE"), primary_key=True)


class FavoriteExchange(Base):
    __tablename__ = "favorite_exchange"

    user_id       = Column(String(50), ForeignKey("user.user_id", ondelete="CASCADE"), primary_key=True)
    currency_pair = Column(String(10), ForeignKey("exchange_rate.currency_pair", ondelete="CASCADE"), primary_key=True)

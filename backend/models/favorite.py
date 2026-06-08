from sqlalchemy import Column, ForeignKey, String
from backend.db import Base


class FavoriteAsset(Base):
    __tablename__ = "favorite_asset"

    user_id = Column(String(50), ForeignKey("user.user_id", ondelete="CASCADE"), primary_key=True)
    ticker  = Column(String(20), ForeignKey("asset.ticker", ondelete="CASCADE"), primary_key=True)

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.db import get_db
from backend.routers.auth import _get_user_id

router = APIRouter(prefix="/favorites", tags=["favorites"])

EXCHANGE_PAIRS = {'KRW/USD', 'KRW/JPY', 'KRW/EUR', 'KRW/CNY', 'KRW/CHF', 'KRW/GBP'}


class FavoritesBody(BaseModel):
    assets: list[str] = []


@router.get("")
def get_favorites(
    user_id: str = Depends(_get_user_id),
    db: Session = Depends(get_db),
) -> dict:
    tickers = db.execute(
        text("SELECT ticker FROM favorite_ticker WHERE user_id = :uid"),
        {"uid": user_id},
    ).fetchall()
    pairs = db.execute(
        text("SELECT currency_pair FROM favorite_exchange WHERE user_id = :uid"),
        {"uid": user_id},
    ).fetchall()
    assets = [r.ticker for r in tickers] + [r.currency_pair for r in pairs]
    return {"assets": assets}


@router.put("")
def put_favorites(
    body: FavoritesBody,
    user_id: str = Depends(_get_user_id),
    db: Session = Depends(get_db),
) -> dict:
    tickers = [a for a in body.assets if a not in EXCHANGE_PAIRS]
    pairs   = [a for a in body.assets if a in EXCHANGE_PAIRS]

    db.execute(text("DELETE FROM favorite_ticker  WHERE user_id = :uid"), {"uid": user_id})
    db.execute(text("DELETE FROM favorite_exchange WHERE user_id = :uid"), {"uid": user_id})

    for t in tickers:
        db.execute(
            text("INSERT IGNORE INTO favorite_ticker (user_id, ticker) VALUES (:uid, :t)"),
            {"uid": user_id, "t": t},
        )
    for p in pairs:
        db.execute(
            text("INSERT IGNORE INTO favorite_exchange (user_id, currency_pair) VALUES (:uid, :p)"),
            {"uid": user_id, "p": p},
        )
    db.commit()
    return {"ok": True}

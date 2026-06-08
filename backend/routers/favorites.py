from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.db import get_db
from backend.routers.auth import _get_user_id

router = APIRouter(prefix="/favorites", tags=["favorites"])


class FavoritesBody(BaseModel):
    assets: list[str] = []


@router.get("")
def get_favorites(
    user_id: str = Depends(_get_user_id),
    db: Session = Depends(get_db),
) -> dict:
    rows = db.execute(
        text("SELECT ticker FROM favorite_asset WHERE user_id = :uid"),
        {"uid": user_id},
    ).fetchall()
    return {"assets": [r.ticker for r in rows]}


@router.put("")
def put_favorites(
    body: FavoritesBody,
    user_id: str = Depends(_get_user_id),
    db: Session = Depends(get_db),
) -> dict:
    db.execute(text("DELETE FROM favorite_asset WHERE user_id = :uid"), {"uid": user_id})
    for ticker in body.assets:
        db.execute(
            text("INSERT IGNORE INTO favorite_asset (user_id, ticker) VALUES (:uid, :t)"),
            {"uid": user_id, "t": ticker},
        )
    db.commit()
    return {"ok": True}

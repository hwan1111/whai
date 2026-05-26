import json
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.models.news import NewsEs

router = APIRouter(prefix="/news", tags=["news"])


@router.get("")
def get_news(
    ticker: str = Query(default=""),
    days: int = Query(default=7),
    db: Session = Depends(get_db),
) -> list[dict]:
    cutoff = date.today() - timedelta(days=days)
    rows = db.query(NewsEs).all()

    result = []
    for row in rows:
        try:
            doc = json.loads(row.content)
        except Exception:
            continue

        pub_str = doc.get("published_at", "")
        try:
            pub_date = date.fromisoformat(pub_str)
        except Exception:
            continue

        if pub_date < cutoff:
            continue
        if ticker and doc.get("ticker") != ticker:
            continue

        result.append({
            "ticker": doc.get("ticker", ""),
            "title": doc.get("title", ""),
            "body": doc.get("body", ""),
            "source": doc.get("source", ""),
            "published_at": pub_str,
            "date_str": doc.get("date_str", pub_str),
            "ai_summary": doc.get("ai_summary", ""),
        })

    result.sort(key=lambda x: x["published_at"], reverse=True)
    return result

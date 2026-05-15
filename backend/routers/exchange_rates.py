from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.db import get_db

router = APIRouter(prefix="/exchange-rates", tags=["exchange-rates"])

PERIOD_DAYS = {
    "1W": 7, "1M": 30, "3M": 90, "6M": 180,
    "1Y": 365, "3Y": 1095, "ALL": 3650,
}

VALID_PAIRS = {"KRW/USD", "KRW/JPY", "KRW/EUR", "KRW/GBP", "KRW/CHF", "KRW/CNY"}


@router.get("/latest")
def get_latest_exchange_rates(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(text("""
        SELECT er1.currency_pair, er1.rate,
               (SELECT rate FROM exchange_rate er2
                WHERE er2.currency_pair = er1.currency_pair AND er2.date < er1.date
                ORDER BY er2.date DESC LIMIT 1) AS prev_rate
        FROM exchange_rate er1
        WHERE er1.base_currency_code = 'KRW'
          AND er1.date = (
              SELECT MAX(date) FROM exchange_rate
              WHERE currency_pair = er1.currency_pair)
    """)).fetchall()

    result = []
    for r in rows:
        rate = float(r.rate)
        prev = float(r.prev_rate) if r.prev_rate else rate
        change_pct = round((rate - prev) / prev * 100, 2) if prev else 0.0
        result.append({
            "pair": r.currency_pair,
            "rate": round(rate, 2),
            "prev_rate": round(prev, 2),
            "change_pct": change_pct,
        })

    return result


@router.get("/history")
def get_exchange_rate_history(
    pair: str = Query(...),
    period: str = Query(default="3M"),
    db: Session = Depends(get_db),
) -> list[dict]:
    if pair not in VALID_PAIRS:
        return []

    days = PERIOD_DAYS.get(period, 90)
    cutoff = date.today() - timedelta(days=days)

    rows = db.execute(text("""
        SELECT date, rate FROM exchange_rate
        WHERE currency_pair = :pair AND date >= :cutoff
        ORDER BY date ASC
    """), {"pair": pair, "cutoff": str(cutoff)}).fetchall()

    if not rows:
        return []

    base = float(rows[0].rate)
    return [
        {
            "date": str(r.date),
            "rate": round(float(r.rate), 2),
            "return_pct": round((float(r.rate) - base) / base * 100, 2),
        }
        for r in rows
    ]

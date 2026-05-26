from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.db import get_db

router = APIRouter(prefix="/prices", tags=["prices"])

PERIOD_DAYS = {
    "1W": 7, "1M": 30, "3M": 90, "6M": 180,
    "1Y": 365, "3Y": 1095, "ALL": 3650,
}


@router.get("/latest")
def get_latest_prices(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(text("""
        SELECT p1.ticker, p1.close, p1.date, c.name, c.sector,
               (SELECT close FROM price p2
                WHERE p2.ticker = p1.ticker AND p2.date < p1.date
                ORDER BY p2.date DESC LIMIT 1) AS prev_close
        FROM price p1
        JOIN company c ON p1.ticker = c.ticker
        WHERE p1.date = (SELECT MAX(date) FROM price p3 WHERE p3.ticker = p1.ticker)
        ORDER BY c.sector, p1.ticker
    """)).fetchall()

    result = []
    for r in rows:
        prev = int(r.prev_close) if r.prev_close else r.close
        change_pct = round((r.close - prev) / prev * 100, 2) if prev else 0.0
        result.append({
            "ticker": r.ticker,
            "name": r.name,
            "sector": r.sector,
            "close": r.close,
            "change": round(r.close - prev, 2),
            "change_pct": change_pct,
            "date": str(r.date),
        })
    return result


@router.get("/{ticker}/history")
def get_price_history(
    ticker: str,
    period: str = Query(default="3M"),
    db: Session = Depends(get_db),
) -> list[dict]:
    days = PERIOD_DAYS.get(period, 90)
    cutoff = date.today() - timedelta(days=days)
    rows = db.execute(text("""
        SELECT date, close FROM price
        WHERE ticker = :ticker AND date >= :cutoff
        ORDER BY date ASC
    """), {"ticker": ticker, "cutoff": str(cutoff)}).fetchall()

    if not rows:
        return []

    base = rows[0].close
    return [
        {
            "date": str(r.date),
            "close": r.close,
            "return_pct": round((r.close - base) / base * 100, 2),
        }
        for r in rows
    ]


@router.get("/{ticker}/stats")
def get_price_stats(
    ticker: str,
    db: Session = Depends(get_db),
) -> dict:
    cutoff = date.today() - timedelta(days=365)
    row = db.execute(text("""
        SELECT MAX(close) AS high52, MIN(close) AS low52
        FROM price WHERE ticker = :ticker AND date >= :cutoff
    """), {"ticker": ticker, "cutoff": str(cutoff)}).fetchone()

    latest = db.execute(text("""
        SELECT close, volume FROM price
        WHERE ticker = :ticker ORDER BY date DESC LIMIT 1
    """), {"ticker": ticker}).fetchone()

    fund = db.execute(text("""
        SELECT per, pbr, market_cap FROM fundamental WHERE ticker = :ticker
    """), {"ticker": ticker}).fetchone()

    return {
        "high52": int(row.high52) if row and row.high52 else None,
        "low52": int(row.low52) if row and row.low52 else None,
        "volume": int(latest.volume) if latest and latest.volume else None,
        "per": round(float(fund.per), 2) if fund and fund.per else None,
        "pbr": round(float(fund.pbr), 2) if fund and fund.pbr else None,
        "market_cap": int(fund.market_cap) if fund and fund.market_cap else None,
    }

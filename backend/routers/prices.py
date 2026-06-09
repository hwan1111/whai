import re
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.db import get_db

router = APIRouter(prefix="/prices", tags=["prices"])

_TICKER_RE = re.compile(r'^([0-9]{6}|[A-Z]{3})$')
_DECIMAL_TICKER_RE = re.compile(r'^([A-Z]{3}|000000)$')

def _validate_ticker(ticker: str) -> None:
    if not _TICKER_RE.match(ticker):
        raise HTTPException(status_code=400, detail="유효하지 않은 ticker 형식입니다.")

PERIOD_DAYS = {
    "1W": 7, "1M": 30, "3M": 90, "6M": 180,
    "1Y": 365, "3Y": 1095, "ALL": 3650,
}


@router.get("/latest")
def get_latest_prices(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(text("""
        WITH ranked AS (
            SELECT ticker, close, date,
                   LAG(close) OVER (PARTITION BY ticker ORDER BY date) AS prev_close,
                   ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) AS rn
            FROM price
        )
        SELECT r.ticker, r.close, r.date, c.name, c.sector, r.prev_close
        FROM ranked r
        JOIN asset c ON r.ticker = c.ticker
        WHERE r.rn = 1
        ORDER BY c.sector, r.ticker
    """)).fetchall()

    result = []
    for r in rows:
        to_close = float if _DECIMAL_TICKER_RE.match(r.ticker) else int
        close = float(r.close)
        prev = float(r.prev_close) if r.prev_close else close
        change_pct = round((close - prev) / prev * 100, 2) if prev else 0.0
        result.append({
            "ticker": r.ticker,
            "name": r.name,
            "sector": r.sector,
            "close": to_close(r.close),
            "change": to_close(round(close - prev, 2)),
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
    _validate_ticker(ticker)
    days = PERIOD_DAYS.get(period, 90)
    cutoff = date.today() - timedelta(days=days)
    rows = db.execute(text("""
        SELECT date, close FROM price
        WHERE ticker = :ticker AND date >= :cutoff
        ORDER BY date ASC
    """), {"ticker": ticker, "cutoff": str(cutoff)}).fetchall()

    if not rows:
        return []

    to_close = float if _DECIMAL_TICKER_RE.match(ticker) else int
    base = float(rows[0].close)
    return [
        {
            "date": str(r.date),
            "close": to_close(r.close),
            "return_pct": round((float(r.close) - base) / base * 100, 2),
        }
        for r in rows
    ]


@router.get("/{ticker}/stats")
def get_price_stats(
    ticker: str,
    db: Session = Depends(get_db),
) -> dict:
    _validate_ticker(ticker)
    cutoff = date.today() - timedelta(days=365)
    row = db.execute(text("""
        SELECT MAX(close) AS high52, MIN(close) AS low52
        FROM price WHERE ticker = :ticker AND date >= :cutoff
    """), {"ticker": ticker, "cutoff": str(cutoff)}).fetchone()

    latest = db.execute(text("""
        SELECT close, volume FROM price
        WHERE ticker = :ticker ORDER BY date DESC LIMIT 1
    """), {"ticker": ticker}).fetchone()

    prev_row = db.execute(text("""
        SELECT close FROM price
        WHERE ticker = :ticker ORDER BY date DESC LIMIT 1 OFFSET 1
    """), {"ticker": ticker}).fetchone()

    fund = db.execute(text("""
        SELECT per, pbr, market_cap FROM fundamental
        WHERE ticker = :ticker ORDER BY date DESC LIMIT 1
    """), {"ticker": ticker}).fetchone()

    close = int(latest.close) if latest and latest.close else None
    prev = int(prev_row.close) if prev_row and prev_row.close else close
    change = round(close - prev, 2) if close and prev else None
    change_pct = round((close - prev) / prev * 100, 2) if close and prev else None

    return {
        "high52": int(row.high52) if row and row.high52 else None,
        "low52": int(row.low52) if row and row.low52 else None,
        "volume": int(latest.volume) if latest and latest.volume else None,
        "per": round(float(fund.per), 2) if fund and fund.per is not None and float(fund.per) > 0 else None,
        "pbr": round(float(fund.pbr), 2) if fund and fund.pbr is not None and float(fund.pbr) > 0 else None,
        "market_cap": int(fund.market_cap) if fund and fund.market_cap else None,
        "change": change,
        "change_pct": change_pct,
    }

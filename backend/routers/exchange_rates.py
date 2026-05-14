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

# Frontend pair → (DB pair stored as USD/X, multiplier)
# KRW/USD  = USD/KRW rate directly  (1 USD = X KRW)
# KRW/EUR  = USD/KRW / USD/EUR      (1 EUR = X KRW)
# KRW/JPY  = USD/KRW / USD/JPY *100 (100 JPY = X KRW)
PAIR_MAP: dict[str, tuple[str, int]] = {
    "KRW/USD": ("USD/KRW", 1),
    "KRW/EUR": ("USD/EUR", 1),
    "KRW/JPY": ("USD/JPY", 100),
    "KRW/CNY": ("USD/CNY", 1),
    "KRW/CHF": ("USD/CHF", 1),
    "KRW/GBP": ("USD/GBP", 1),
}


def _cross(krw_usd: float, fx: float, db_pair: str, mult: int) -> float:
    if db_pair == "USD/KRW":
        return round(krw_usd, 2)
    return round(krw_usd / fx * mult, 2)


@router.get("/latest")
def get_latest_exchange_rates(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(text("""
        SELECT er1.currency_pair, er1.rate,
               (SELECT rate FROM exchange_rate er2
                WHERE er2.currency_pair = er1.currency_pair AND er2.date < er1.date
                ORDER BY er2.date DESC LIMIT 1) AS prev_rate
        FROM exchange_rate er1
        WHERE er1.base_currency_code = 'USD'
          AND er1.date = (
              SELECT MAX(date) FROM exchange_rate
              WHERE currency_pair = er1.currency_pair)
    """)).fetchall()

    db_rates = {
        r.currency_pair: {
            "rate": float(r.rate),
            "prev": float(r.prev_rate or r.rate),
        }
        for r in rows
    }
    krw_usd = db_rates.get("USD/KRW", {}).get("rate", 1400.0)
    krw_usd_prev = db_rates.get("USD/KRW", {}).get("prev", krw_usd)

    result = []
    for fe_pair, (db_pair, mult) in PAIR_MAP.items():
        if db_pair not in db_rates:
            continue
        fx = db_rates[db_pair]["rate"]
        fx_prev = db_rates[db_pair]["prev"]
        r = _cross(krw_usd, fx, db_pair, mult)
        p = _cross(krw_usd_prev, fx_prev, db_pair, mult)
        change_pct = round((r - p) / p * 100, 2) if p else 0.0
        result.append({"pair": fe_pair, "rate": r, "prev_rate": p, "change_pct": change_pct})

    return result


@router.get("/{pair}/history")
def get_exchange_rate_history(
    pair: str,
    period: str = Query(default="3M"),
    db: Session = Depends(get_db),
) -> list[dict]:
    if pair not in PAIR_MAP:
        return []

    db_pair, mult = PAIR_MAP[pair]
    days = PERIOD_DAYS.get(period, 90)
    cutoff = date.today() - timedelta(days=days)

    if db_pair == "USD/KRW":
        rows = db.execute(text("""
            SELECT date, CAST(rate AS DECIMAL(18,4)) AS rate
            FROM exchange_rate
            WHERE currency_pair = 'USD/KRW' AND date >= :cutoff
            ORDER BY date ASC
        """), {"cutoff": str(cutoff)}).fetchall()

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

    rows = db.execute(text("""
        SELECT kr.date,
               CAST(kr.rate AS DECIMAL(18,4)) AS krw_rate,
               CAST(fx.rate AS DECIMAL(18,4)) AS fx_rate
        FROM exchange_rate kr
        JOIN exchange_rate fx
          ON kr.date = fx.date AND fx.currency_pair = :fx_pair
        WHERE kr.currency_pair = 'USD/KRW' AND kr.date >= :cutoff
        ORDER BY kr.date ASC
    """), {"fx_pair": db_pair, "cutoff": str(cutoff)}).fetchall()

    if not rows:
        return []

    computed = [
        {
            "date": str(r.date),
            "rate": round(float(r.krw_rate) / float(r.fx_rate) * mult, 2),
        }
        for r in rows
    ]
    base = computed[0]["rate"]
    for c in computed:
        c["return_pct"] = round((c["rate"] - base) / base * 100, 2)
    return computed

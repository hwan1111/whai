from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.models.company import Company
from backend.models.regime import Regime, RegimeSummary

router = APIRouter(prefix="/news", tags=["news"])


@router.get("")
def get_news(
    ticker: str = Query(default=""),
    days: int = Query(default=7),
    db: Session = Depends(get_db),
) -> list[dict]:
    cutoff = date.today() - timedelta(days=days)

    query = (
        db.query(Regime, RegimeSummary, Company.name)
        .outerjoin(RegimeSummary, RegimeSummary.regime_pk == Regime.id)
        .outerjoin(Company, Company.ticker == Regime.ticker)
        .filter(Regime.end_date >= cutoff)
    )
    if ticker:
        query = query.filter(Regime.ticker == ticker)

    rows = query.order_by(Regime.end_date.desc()).all()

    return [
        {
            "ticker": reg.ticker,
            "name": name or reg.ticker,
            "direction": reg.direction or "",
            "start_date": reg.start_date.isoformat(),
            "end_date": reg.end_date.isoformat(),
            "cum_return": reg.cum_return,
            "cause": summ.cause if summ else "",
            "vol_insight": summ.vol_insight if summ else "",
            "confidence": summ.confidence if summ else "",
        }
        for reg, summ, name in rows
    ]

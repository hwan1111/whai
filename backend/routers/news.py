import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

import boto3
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.models.asset import Asset
from backend.models.regime import Regime

_S3_BUCKET = os.getenv("AWS_S3_BUCKET", "fisa-news-archive")
_S3_REGION = "ap-northeast-2"

router = APIRouter(prefix="/news", tags=["news"])


def _fetch_summary_from_s3(s3_client, ticker: str, start_date: str, end_date: str) -> dict:
    """summary/{ticker}/{start}_{end}.json 에서 cause/vol_insight/confidence 추출."""
    key = f"summary/{ticker}/{start_date}_{end_date}.json"
    try:
        resp = s3_client.get_object(Bucket=_S3_BUCKET, Key=key)
        payload = json.loads(resp["Body"].read().decode("utf-8"))
        analysis = payload.get("llm_analysis") or {}
        return {
            "cause": analysis.get("cause", ""),
            "vol_insight": analysis.get("vol_insight", ""),
            "confidence": analysis.get("confidence", ""),
        }
    except Exception:
        return {"cause": "", "vol_insight": "", "confidence": ""}


@router.get("")
def get_news(
    ticker: str = Query(default=""),
    days: int = Query(default=7),
    db: Session = Depends(get_db),
) -> list[dict]:
    cutoff = date.today() - timedelta(days=days)

    query = (
        db.query(Regime, Asset.name)
        .outerjoin(Asset, Asset.ticker == Regime.ticker)
        .filter(Regime.end_date >= cutoff)
    )
    if ticker:
        query = query.filter(Regime.ticker == ticker)

    rows = query.order_by(Regime.end_date.desc()).all()
    if not rows:
        return []

    s3 = boto3.client("s3", region_name=_S3_REGION)

    def _fetch(reg: Regime):
        return reg.id, _fetch_summary_from_s3(
            s3, reg.ticker, reg.start_date.isoformat(), reg.end_date.isoformat()
        )

    summaries: dict[int, dict] = {}
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(_fetch, reg): reg for reg, _ in rows}
        for fut in as_completed(futures):
            rid, data = fut.result()
            summaries[rid] = data

    return [
        {
            "ticker": reg.ticker,
            "name": name or reg.ticker,
            "direction": reg.direction or "",
            "start_date": reg.start_date.isoformat(),
            "end_date": reg.end_date.isoformat(),
            "cum_return": reg.cum_return,
            **summaries.get(reg.id, {"cause": "", "vol_insight": "", "confidence": ""}),
        }
        for reg, name in rows
    ]

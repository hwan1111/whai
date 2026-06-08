"""BOK ECOS API를 통한 KRW 환율 데이터 조회.

통계표: 731Y001 (주요국통화의대원화환율)
저장 형식: KRW/USD
"""

import os

import pandas as pd
import requests

BASE_CURRENCY = "KRW"

# BOK ECOS 통계항목코드 → 통화코드
BOK_ITEMS: dict[str, str] = {
    "0000001": "USD",   # 미국 달러 (1달러)
}

_BOK_STAT = "731Y001"
_BOK_BASE = "https://ecos.bok.or.kr/api/StatisticSearch"


def fetch_bok(start_date: str, end_date: str, page_size: int = 10000) -> list[dict]:
    """BOK ECOS에서 KRW 환율 조회 (페이지네이션 자동 처리).

    Args:
        start_date: YYYYMMDD
        end_date:   YYYYMMDD

    Returns:
        BOK API row 목록 (각 행에 ITEM_CODE1, TIME, DATA_VALUE 포함).
    """
    api_key = os.getenv("BOK_API_KEY")
    if not api_key:
        raise RuntimeError("BOK_API_KEY가 환경변수에 없습니다.")

    all_rows: list[dict] = []
    start_idx = 1

    while True:
        end_idx = start_idx + page_size - 1
        url = (
            f"{_BOK_BASE}/{api_key}/json/kr"
            f"/{start_idx}/{end_idx}/{_BOK_STAT}/D/{start_date}/{end_date}"
        )
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        body = resp.json()

        if "RESULT" in body:
            code = body["RESULT"].get("CODE", "")
            msg = body["RESULT"].get("MESSAGE", "")
            raise RuntimeError(f"BOK API 오류 [{code}]: {msg}")

        search = body.get("StatisticSearch", {})
        total = int(search.get("list_total_count", 0))
        rows = search.get("row", [])
        all_rows.extend(rows)

        if end_idx >= total or not rows:
            break
        start_idx += page_size

    return all_rows


def make_exchange_rate_df(rows: list[dict]) -> pd.DataFrame:
    """BOK API row 목록을 exchange_rate 테이블용 DataFrame으로 변환."""
    records = []
    for r in rows:
        item_code = r.get("ITEM_CODE1", "")
        if item_code not in BOK_ITEMS:
            continue
        target = BOK_ITEMS[item_code]

        time_str = r.get("TIME", "")
        if len(time_str) == 8:
            date_str = f"{time_str[:4]}-{time_str[4:6]}-{time_str[6:]}"
        else:
            continue

        raw_val = r.get("DATA_VALUE", "")
        if not raw_val or raw_val.strip() in ("", "-"):
            continue
        try:
            rate = float(raw_val)
        except ValueError:
            continue

        records.append({
            "currency_pair": f"KRW/{target}",
            "date": date_str,
            "base_currency_code": "KRW",
            "target_currency_code": target,
            "rate": rate,
        })

    return pd.DataFrame(records)

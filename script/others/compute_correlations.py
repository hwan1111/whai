"""
12개 종목 × 7 기간 Pearson 상관계수 증분 적재 (1일 1행).

Run manually:
    python script/others/compute_correlations.py

Or via Airflow: finance_market_data_daily / compute_correlations
(kospi, stocks, exchange_rates 태스크 완료 후 실행)
"""

import os
import sys
from datetime import date, datetime, timedelta, timezone
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=True)

from sqlalchemy import create_engine, text

# prices.py PERIOD_DAYS와 동일
PERIOD_DAYS: dict[str, int] = {
    "1W":  7,
    "1M":  30,
    "3M":  90,
    "6M":  180,
    "1Y":  365,
    "3Y":  1095,
    "ALL": 3650,
}

TICKERS = [
    "000000",  # KOSPI
    "005930",  # 삼성전자
    "000660",  # SK하이닉스
    "005380",  # 현대차
    "000270",  # 기아
    "079550",  # LIG넥스원
    "012450",  # 한화에어로스페이스
    "105560",  # KB금융
    "055550",  # 신한지주
    "051910",  # LG화학
    "096770",  # SK이노베이션
    "USD",     # USD/KRW
]


def get_engine():
    url = os.getenv("SERVICE_DATABASE_URL")
    if not url:
        raise RuntimeError("SERVICE_DATABASE_URL이 .env에 없습니다.")
    ca_path = ROOT / "config" / "certs" / "ca.pem"
    base_url = url.split("?")[0]
    db_url = f"{base_url}?charset=utf8mb4"
    connect_args = {"ssl": {"ca": str(ca_path)}} if ca_path.exists() else {}
    return create_engine(db_url, connect_args=connect_args, pool_pre_ping=True)


def _fetch_closes(engine, ticker: str, since: date | None) -> list[tuple[str, float]]:
    sql = "SELECT date, close FROM price WHERE ticker = :t"
    params: dict = {"t": ticker}
    if since:
        sql += " AND date >= :since"
        params["since"] = since
    sql += " ORDER BY date ASC"
    with engine.connect() as conn:
        return [(str(r.date), float(r.close)) for r in conn.execute(text(sql), params)]


def _daily_returns(closes: list[tuple[str, float]]) -> dict[str, float]:
    result: dict[str, float] = {}
    for i in range(1, len(closes)):
        _, c_prev = closes[i - 1]
        d_curr, c_curr = closes[i]
        if c_prev != 0:
            result[d_curr] = (c_curr - c_prev) / c_prev
    return result


def _pearson(ret_a: dict[str, float], ret_b: dict[str, float]) -> float | None:
    common = sorted(set(ret_a) & set(ret_b))
    n = len(common)
    if n < 5:
        return None
    a = [ret_a[d] for d in common]
    b = [ret_b[d] for d in common]
    ma = sum(a) / n
    mb = sum(b) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den_a = sum((x - ma) ** 2 for x in a) ** 0.5
    den_b = sum((y - mb) ** 2 for y in b) ** 0.5
    if den_a == 0 or den_b == 0:
        return None
    return num / (den_a * den_b)


def compute_correlations(engine) -> int:
    today = datetime.now(timezone.utc).date()
    today_iso = today.isoformat()
    total = 0

    for period, days in PERIOD_DAYS.items():
        since = today - timedelta(days=days)

        returns: dict[str, dict[str, float]] = {}
        for ticker in TICKERS:
            try:
                closes = _fetch_closes(engine, ticker, since)
                returns[ticker] = _daily_returns(closes)
            except Exception as exc:
                print(f"[상관계수 {period}] {ticker} 로드 실패: {exc}")
                returns[ticker] = {}

        rows = []
        for a, b in combinations(TICKERS, 2):
            if not returns.get(a) or not returns.get(b):
                continue
            v = _pearson(returns[a], returns[b])
            if v is None:
                continue
            rows.append({
                "ticker_a": a,
                "ticker_b": b,
                "period":   period,
                "computed_date": today_iso,
                "correlation_coeff": round(v, 4),
            })

        if rows:
            with engine.begin() as conn:
                conn.execute(
                    text("""
                        INSERT INTO correlation
                            (ticker_a, ticker_b, period, computed_date, correlation_coeff, created_at)
                        VALUES
                            (:ticker_a, :ticker_b, :period, :computed_date, :correlation_coeff, NOW())
                        ON DUPLICATE KEY UPDATE
                            correlation_coeff = VALUES(correlation_coeff),
                            created_at        = NOW()
                    """),
                    rows,
                )
            total += len(rows)
            print(f"[상관계수] {period}: {len(rows)}쌍 적재")

    print(f"[상관계수] 총 {total}쌍 적재 완료 ({today_iso})")
    return total


if __name__ == "__main__":
    compute_correlations(get_engine())

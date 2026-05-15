"""
Daily market data loader — KOSPI (1), stocks (10), exchange rates (6).

Run manually:
    python script/load_market_data.py

Or via Airflow DAG: finance_market_data_daily
"""

import os
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env.local", override=True)

from sqlalchemy import create_engine, text


def get_engine():
    url = os.getenv("SERVICE_DATABASE_URL")
    if not url:
        raise RuntimeError("SERVICE_DATABASE_URL이 .env.local에 없습니다.")
    ca_path = ROOT / "config" / "certs" / "ca.pem"
    base_url = url.split("?")[0]
    db_url = f"{base_url}?charset=utf8mb4"
    connect_args = {"ssl": {"ca": str(ca_path)}} if ca_path.exists() else {}
    return create_engine(db_url, connect_args=connect_args, pool_pre_ping=True)


def _latest_price_date(engine, ticker: str) -> date:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT MAX(date) FROM price WHERE ticker = :t"), {"t": ticker}
        ).fetchone()
    return row[0] if row[0] else date(2023, 1, 1)


def _latest_exchange_date(engine) -> date:
    with engine.connect() as conn:
        row = conn.execute(text("SELECT MAX(date) FROM exchange_rate")).fetchone()
    return row[0] if row[0] else date(2023, 1, 1)


def load_kospi(engine) -> int:
    """yfinance로 KOSPI 지수(000000) 증분 적재."""
    try:
        import yfinance as yf
    except ImportError:
        print("[KOSPI] yfinance 미설치: pip install yfinance")
        return 0

    last = _latest_price_date(engine, "000000")
    start = last + timedelta(days=1)
    today = date.today()

    if start > today:
        print("[KOSPI] 최신 상태")
        return 0

    df = yf.download(
        "^KS11",
        start=start.strftime("%Y-%m-%d"),
        end=(today + timedelta(days=1)).strftime("%Y-%m-%d"),
        progress=False,
    )
    if df.empty:
        print(f"[KOSPI] 데이터 없음 ({start} ~ {today})")
        return 0

    close = df["Close"].squeeze()
    volume = df["Volume"].squeeze()
    # squeeze()가 단일 행일 때 스칼라를 반환하므로 Series로 보장
    if not hasattr(close, "__len__"):
        close = df["Close"].iloc[:, 0] if df["Close"].ndim > 1 else df["Close"]
        volume = df["Volume"].iloc[:, 0] if df["Volume"].ndim > 1 else df["Volume"]
    rows = [
        {
            "ticker": "000000",
            "date": idx.strftime("%Y-%m-%d"),
            "close": round(float(close.iloc[i])),
            "volume": int(volume.iloc[i]),
        }
        for i, idx in enumerate(df.index)
    ]

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO price (ticker, date, close, volume)
                VALUES (:ticker, :date, :close, :volume)
                ON DUPLICATE KEY UPDATE close=VALUES(close), volume=VALUES(volume)
            """),
            rows,
        )

    print(f"[KOSPI] {len(rows)}건 적재 ({start} ~ {today})")
    return len(rows)


def load_stocks(engine) -> int:
    """pykrx로 company 테이블 KRW 종목(KOSPI 제외) 증분 적재."""
    try:
        from pykrx import stock as krx
    except ImportError:
        print("[주식] pykrx 미설치: pip install pykrx")
        return 0

    with engine.connect() as conn:
        tickers = {
            r.ticker: r.name
            for r in conn.execute(
                text("SELECT ticker, name FROM company WHERE currency_code='KRW' AND ticker != '000000'")
            )
        }

    if not tickers:
        print("[주식] company 테이블에 종목이 없습니다.")
        return 0

    today_str = date.today().strftime("%Y%m%d")
    total = 0

    for ticker, name in tickers.items():
        last = _latest_price_date(engine, ticker)
        start_str = (last + timedelta(days=1)).strftime("%Y%m%d")

        if start_str > today_str:
            print(f"[{ticker} {name}] 최신 상태")
            continue

        try:
            df = krx.get_market_ohlcv_by_date(start_str, today_str, ticker)
            if df.empty:
                print(f"[{ticker} {name}] 데이터 없음")
                continue

            rows = [
                {
                    "ticker": ticker,
                    "date": idx.strftime("%Y-%m-%d"),
                    "close": int(row["종가"]),
                    "volume": int(row["거래량"]),
                }
                for idx, row in df.iterrows()
            ]

            with engine.begin() as conn:
                conn.execute(
                    text("""
                        INSERT INTO price (ticker, date, close, volume)
                        VALUES (:ticker, :date, :close, :volume)
                        ON DUPLICATE KEY UPDATE close=VALUES(close), volume=VALUES(volume)
                    """),
                    rows,
                )

            total += len(rows)
            print(f"[{ticker} {name}] {len(rows)}건 적재")

        except Exception as e:
            print(f"[{ticker} {name}] 실패: {e}")

    print(f"[주식] 총 {total}건 적재")
    return total


def load_exchange_rates(engine) -> int:
    """Frankfurter API로 6개 환율 증분 적재."""
    from exchange_rate_fetcher import BASE_CURRENCY, fetch_frankfurter, make_exchange_rate_df
    from exchange_rate_loader import insert_exchange_rate

    last = _latest_exchange_date(engine)
    start = last + timedelta(days=1)
    today = date.today()

    if start > today:
        print("[환율] 최신 상태")
        return 0

    total = 0
    current = start

    while current <= today:
        req = current.strftime("%Y-%m-%d")
        try:
            data = fetch_frankfurter(req, base=BASE_CURRENCY)
            actual = data.get("date")
            if actual != req:
                print(f"[환율 SKIP] {req} (휴일 → {actual})")
            elif data.get("rates"):
                df = make_exchange_rate_df(data)
                insert_exchange_rate(engine, df)
                total += len(df)
                print(f"[환율] {req} {len(df)}건 적재")
        except Exception as e:
            print(f"[환율 ERROR] {req}: {e}")
        current += timedelta(days=1)

    print(f"[환율] 총 {total}건 적재")
    return total


def load_all(engine) -> dict[str, int]:
    """KOSPI, 주식, 환율 증분 적재 실행."""
    print("=== 일일 시장 데이터 적재 시작 ===\n")
    results = {
        "kospi": load_kospi(engine),
        "stocks": load_stocks(engine),
        "exchange_rates": load_exchange_rates(engine),
    }
    total = sum(results.values())
    print(
        f"\n=== 완료: 총 {total}건 "
        f"(KOSPI {results['kospi']} / 주식 {results['stocks']} / 환율 {results['exchange_rates']}) ==="
    )
    return results


if __name__ == "__main__":
    load_all(get_engine())

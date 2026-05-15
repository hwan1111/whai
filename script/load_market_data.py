"""
Daily market data loader — KOSPI (1), stocks (10), exchange rates (6), fundamentals (10).

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
    return row[0] if row[0] else date(2020, 1, 1)


def _latest_exchange_date(engine) -> date:
    with engine.connect() as conn:
        row = conn.execute(text("SELECT MAX(date) FROM exchange_rate")).fetchone()
    return row[0] if row[0] else date(2020, 1, 1)


def load_kospi(engine) -> int:
    """pykrx로 KOSPI 지수(000000) 증분 적재."""
    try:
        from pykrx import stock as krx
    except ImportError:
        print("[KOSPI] pykrx 미설치")
        return 0

    last = _latest_price_date(engine, "000000")
    start = last + timedelta(days=1)
    today = date.today()

    if start > today:
        print("[KOSPI] 최신 상태")
        return 0

    df = krx.get_index_ohlcv_by_date(
        start.strftime("%Y%m%d"),
        today.strftime("%Y%m%d"),
        "1001",  # KOSPI 지수 코드
    )
    if df.empty:
        print(f"[KOSPI] 데이터 없음 ({start} ~ {today})")
        return 0

    rows = [
        {
            "ticker": "000000",
            "date": idx.strftime("%Y-%m-%d"),
            "close": round(float(row["종가"])),
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
    """BOK ECOS API로 6개 KRW 환율 증분 적재."""
    from exchange_rate_fetcher import fetch_bok, make_exchange_rate_df
    from exchange_rate_loader import insert_exchange_rate

    last = _latest_exchange_date(engine)
    start = last + timedelta(days=1)
    today = date.today()

    if start > today:
        print("[환율] 최신 상태")
        return 0

    start_str = start.strftime("%Y%m%d")
    end_str = today.strftime("%Y%m%d")

    try:
        rows = fetch_bok(start_str, end_str)
    except Exception as e:
        print(f"[환율 ERROR] BOK API 호출 실패: {e}")
        return 0

    if not rows:
        print(f"[환율] 데이터 없음 ({start} ~ {today})")
        return 0

    df = make_exchange_rate_df(rows)
    if df.empty:
        print(f"[환율] 파싱된 데이터 없음 ({start} ~ {today})")
        return 0

    insert_exchange_rate(engine, df)
    print(f"[환율] {len(df)}건 적재 ({start} ~ {today})")
    return len(df)


def load_fundamentals(engine) -> int:
    """pykrx로 10개 종목 PER·PBR·시가총액 최신 스냅샷 적재."""
    try:
        from pykrx import stock as krx
    except ImportError:
        print("[펀더멘털] pykrx 미설치")
        return 0

    with engine.connect() as conn:
        tickers = [
            r.ticker for r in conn.execute(
                text("SELECT ticker FROM company WHERE currency_code='KRW' AND ticker != '000000'")
            )
        ]

    if not tickers:
        print("[펀더멘털] 종목 없음")
        return 0

    # 가장 최근 영업일 기준 (오늘 데이터 없으면 어제)
    today_str = date.today().strftime("%Y%m%d")
    yesterday_str = (date.today() - timedelta(days=1)).strftime("%Y%m%d")
    today_iso = date.today().strftime("%Y-%m-%d")

    rows = []
    for ticker in tickers:
        try:
            fd = krx.get_market_fundamental_by_date(yesterday_str, today_str, ticker)
            mc = krx.get_market_cap_by_date(yesterday_str, today_str, ticker)
            if fd.empty:
                print(f"[펀더멘털 {ticker}] 데이터 없음")
                continue
            frow = fd.iloc[-1]
            per = float(frow.get("PER", 0)) or None
            pbr = float(frow.get("PBR", 0)) or None
            market_cap = int(mc.iloc[-1]["시가총액"]) if not mc.empty else None
            rows.append({
                "ticker": ticker,
                "date": today_iso,
                "per": per,
                "pbr": pbr,
                "market_cap": market_cap,
            })
            cap_str = f"{market_cap // 10**12:,}조" if market_cap else "—"
            print(f"[펀더멘털 {ticker}] PER={per} PBR={pbr} 시가총액={cap_str}")
        except Exception as e:
            print(f"[펀더멘털 {ticker}] 실패: {e}")

    if rows:
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO fundamental (ticker, date, per, pbr, market_cap)
                    VALUES (:ticker, :date, :per, :pbr, :market_cap)
                    ON DUPLICATE KEY UPDATE date=VALUES(date), per=VALUES(per),
                        pbr=VALUES(pbr), market_cap=VALUES(market_cap)
                """),
                rows,
            )
    print(f"[펀더멘털] 총 {len(rows)}건 적재")
    return len(rows)


def load_all(engine) -> dict[str, int]:
    """KOSPI, 주식, 환율 증분 적재 실행."""
    print("=== 일일 시장 데이터 적재 시작 ===\n")
    results = {
        "kospi": load_kospi(engine),
        "stocks": load_stocks(engine),
        "exchange_rates": load_exchange_rates(engine),
        "fundamentals": load_fundamentals(engine),
    }
    total = sum(results.values())
    print(
        f"\n=== 완료: 총 {total}건 "
        f"(KOSPI {results['kospi']} / 주식 {results['stocks']} / "
        f"환율 {results['exchange_rates']} / 펀더멘털 {results['fundamentals']}) ==="
    )
    return results


if __name__ == "__main__":
    load_all(get_engine())

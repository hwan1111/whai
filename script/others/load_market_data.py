"""
Daily market data loader — KOSPI (1), stocks (10), exchange rates (6), fundamentals (10).

Run manually:
    python script/load_market_data.py

Or via Airflow DAG: finance_market_data_daily
"""

import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=True)

from sqlalchemy import create_engine, text


def get_engine():
    url = os.getenv("SERVICE_DATABASE_URL")
    if not url:
        raise RuntimeError("SERVICE_DATABASE_URL이 .env에 없습니다.")
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
        row = conn.execute(
            text("SELECT MAX(date) FROM price WHERE ticker = 'USD'")
        ).fetchone()
    return row[0] if row[0] else date(2020, 1, 1)


def _latest_fundamental_date(engine) -> date:
    with engine.connect() as conn:
        row = conn.execute(text("SELECT MAX(date) FROM fundamental")).fetchone()
    return row[0] if row[0] else date(2020, 1, 1)


def load_kospi(engine, since: date | None = None, as_of: date | None = None) -> int:
    """pykrx로 KOSPI 지수(000000) 증분 적재."""
    try:
        from pykrx import stock as krx
    except ImportError:
        print("[KOSPI] pykrx 미설치")
        return 0

    last = _latest_price_date(engine, "000000")
    start = since if since else last + timedelta(days=1)
    end = as_of if as_of else datetime.now(timezone.utc).date() - timedelta(days=1)

    if start > end:
        print("[KOSPI] 최신 상태")
        return 0

    df = krx.get_index_ohlcv_by_date(
        start.strftime("%Y%m%d"),
        end.strftime("%Y%m%d"),
        "1001",  # KOSPI 지수 코드
    )
    if df.empty:
        print(f"[KOSPI] 데이터 없음 ({start} ~ {end})")
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

    print(f"[KOSPI] {len(rows)}건 적재 ({start} ~ {end})")
    return len(rows)


def load_stocks(engine, since: date | None = None, as_of: date | None = None) -> int:
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
                text("SELECT ticker, name FROM asset WHERE ticker REGEXP '^[0-9]{6}$'")
            )
        }

    if not tickers:
        print("[주식] asset 테이블에 종목이 없습니다.")
        return 0

    end_str = (as_of if as_of else datetime.now(timezone.utc).date() - timedelta(days=1)).strftime("%Y%m%d")
    total = 0

    for ticker, name in tickers.items():
        last = _latest_price_date(engine, ticker)
        start_str = (since if since else last + timedelta(days=1)).strftime("%Y%m%d")

        if start_str > end_str:
            print(f"[{ticker} {name}] 최신 상태")
            continue

        try:
            df = krx.get_market_ohlcv_by_date(start_str, end_str, ticker)
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


def load_exchange_rates(engine, since: date | None = None,
                        as_of: date | None = None) -> int:
    """BOK ECOS API로 USD/KRW 환율 증분 적재 (price 테이블, ticker='USD')."""
    sys.path.insert(0, str(ROOT / "src"))
    from exchange_rate_fetcher import fetch_bok, make_exchange_rate_df

    last = _latest_exchange_date(engine)
    start = since if since else last + timedelta(days=1)
    end = as_of if as_of else datetime.now(timezone.utc).date() - timedelta(days=1)

    if start > end:
        print("[환율] 최신 상태")
        return 0

    start_str = start.strftime("%Y%m%d")
    end_str = end.strftime("%Y%m%d")

    try:
        raw_rows = fetch_bok(start_str, end_str)
    except Exception as e:
        print(f"[환율 ERROR] BOK API 호출 실패: {e}")
        return 0

    if not raw_rows:
        print(f"[환율] 데이터 없음 ({start} ~ {end})")
        return 0

    df = make_exchange_rate_df(raw_rows)
    if df.empty:
        print(f"[환율] 파싱된 데이터 없음 ({start} ~ {end})")
        return 0

    rows = [
        {"ticker": "USD", "date": r["date"], "close": round(r["rate"], 4), "volume": 0}
        for r in df.to_dict(orient="records")
    ]

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO price (ticker, date, close, volume)
                VALUES (:ticker, :date, :close, :volume)
                ON DUPLICATE KEY UPDATE close=VALUES(close)
            """),
            rows,
        )

    print(f"[환율] {len(rows)}건 적재 ({start} ~ {end})")
    return len(rows)


def load_fundamentals(engine, as_of: date | None = None,
                      force: bool = False) -> int:
    """pykrx로 개별 종목(10개) + KOSPI 지수 PER·PBR·시가총액 최신 스냅샷 적재."""
    try:
        from pykrx import stock as krx
    except ImportError:
        print("[펀더멘털] pykrx 미설치")
        return 0

    with engine.connect() as conn:
        stock_tickers = [
            r.ticker for r in conn.execute(
                text("SELECT ticker FROM asset WHERE ticker REGEXP '^[0-9]{6}$' AND ticker != '000000'")
            )
        ]

    if not stock_tickers:
        print("[펀더멘털] 종목 없음")
        return 0

    end = as_of if as_of else datetime.now(timezone.utc).date() - timedelta(days=1)
    last = _latest_fundamental_date(engine)
    if last >= end and not force:
        print("[펀더멘털] 최신 상태")
        return 0

    end_str = end.strftime("%Y%m%d")
    start_str = (end - timedelta(days=1)).strftime("%Y%m%d")
    end_iso = end.strftime("%Y-%m-%d")

    rows = []

    # KOSPI 지수 PER/PBR (pykrx 인덱스 펀더멘털)
    try:
        df = krx.get_index_fundamental_by_date(start_str, end_str, "1001")
        if not df.empty:
            valid = df[df["PER"] > 0]
            frow = valid.iloc[-1] if not valid.empty else df.iloc[-1]
            per_val = float(frow.get("PER", 0) or 0)
            pbr_val = float(frow.get("PBR", 0) or 0)
            rows.append({
                "ticker": "000000",
                "date": end_iso,
                "per": per_val if per_val > 0 else None,
                "pbr": pbr_val if pbr_val > 0 else None,
                "market_cap": None,
            })
            print(f"[펀더멘털 000000 KOSPI] PER={per_val} PBR={pbr_val}")
        else:
            print("[펀더멘털 000000 KOSPI] 데이터 없음")
    except Exception as e:
        print(f"[펀더멘털 000000 KOSPI] 실패: {e}")

    # 개별 종목
    for ticker in stock_tickers:
        try:
            fd = krx.get_market_fundamental_by_date(start_str, end_str, ticker)
            mc = krx.get_market_cap_by_date(start_str, end_str, ticker)
            if fd.empty:
                print(f"[펀더멘털 {ticker}] 데이터 없음")
                continue
            frow = fd.iloc[-1]
            per_raw = frow.get("PER", 0)
            per_val = float(per_raw) if per_raw not in (None, "") else 0
            per = per_val if per_val > 0 else None
            pbr = float(frow.get("PBR", 0)) if frow.get("PBR", 0) not in (None, "") else None
            market_cap = int(mc.iloc[-1]["시가총액"]) if not mc.empty else None
            rows.append({
                "ticker": ticker,
                "date": end_iso,
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


def load_all(engine, since: date | None = None,
             as_of: date | None = None) -> dict[str, int]:
    """KOSPI, 주식, 환율 증분 적재 실행."""
    print("=== 일일 시장 데이터 적재 시작 ===\n")
    if since:
        print(f"  [강제 시작] --since {since} (기존 데이터 덮어쓰기 포함)\n")
    end = as_of or date.today() - timedelta(days=1)
    print(f"  [기준일] {end}\n")
    results = {
        "kospi": load_kospi(engine, since=since, as_of=end),
        "stocks": load_stocks(engine, since=since, as_of=end),
        "exchange_rates": load_exchange_rates(engine, since=since, as_of=end),
        "fundamentals": load_fundamentals(engine, as_of=end, force=since is not None),
    }
    total = sum(results.values())
    print(
        f"\n=== 완료: 총 {total}건 "
        f"(KOSPI {results['kospi']} / 주식 {results['stocks']} / "
        f"환율 {results['exchange_rates']} / 펀더멘털 {results['fundamentals']}) ==="
    )
    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="일일 시장 데이터 적재")
    parser.add_argument(
        "--since", default=None,
        help="강제 시작일 YYYY-MM-DD (지정 시 해당 날짜부터 재수집, 기본: DB 최신+1일)",
    )
    parser.add_argument(
        "--as-of", default=None,
        help="수집 종료 기준일 YYYY-MM-DD (기본: 완료된 전일)",
    )
    args = parser.parse_args()
    since_date = date.fromisoformat(args.since) if args.since else None
    as_of_date = date.fromisoformat(args.as_of) if args.as_of else None
    load_all(get_engine(), since=since_date, as_of=as_of_date)

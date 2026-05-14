"""KRX 종목 주가 데이터를 pykrx로 가져와 price 테이블에 적재.
KOSPI 지수(000000)는 pykrx index API 대신 yfinance(^KS11)를 사용한다.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from backend.db import engine

START     = "20230101"
START_ISO = "2023-01-01"
END       = date.today().strftime("%Y%m%d")

KOSPI_TICKER  = "000000"
KOSPI_YF_CODE = "^KS11"


def load_tickers() -> dict[str, str]:
    """company 테이블에서 KRW 종목 ticker, name 조회."""
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT ticker, name FROM company WHERE currency_code = 'KRW' ORDER BY ticker"
        )).fetchall()
    return {r.ticker: r.name for r in rows}


def _fetch_kospi() -> list[dict]:
    """yfinance로 KOSPI 지수 데이터 수집."""
    try:
        import yfinance as yf
    except ImportError:
        print("yfinance 미설치: pip install yfinance")
        return []

    df = yf.download(KOSPI_YF_CODE, start=START_ISO,
                     end=(date.today() + timedelta(days=1)).strftime("%Y-%m-%d"), progress=False)
    if df.empty:
        return []

    close  = df["Close"].squeeze()
    volume = df["Volume"].squeeze()
    return [
        {
            "ticker": KOSPI_TICKER,
            "date":   idx.strftime("%Y-%m-%d"),
            "close":  round(float(close[idx])),
            "volume": int(volume[idx]),
        }
        for idx in df.index
    ]


def load_price(tickers: dict[str, str]) -> None:
    try:
        from pykrx import stock as krx
    except ImportError:
        print("pykrx 미설치: pip install pykrx")
        sys.exit(1)

    total = 0
    for ticker, name in tickers.items():
        print(f"  {ticker} ({name}) 조회 중...", end=" ", flush=True)
        try:
            if ticker == KOSPI_TICKER:
                rows = _fetch_kospi()
            else:
                df = krx.get_market_ohlcv_by_date(START, END, ticker)
                if df.empty:
                    print("데이터 없음")
                    continue
                rows = [
                    {
                        "ticker": ticker,
                        "date":   idx.strftime("%Y-%m-%d"),
                        "close":  int(row["종가"]),
                        "volume": int(row["거래량"]),
                    }
                    for idx, row in df.iterrows()
                ]

            if not rows:
                print("데이터 없음")
                continue

            with engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO price (ticker, date, close, volume)
                    VALUES (:ticker, :date, :close, :volume)
                    ON DUPLICATE KEY UPDATE close=VALUES(close), volume=VALUES(volume)
                """), rows)

            total += len(rows)
            print(f"{len(rows)}건")
        except Exception as e:
            print(f"실패: {e}")

    print(f"\nprice: 총 {total}건 적재 완료")


if __name__ == "__main__":
    tickers = load_tickers()
    if not tickers:
        print("company 테이블에 종목이 없습니다. 먼저 company 데이터를 적재해주세요.")
        sys.exit(1)

    print(f"=== KRX 데이터 적재 ({START} ~ {END}) ===")
    print(f"대상 종목: {len(tickers)}개 - {', '.join(tickers.values())}\n")
    load_price(tickers)

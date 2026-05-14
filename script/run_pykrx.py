"""KRX 종목 주가 데이터를 pykrx로 가져와 price 테이블에 적재."""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from backend.db import engine

START = "20230101"
END   = date.today().strftime("%Y%m%d")


def load_tickers() -> dict[str, str]:
    """company 테이블에서 KRW 종목 ticker, name 조회."""
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT ticker, name FROM company WHERE currency_code = 'KRW' ORDER BY ticker"
        )).fetchall()
    return {r.ticker: r.name for r in rows}


KOSPI_TICKER    = "000000"
KOSPI_KRX_CODE  = "1001"   # pykrx 지수 코드


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
                df = krx.get_index_ohlcv_by_date(START, END, KOSPI_KRX_CODE)
            else:
                df = krx.get_market_ohlcv_by_date(START, END, ticker)

            if df.empty:
                print("데이터 없음")
                continue

            close_col  = "종가"
            volume_col = "거래량" if "거래량" in df.columns else None

            rows = [
                {
                    "ticker": ticker,
                    "date":   idx.strftime("%Y-%m-%d"),
                    "close":  int(row[close_col]),
                    "volume": int(row[volume_col]) if volume_col else 0,
                }
                for idx, row in df.iterrows()
            ]

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
    print(f"대상 종목: {len(tickers)}개 — {', '.join(tickers.values())}\n")
    load_price(tickers)

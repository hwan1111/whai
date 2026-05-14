"""KRX 종목 주가 데이터를 pykrx로 가져와 price / company 테이블에 적재."""

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from backend.db import engine

TICKERS = {
    "005930": ("삼성전자",   "반도체"),
    "000660": ("SK하이닉스", "반도체"),
    "005380": ("현대차",     "자동차"),
    "000270": ("기아",       "자동차"),
    "079550": ("LIG넥스원",  "방산"),
    "012450": ("한화에어로스페이스", "방산"),
    "105560": ("KB금융",     "금융"),
    "055550": ("신한지주",   "금융"),
    "051910": ("LG화학",     "화학"),
    "096770": ("SK이노베이션", "화학"),
}

START = "20230101"
END   = date.today().strftime("%Y%m%d")


def load_company():
    rows = [
        {"ticker": t, "name": name, "sector": sector, "currency_code": "KRW"}
        for t, (name, sector) in TICKERS.items()
    ]
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO company (ticker, name, sector, currency_code)
            VALUES (:ticker, :name, :sector, :currency_code)
            ON DUPLICATE KEY UPDATE name=VALUES(name), sector=VALUES(sector)
        """), rows)
    print(f"company: {len(rows)}개 종목 적재 완료")


def load_price():
    try:
        from pykrx import stock as krx
    except ImportError:
        print("pykrx 미설치: pip install pykrx")
        sys.exit(1)

    total = 0
    for ticker in TICKERS:
        print(f"  {ticker} ({TICKERS[ticker][0]}) 조회 중...", end=" ", flush=True)
        try:
            df = krx.get_market_ohlcv_by_date(START, END, ticker)
            if df.empty:
                print("데이터 없음")
                continue

            rows = [
                {
                    "ticker": ticker,
                    "date":   idx.strftime("%Y-%m-%d"),
                    "close":  float(row["종가"]),
                    "volume": int(row["거래량"]),
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
    print(f"=== KRX 데이터 적재 ({START} ~ {END}) ===\n")
    load_company()
    print()
    load_price()

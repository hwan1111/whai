"""특정 종목의 가격 데이터를 수정주가 기준으로 다시 불러옵니다.

Usage:
    python reload_price_data.py --ticker 000660
    python reload_price_data.py --ticker 005930 --start 20200101
    python reload_price_data.py --ticker 012450 --start 20200101 --end 20261231
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from dotenv import dotenv_values
from pykrx import stock
from sqlalchemy import create_engine, text


def get_db_engine():
    """데이터베이스 연결을 위한 SQLAlchemy 엔진을 생성합니다."""
    env_path = Path(__file__).resolve().parents[1] / ".env.local"
    if not env_path.exists():
        raise FileNotFoundError(f".env.local file not found at {env_path}")

    env = dotenv_values(env_path)
    url = env.get("SERVICE_DATABASE_URL") or env.get("DATABASE_URL")
    if not url:
        raise ValueError("SERVICE_DATABASE_URL or DATABASE_URL not found in .env.local.")

    # ${CA_PATH} 플레이스홀더를 실제 경로로 교체
    ca_path_str = str(Path(__file__).resolve().parents[1] / "config" / "certs" / "ca.pem")
    if "${CA_PATH}" in url:
        url = url.replace("${CA_PATH}", ca_path_str)

    return create_engine(url)


def reload_price_for_ticker(engine, ticker: str, start_date: str, end_date: str):
    """특정 종목의 데이터를 삭제하고 수정주가 기준으로 다시 적재합니다."""
    print(f"--- Ticker: {ticker} 데이터 재적재 시작 ---")

    # 1. 기존 데이터 삭제
    with engine.connect() as conn:
        print(f"Deleting existing data for ticker {ticker}...")
        conn.execute(text(f"DELETE FROM price WHERE ticker = '{ticker}'"))
        conn.commit()
        print("Deletion complete.")

    # 2. pykrx로 수정주가 데이터 조회 (adjusted=True가 기본값이므로 별도 설정 불필요)
    print(f"Fetching adjusted price data for {ticker} from {start_date} to {end_date}...")
    df = stock.get_market_ohlcv(start_date, end_date, ticker)

    if df.empty:
        print(f"No data found for {ticker}. Aborting.")
        return

    # 3. 데이터베이스 스키마에 맞게 컬럼명 변경 및 추가
    df.reset_index(inplace=True)
    df.rename(columns={'날짜': 'date', '시가': 'open', '고가': 'high', '저가': 'low', '종가': 'close', '거래량': 'volume'}, inplace=True)
    df['ticker'] = ticker
    df = df[['date', 'ticker', 'open', 'high', 'low', 'close', 'volume']]

    # 4. 데이터베이스에 적재
    print(f"Loading {len(df)} rows into 'price' table...")
    df.to_sql('price', con=engine, if_exists='append', index=False)

    print(f"✅ Ticker: {ticker} 데이터 재적재 완료.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="특정 종목의 가격 데이터를 수정주가 기준으로 재적재합니다.")
    parser.add_argument("--ticker", required=True, help="종목 코드 (예: 000660)")
    parser.add_argument("--start", default="20100101", help="시작일 YYYYMMDD (기본값: 20100101)")
    parser.add_argument("--end", default=datetime.now().strftime("%Y%m%d"), help="종료일 YYYYMMDD (기본값: 오늘)")
    args = parser.parse_args()

    try:
        db_engine = get_db_engine()
        reload_price_for_ticker(db_engine, args.ticker, args.start, args.end)
    except Exception as e:
        print(f"\n❌ 작업 중 오류가 발생했습니다: {e}")
        sys.exit(1)

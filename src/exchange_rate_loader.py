import os
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from exchange_rate_fetcher import BASE_CURRENCY, fetch_frankfurter, make_exchange_rate_df

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env.local", override=True)


def get_engine():
    url = os.getenv("SERVICE_DATABASE_URL")
    if not url:
        raise RuntimeError("SERVICE_DATABASE_URL이 .env.local에 없습니다.")

    ca_path = ROOT / "config" / "certs" / "ca.pem"
    base_url = url.split("?")[0]
    db_url = f"{base_url}?charset=utf8mb4"
    connect_args = {"ssl": {"ca": str(ca_path)}} if ca_path.exists() else {}

    return create_engine(db_url, connect_args=connect_args, pool_pre_ping=True)


def insert_exchange_rate(engine, exchange_df: pd.DataFrame):
    if exchange_df.empty:
        return

    insert_sql = """
    INSERT INTO exchange_rate (
        currency_pair,
        date,
        base_currency_code,
        target_currency_code,
        rate
    )
    VALUES (
        :currency_pair,
        :date,
        :base_currency_code,
        :target_currency_code,
        :rate
    )
    ON DUPLICATE KEY UPDATE
        rate = VALUES(rate)
    """

    with engine.begin() as conn:
        conn.execute(text(insert_sql), exchange_df.to_dict(orient="records"))


def load_exchange_rate_from_api(engine, start_date, end_date):
    current_date = start_date
    total = 0

    while current_date <= end_date:
        requested_date = current_date.strftime("%Y-%m-%d")

        try:
            data = fetch_frankfurter(requested_date, base=BASE_CURRENCY)
            actual_date = data.get("date")

            # 주말 / 휴일 fallback 데이터 스킵
            if actual_date != requested_date:
                print(f"[SKIP] 요청일: {requested_date} / 실제 데이터 기준일: {actual_date}")

            elif "rates" not in data or not data["rates"]:
                print(f"[NO DATA] {requested_date}")

            else:
                exchange_df = make_exchange_rate_df(data)
                insert_exchange_rate(engine, exchange_df)
                total += len(exchange_df)
                print(f"[DB 저장] {requested_date} / {len(exchange_df)}건")

        except Exception as e:
            print(f"[ERROR] {requested_date} / {e}")

        current_date += timedelta(days=1)

    print(f"\nAPI 적재 완료 / 총 {total}건")


def load_exchange_rate_from_csv(engine, csv_path: str):
    df = pd.read_csv(csv_path)
    insert_exchange_rate(engine, df)
    print(f"CSV 적재 완료 / 총 {len(df)}건")
    return pd.to_datetime(df["date"]).max().date()


if __name__ == "__main__":
    engine = get_engine()
    csv_path = ROOT / "data" / "exchange_rate_2020_today.csv"

    last_date = load_exchange_rate_from_csv(engine, csv_path)
    print(f"CSV 마지막 날짜: {last_date}")

    api_start = last_date + timedelta(days=1)
    api_end = datetime.today().date()

    if api_start <= api_end:
        print(f"API 호출 시작: {api_start} ~ {api_end}")
        load_exchange_rate_from_api(engine, api_start, api_end)
    else:
        print("API 호출 불필요 (CSV가 최신 상태)")

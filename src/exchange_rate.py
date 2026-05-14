import os
import requests
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

EXIM_API_KEY = os.getenv("EXIM_API_KEY")

DB_HOST = os.getenv("MYSQL_HOST", "localhost")
DB_PORT = os.getenv("MYSQL_PORT", "3306")
DB_NAME = os.getenv("MYSQL_DATABASE")
DB_USER = os.getenv("MYSQL_USER")
DB_PASSWORD = os.getenv("MYSQL_PASSWORD")

TARGET_CURRENCIES = [
    "KRW", "EUR", "JPY", "CNY", "CHF", "GBP", "AUD", "CAD"
]

BASE_CURRENCY = "USD"


def get_engine():
    db_url = (
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
    )
    return create_engine(db_url)


def clean_rate(rate_text):
    return float(str(rate_text).replace(",", ""))


def normalize_currency_code(cur_unit):
    cur_unit = str(cur_unit)

    if "(100)" in cur_unit:
        return cur_unit.replace("(100)", "")

    return cur_unit


def insert_exchange_rate(engine, exchange_df: pd.DataFrame):
    if exchange_df.empty:
        return

    insert_sql = """
    INSERT INTO EXCHANGE_RATE (
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
        base_currency_code = VALUES(base_currency_code),
        target_currency_code = VALUES(target_currency_code),
        rate = VALUES(rate);
    """

    records = exchange_df.to_dict(orient="records")

    with engine.begin() as conn:
        conn.execute(text(insert_sql), records)


# =========================
# 1. 한국수출입은행 API: 외화/KRW
# =========================

def fetch_exim_api(searchdate: str):
    url = "https://oapi.koreaexim.go.kr/site/program/financial/exchangeJSON"

    params = {
        "authkey": EXIM_API_KEY,
        "searchdate": searchdate,
        "data": "AP01"
    }

    response = requests.get(url, params=params)
    response.raise_for_status()

    return pd.DataFrame(response.json())


def make_exim_exchange_rate_df(api_df: pd.DataFrame, searchdate: str):
    exchange_df = api_df[["cur_unit", "deal_bas_r"]].copy()

    # JPY(100) → JPY로 정리
    # rate는 deal_bas_r 그대로 저장
    exchange_df["base_currency_code"] = exchange_df["cur_unit"].apply(
        normalize_currency_code
    )

    exchange_df["target_currency_code"] = "KRW"
    exchange_df["currency_pair"] = exchange_df["base_currency_code"] + "/KRW"
    exchange_df["date"] = datetime.strptime(searchdate, "%Y%m%d").date()
    exchange_df["rate"] = exchange_df["deal_bas_r"].apply(clean_rate)

    exchange_df = exchange_df[
        [
            "currency_pair",
            "date",
            "base_currency_code",
            "target_currency_code",
            "rate"
        ]
    ]

    return exchange_df


def load_exim_exchange_rate_from_2020(engine):
    start_date = datetime(2020, 1, 1).date()
    end_date = datetime.today().date()

    current_date = start_date

    while current_date <= end_date:
        searchdate = current_date.strftime("%Y%m%d")

        try:
            api_df = fetch_exim_api(searchdate)

            if api_df.empty:
                print(f"[EXIM] 환율 데이터 없음: {searchdate}")
            else:
                exchange_df = make_exim_exchange_rate_df(api_df, searchdate)

                allowed_currencies = [
                    "USD", "KRW", "EUR", "JPY", "CNY", "CHF", "GBP", "AUD", "CAD"
                ]

                exchange_df = exchange_df[
                    exchange_df["base_currency_code"].isin(allowed_currencies)
                ]

                insert_exchange_rate(engine, exchange_df)
                print(f"[EXIM] KRW 기준 저장 완료: {searchdate}, {len(exchange_df)}건")

        except Exception as e:
            print(f"[EXIM] 오류 발생: {searchdate} / {e}")

        current_date += timedelta(days=1)


# =========================
# 2. Frankfurter API: USD/외화
# =========================

def fetch_frankfurter(date: str, base: str = BASE_CURRENCY):
    url = f"https://api.frankfurter.app/{date}"

    params = {
        "from": base,
        "to": ",".join(TARGET_CURRENCIES)
    }

    response = requests.get(url, params=params)
    response.raise_for_status()

    return response.json()


def make_frankfurter_exchange_rate_df(data: dict, base: str, date: str):
    rates = data.get("rates", {})

    rows = []

    for target, rate in rates.items():
        if target not in TARGET_CURRENCIES:
            continue

        rows.append({
            "currency_pair": f"{target}/{base}",
            "date": datetime.strptime(date, "%Y-%m-%d").date(),
            "base_currency_code": base,
            "target_currency_code": target,
            "rate": float(rate)
        })

    return pd.DataFrame(rows)


def load_usd_exchange_rate_from_2020(engine):
    start_date = datetime(2020, 1, 1).date()
    end_date = datetime.today().date()

    current_date = start_date

    while current_date <= end_date:
        date_str = current_date.strftime("%Y-%m-%d")

        try:
            data = fetch_frankfurter(date_str, base=BASE_CURRENCY)

            if "rates" not in data or not data["rates"]:
                print(f"[Frankfurter] 데이터 없음: {date_str}")
            else:
                exchange_df = make_frankfurter_exchange_rate_df(
                    data,
                    base=BASE_CURRENCY,
                    date=date_str
                )

                insert_exchange_rate(engine, exchange_df)
                print(f"[Frankfurter] USD 기준 저장 완료: {date_str}, {len(exchange_df)}건")

        except Exception as e:
            print(f"[Frankfurter] 오류 발생: {date_str} / {e}")

        current_date += timedelta(days=1)


if __name__ == "__main__":
    engine = get_engine()

    load_exim_exchange_rate_from_2020(engine)
    load_usd_exchange_rate_from_2020(engine)

    print("2020-01-01부터 오늘까지 EXCHANGE_RATE 통합 적재 완료")
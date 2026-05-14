import requests
import pandas as pd

BASE_CURRENCY = "USD"

TARGET_CURRENCIES = [
    "KRW",
    "EUR",
    "JPY",
    "CNY",
    "CHF",
    "GBP"
]


def fetch_frankfurter(date: str, base: str = BASE_CURRENCY) -> dict:
    url = f"https://api.frankfurter.app/{date}"

    params = {
        "from": base,
        "to": ",".join(TARGET_CURRENCIES)
    }

    response = requests.get(url, params=params)
    response.raise_for_status()

    return response.json()


def make_exchange_rate_df(data: dict) -> pd.DataFrame:
    rates = data.get("rates", {})
    actual_date = data.get("date")
    base = data.get("base")

    rows = []

    for target, rate in rates.items():
        rows.append({
            "currency_pair": f"{base}/{target}",
            "date": actual_date,
            "base_currency_code": base,
            "target_currency_code": target,
            "rate": float(rate)
        })

    return pd.DataFrame(rows)

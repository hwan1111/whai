"""Run KOSPI and USD/KRW predictions once without Airflow."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from dotenv import load_dotenv
from pandas.tseries.offsets import BDay
from prophet import Prophet
from sqlalchemy import create_engine, text
from statsmodels.tsa.vector_ar.vecm import VECM, select_coint_rank


PROJECT_ROOT = Path(__file__).resolve().parents[1]
HORIZON = 5
FORECAST_STEPS = 25
CI_Z = 1.28
CI_PCT = 0.80
VOL_DAYS = 20

ASSETS = {
    "000000": {"name": "KOSPI", "symbol": "^KS11", "model": "Prophet"},
    "USD": {"name": "USD/KRW", "symbol": "KRW=X", "model": "VECM"},
}


def column(frame: pd.DataFrame, name: str) -> pd.Series:
    if isinstance(frame.columns, pd.MultiIndex):
        frame = frame.copy()
        frame.columns = frame.columns.get_level_values(0)
    series = frame[name]
    if isinstance(series, pd.DataFrame):
        series = series.iloc[:, 0]
    series.index = pd.to_datetime(series.index).tz_localize(None)
    return series


def download_close(symbol: str, start: str = "2020-01-01") -> pd.Series:
    frame = yf.download(
        symbol,
        start=start,
        auto_adjust=True,
        progress=False,
        timeout=60,
    )
    if frame.empty:
        raise RuntimeError(f"{symbol} 가격 데이터를 받지 못했습니다.")
    return column(frame, "Close").dropna()


def predict_kospi(close: pd.Series) -> tuple[np.ndarray, float]:
    train = close[close.index >= pd.Timestamp.today().normalize() - pd.DateOffset(months=48)]
    data = np.log(train).reset_index()
    data.columns = ["ds", "y"]
    model = Prophet(
        daily_seasonality=False,
        yearly_seasonality=True,
        weekly_seasonality=True,
        uncertainty_samples=False,
    )
    model.fit(data)
    future = model.make_future_dataframe(periods=FORECAST_STEPS, freq="B")
    prediction = np.exp(model.predict(future).tail(FORECAST_STEPS)["yhat"].to_numpy())
    volatility = float(np.log(train / train.shift(1)).dropna().tail(VOL_DAYS).std())
    return prediction, volatility


def predict_usd(close: pd.Series) -> tuple[np.ndarray, float]:
    exog = {
        "KOSPI200": download_close("^KS200"),
        "WTI": download_close("CL=F"),
        "VIX": download_close("^VIX"),
    }
    panel = pd.DataFrame({"close": close})
    for name, series in exog.items():
        panel[name] = series
    panel = panel.ffill().bfill().dropna()
    panel = panel[
        panel.index >= pd.Timestamp.today().normalize() - pd.DateOffset(months=48)
    ]
    try:
        rank = max(select_coint_rank(panel, det_order=0, k_ar_diff=1).rank, 1)
    except Exception:
        rank = 1
    model = VECM(
        panel,
        deterministic="co",
        k_ar_diff=1,
        coint_rank=min(rank, panel.shape[1] - 1),
    ).fit()
    prediction = model.predict(steps=FORECAST_STEPS)[:, 0]
    volatility = float(np.log(close / close.shift(1)).dropna().tail(VOL_DAYS).std())
    return prediction, volatility


def confidence_interval(base: float, price: float, volatility: float, horizon: int) -> tuple[float, float]:
    log_return = float(np.log(price / base))
    half = CI_Z * volatility * np.sqrt(horizon)
    return (
        round(base * np.exp(log_return + half), 2),
        round(base * np.exp(log_return - half), 2),
    )


def build_forecast(
    base_date: pd.Timestamp,
    base_price: float,
    prices: np.ndarray,
    volatility: float,
) -> list[dict]:
    result = []
    for horizon, price in enumerate(prices[:HORIZON], start=1):
        upper, lower = confidence_interval(base_price, float(price), volatility, horizon)
        result.append(
            {
                "horizon": horizon,
                "date": str((base_date + BDay(horizon)).date()),
                "price": round(float(price), 2),
                "ci_upper": upper,
                "ci_lower": lower,
            }
        )
    return result


def get_engine():
    load_dotenv(PROJECT_ROOT / ".env", override=True)
    raw = os.environ["SERVICE_DATABASE_URL"]
    ca = str(PROJECT_ROOT / "config" / "certs" / "ca.pem")
    if "ssl_ca=" in raw:
        url = raw.split("?")[0] + "?charset=utf8mb4"
        args = {"ssl": {"ca": ca}}
    else:
        url, args = raw, {}
    return create_engine(url, connect_args=args, pool_pre_ping=True)


def save_prediction(ticker: str, config: dict, close: pd.Series, prices: np.ndarray, volatility: float) -> dict:
    base_date = pd.Timestamp(close.index[-1]).normalize()
    base_price = float(close.iloc[-1])
    d5_price = float(prices[HORIZON - 1])
    target_date = (base_date + BDay(HORIZON)).date()
    forecast = build_forecast(base_date, base_price, prices, volatility)
    ci_upper, ci_lower = confidence_interval(base_price, d5_price, volatility, HORIZON)
    record = {
        "ticker": ticker,
        "date": str(base_date.date()),
        "target_date": str(target_date),
        "model_used": "priority_1",
        "model_name": config["model"],
        "model_source": "Choi",
        "base_price": round(base_price, 4),
        "pred_price_d5": round(d5_price, 4),
        "pred_return_d5": round(float(np.log(d5_price / base_price)), 6),
        "ci_pct": CI_PCT,
        "ci_upper_d5": ci_upper,
        "ci_lower_d5": ci_lower,
        "vol_20d": round(volatility, 6),
        "drift_detected": 0,
        "rolling_mape": None,
        "threshold": 0.0,
        "retrain_needed": 0,
        "forecast_json": json.dumps(forecast, ensure_ascii=False),
    }
    with get_engine().begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO prediction
                    (ticker, date, target_date, model_used, model_name,
                     model_source, base_price, pred_price_d5, pred_return_d5,
                     ci_pct, ci_upper_d5, ci_lower_d5, vol_20d,
                     drift_detected, rolling_mape, threshold,
                     retrain_needed, forecast_json)
                VALUES
                    (:ticker, :date, :target_date, :model_used, :model_name,
                     :model_source, :base_price, :pred_price_d5, :pred_return_d5,
                     :ci_pct, :ci_upper_d5, :ci_lower_d5, :vol_20d,
                     :drift_detected, :rolling_mape, :threshold,
                     :retrain_needed, :forecast_json)
                ON DUPLICATE KEY UPDATE
                    target_date = VALUES(target_date),
                    model_used = VALUES(model_used),
                    model_name = VALUES(model_name),
                    model_source = VALUES(model_source),
                    base_price = VALUES(base_price),
                    pred_price_d5 = VALUES(pred_price_d5),
                    pred_return_d5 = VALUES(pred_return_d5),
                    ci_pct = VALUES(ci_pct),
                    ci_upper_d5 = VALUES(ci_upper_d5),
                    ci_lower_d5 = VALUES(ci_lower_d5),
                    vol_20d = VALUES(vol_20d),
                    drift_detected = VALUES(drift_detected),
                    rolling_mape = VALUES(rolling_mape),
                    threshold = VALUES(threshold),
                    retrain_needed = VALUES(retrain_needed),
                    forecast_json = VALUES(forecast_json),
                    created_at = CURRENT_TIMESTAMP
                """
            ),
            record,
        )
    return record


def run(ticker: str) -> dict:
    config = ASSETS[ticker]
    close = download_close(config["symbol"])
    if ticker == "000000":
        prices, volatility = predict_kospi(close)
    else:
        prices, volatility = predict_usd(close)
    return save_prediction(ticker, config, close, prices, volatility)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ticker",
        choices=[*ASSETS, "all"],
        default="all",
        help="Asset to predict. Default: all",
    )
    args = parser.parse_args()
    tickers = list(ASSETS) if args.ticker == "all" else [args.ticker]
    for ticker in tickers:
        result = run(ticker)
        print(
            f"{ticker} {ASSETS[ticker]['name']}: "
            f"{result['base_price']:,.2f} -> {result['pred_price_d5']:,.2f} "
            f"({result['model_name']})"
        )


if __name__ == "__main__":
    main()

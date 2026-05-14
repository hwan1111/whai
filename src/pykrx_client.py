from datetime import datetime
from pykrx import stock
import pandas as pd


def get_price_data(ticker: str) -> pd.DataFrame:
    """
    PRICE 테이블 구조에 맞는 시세 데이터를 반환한다.

    PRICE 컬럼:
    - ticker
    - date
    - close
    - volume
    """

    start_date = "20200101"
    end_date = datetime.today().strftime("%Y%m%d")

    df = stock.get_market_ohlcv_by_date(start_date, end_date, ticker)

    result = df[["종가", "거래량"]].reset_index()

    result["ticker"] = ticker
    result = result.rename(
        columns={
            "날짜": "date",
            "종가": "close",
            "거래량": "volume",
        }
    )

    result = result[["ticker", "date", "close", "volume"]]

    result["date"] = pd.to_datetime(result["date"]).dt.date
    result["close"] = result["close"].astype(int)
    result["volume"] = result["volume"].astype("int64")

    return result
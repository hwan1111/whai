from datetime import datetime
from pykrx import stock
import pandas as pd


def get_price_data(
    ticker: str,
    start_date: str = "20200101",
    end_date: str | None = None,
) -> pd.DataFrame:
    """
    PRICE 테이블 구조에 맞는 시세 데이터를 반환한다.

    PRICE 컬럼:
    - ticker
    - date
    - close
    - volume

    start_date: YYYYMMDD 형식
    end_date: YYYYMMDD 형식; None이면 오늘 날짜를 사용
    """

    if end_date is None:
        end_date = datetime.today().strftime("%Y%m%d")

    df = stock.get_market_ohlcv_by_date(start_date, end_date, ticker)

    if df.empty:
        return pd.DataFrame(columns=["ticker", "date", "close", "volume"])

    if "종가" in df.columns and "거래량" in df.columns:
        source_columns = ["종가", "거래량"]
    elif "Close" in df.columns and "Volume" in df.columns:
        source_columns = ["Close", "Volume"]
    elif "close" in df.columns and "volume" in df.columns:
        source_columns = ["close", "volume"]
    else:
        raise KeyError(
            f"KRX 데이터 컬럼을 찾을 수 없습니다: {list(df.columns)}"
        )

    result = df[source_columns].reset_index()

    result["ticker"] = ticker
    result = result.rename(
        columns={
            "날짜": "date",
            "종가": "close",
            "거래량": "volume",
            "Close": "close",
            "Volume": "volume",
            "close": "close",
            "volume": "volume",
        }
    )

    result = result[["ticker", "date", "close", "volume"]]

    result["date"] = pd.to_datetime(result["date"]).dt.date
    result["close"] = result["close"].astype(float)
    result["volume"] = result["volume"].astype("int64")

    return result
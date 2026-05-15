import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine


def insert_exchange_rate(engine: Engine, df: pd.DataFrame) -> None:
    """exchange_rate 테이블에 upsert."""
    if df.empty:
        return

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO exchange_rate (
                    currency_pair, date, base_currency_code, target_currency_code, rate
                ) VALUES (
                    :currency_pair, :date, :base_currency_code, :target_currency_code, :rate
                )
                ON DUPLICATE KEY UPDATE rate = VALUES(rate)
            """),
            df.to_dict(orient="records"),
        )

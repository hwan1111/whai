"""
Daily market data sync: KOSPI (1), stocks (10), exchange rates (6).

Schedule: 15:00 UTC (00:00 KST) every weekday.
The 3 load tasks run in parallel, each doing incremental inserts.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.operators.python import PythonOperator

ROOT = Path(__file__).resolve().parents[2]

default_args = {
    "owner": "data-eng",
    "depends_on_past": False,
    "start_date": datetime(2026, 1, 1),
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=10),
}

dag = DAG(
    "finance_market_data_daily",
    default_args=default_args,
    description="KOSPI, 주식 10종, 환율 6쌍 일일 증분 적재",
    schedule_interval="0 15 * * 1-5",  # 00:00 KST 평일
    catchup=False,
    tags=["finance", "market-data", "price"],
)

dag.doc_md = __doc__


def _setup():
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "src"))
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env.local", override=True)
    from script.load_market_data import get_engine
    return get_engine()


def task_load_kospi(**_):
    engine = _setup()
    from script.load_market_data import load_kospi
    load_kospi(engine)


def task_load_stocks(**_):
    engine = _setup()
    from script.load_market_data import load_stocks
    load_stocks(engine)


def task_load_exchange_rates(**_):
    engine = _setup()
    from script.load_market_data import load_exchange_rates
    load_exchange_rates(engine)


t_kospi = PythonOperator(
    task_id="load_kospi",
    python_callable=task_load_kospi,
    dag=dag,
)
t_stocks = PythonOperator(
    task_id="load_stocks",
    python_callable=task_load_stocks,
    dag=dag,
)
t_rates = PythonOperator(
    task_id="load_exchange_rates",
    python_callable=task_load_exchange_rates,
    dag=dag,
)

# 3개 task 병렬 실행 (서로 독립적)
[t_kospi, t_stocks, t_rates]

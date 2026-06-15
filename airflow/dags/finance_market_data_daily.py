"""
Daily market data sync: KOSPI (1), stocks (10), exchange rates (1, KRW/USD), fundamentals (10).

Schedule: 15:00 UTC (00:00 KST) every day.
The 4 load tasks run in parallel, each doing incremental inserts.
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
    "start_date": datetime(2026, 6, 9),
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 3,
    "retry_delay": timedelta(minutes=10),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(hours=1),
}

dag = DAG(
    "finance_market_data_daily",
    default_args=default_args,
    description="KOSPI, 주식 10종, USD/KRW 환율(price ticker=USD), 펀더멘털(PER·PBR·시가총액) 일일 증분 적재",
    schedule="0 15 * * *",  # 00:00 KST 매일 (Airflow/컨테이너는 UTC)
    catchup=True,
    max_active_runs=1,
    tags=["finance", "market-data", "price"],
)

dag.doc_md = __doc__


def _setup():
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "src"))
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=True)
    from script.others.load_market_data import get_engine
    return get_engine()


def task_load_kospi(**_):
    engine = _setup()
    from script.others.load_market_data import load_kospi
    load_kospi(engine)


def task_load_stocks(**_):
    engine = _setup()
    from script.others.load_market_data import load_stocks
    load_stocks(engine)


def task_load_exchange_rates(**_):
    engine = _setup()
    from script.others.load_market_data import load_exchange_rates
    load_exchange_rates(engine)


def task_load_fundamentals(**_):
    engine = _setup()
    from script.others.load_market_data import load_fundamentals
    load_fundamentals(engine)


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
t_fundamentals = PythonOperator(
    task_id="load_fundamentals",
    python_callable=task_load_fundamentals,
    dag=dag,
)

# 4개 task 병렬 실행 (서로 독립적)
[t_kospi, t_stocks, t_rates, t_fundamentals]

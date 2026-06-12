"""
Daily market data sync: KOSPI, stocks, USD/KRW, and fundamentals.

Schedule: 15:00 UTC (00:00 KST) every day.
All market datasets are synchronized by one task with the same completed-date cutoff.
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
    description="KOSPI, 주식 10종, USD/KRW 환율, 펀더멘털(PER·PBR·시가총액) 일일 증분 적재",
    schedule="0 15 * * *",  # 00:00 KST 매일 (뉴스 수집과 동시 시작)
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


def task_sync_market_data(**_):
    engine = _setup()
    from script.load_market_data import load_all
    load_all(engine)


sync_market_data = PythonOperator(
    task_id="sync_market_data",
    python_callable=task_sync_market_data,
    dag=dag,
)

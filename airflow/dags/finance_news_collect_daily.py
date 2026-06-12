"""
Daily news collection and S3 upload for all financial assets.

Collects one day of news per asset using {{ ds }} (previous day's date).
Schedule: 14:00 UTC (23:00 KST) every weekday, same as finance_market_data_daily.
3 tasks run in parallel (independent).

S3 path: raw/{ticker}/{year}/{month:02d}/{date}.json
"""

from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.operators.bash import BashOperator

ROOT = Path(__file__).resolve().parents[2]

default_args = {
    "owner": "data-eng",
    "depends_on_past": False,
    "start_date": datetime(2026, 6, 9),
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=0),
}

dag = DAG(
    "finance_news_collect_daily",
    default_args=default_args,
    description="KOSPI200, Top10 종목, USD/KRW 뉴스 수집 및 S3 적재",
    schedule="0 14 * * 1-5",
    catchup=False,
    tags=["finance", "news", "collect"],
)

dag.doc_md = __doc__

_collect_prefix = f"cd '{ROOT}' && python '{ROOT}/script/news_data/collect/"
_collect_suffix = "' --date {{ next_ds }}"

t_kospi200 = BashOperator(
    task_id="collect_kospi200_news",
    bash_command=_collect_prefix + "collect_kospi200_news.py" + _collect_suffix,
    execution_timeout=timedelta(hours=1),
    dag=dag,
)

t_top10 = BashOperator(
    task_id="collect_top10_stocks_news",
    bash_command=_collect_prefix + "collect_top10_stocks_news.py" + _collect_suffix,
    execution_timeout=timedelta(hours=1),
    dag=dag,
)

t_usd_krw = BashOperator(
    task_id="collect_usd_krw_news",
    bash_command=_collect_prefix + "collect_usd_krw_news.py" + _collect_suffix,
    execution_timeout=timedelta(hours=1),
    dag=dag,
)

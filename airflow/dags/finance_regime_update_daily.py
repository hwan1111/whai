"""
Daily regime detection, LLM summary, evaluation, and DB upload.

For each of 12 tickers (10 stocks + KOSPI200 + USD_KRW):
  1. regime_news_summary  — recalculate regimes + LLM summary (incremental)
  2. branch               — compare JSON output vs DB; skip if no new regimes
  3. eval_regime_summary  — coverage / semantic similarity evaluation
  4. upload_regime_to_db  — append-mode insert to regime / regime_summary tables

Schedule: 15:30 UTC (00:30 KST) weekdays, 30 min after collect DAG.
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import BranchPythonOperator
from airflow.utils.task_group import TaskGroup

ROOT = Path(__file__).resolve().parents[2]

TICKERS = [
    {"code": "005930",   "db_ticker": "005930"},
    {"code": "000660",   "db_ticker": "000660"},
    {"code": "005380",   "db_ticker": "005380"},
    {"code": "000270",   "db_ticker": "000270"},
    {"code": "079550",   "db_ticker": "079550"},
    {"code": "051910",   "db_ticker": "051910"},
    {"code": "096770",   "db_ticker": "096770"},
    {"code": "055550",   "db_ticker": "055550"},
    {"code": "105560",   "db_ticker": "105560"},
    {"code": "012450",   "db_ticker": "012450"},
    {"code": "KOSPI200", "db_ticker": "000000"},
    {"code": "USD_KRW",  "db_ticker": "USD"},
]

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
    "finance_regime_update_daily",
    default_args=default_args,
    description="12개 종목 국면 계산, LLM 요약, 평가, DB 적재",
    schedule="30 15 * * 1-5",
    catchup=False,
    tags=["finance", "regime", "llm"],
)

dag.doc_md = __doc__


def _make_branch_fn(code: str, db_ticker: str, group_id: str):
    def _branch(**_):
        import pymysql

        json_path = Path(f"/opt/data/{code}/regime_news_summary_{code}.json")
        if not json_path.exists():
            return f"{group_id}.skip_{code}"

        summaries = json.loads(json_path.read_text(encoding="utf-8"))
        json_ids = {s["regime_id"] for s in summaries}

        raw_url = os.environ["SERVICE_DATABASE_URL"]
        parsed = urlparse(raw_url.replace("mysql+pymysql://", "mysql://", 1).split("?")[0])
        conn = pymysql.connect(
            host=parsed.hostname,
            port=parsed.port or 3306,
            db=parsed.path.lstrip("/"),
            user=parsed.username,
            password=parsed.password,
            charset="utf8mb4",
            ssl={"ca": "/opt/certs/ca.pem"},
            autocommit=True,
        )
        cur = conn.cursor()
        cur.execute("SELECT regime_id FROM regime WHERE ticker = %s", (db_ticker,))
        db_ids = {r[0] for r in cur.fetchall()}
        conn.close()

        if json_ids - db_ids:
            return f"{group_id}.eval_{code}"
        return f"{group_id}.skip_{code}"

    _branch.__name__ = f"branch_{code}"
    return _branch


_script = str(ROOT / "script")

for t in TICKERS:
    code = t["code"]
    db_ticker = t["db_ticker"]
    group_id = f"group_{code}"

    upload_extra = f" --db-ticker {db_ticker}" if db_ticker != code else ""

    with TaskGroup(group_id=group_id, dag=dag) as tg:
        summary = BashOperator(
            task_id=f"summary_{code}",
            bash_command=(
                f"cd '{ROOT}' && python '{_script}/news_data/eval/regime_news_summary.py'"
                f" --ticker {code}"
            ),
            execution_timeout=timedelta(hours=3),
            dag=dag,
        )

        branch = BranchPythonOperator(
            task_id=f"branch_{code}",
            python_callable=_make_branch_fn(code, db_ticker, group_id),
            dag=dag,
        )

        eval_task = BashOperator(
            task_id=f"eval_{code}",
            bash_command=(
                f"cd '{ROOT}' && python '{_script}/news_data/eval/eval_regime_summary.py'"
                f" --ticker {code}"
                f" --output /opt/data/{code}/eval_regime_summary_{code}.json"
            ),
            execution_timeout=timedelta(hours=1),
            dag=dag,
        )

        upload = BashOperator(
            task_id=f"upload_{code}",
            bash_command=(
                f"cd '{ROOT}' && python '{_script}/others/upload_regime_to_db.py'"
                f" --ticker {code} --mode append{upload_extra}"
            ),
            execution_timeout=timedelta(minutes=30),
            dag=dag,
        )

        skip = EmptyOperator(task_id=f"skip_{code}", dag=dag)

        skip_cleanup = BashOperator(
            task_id=f"skip_cleanup_{code}",
            bash_command=(
                f"cd '{ROOT}' && python '{_script}/others/upload_regime_to_db.py'"
                f" --ticker {code} --cleanup-only"
            ),
            execution_timeout=timedelta(minutes=5),
            dag=dag,
        )

        summary >> branch >> [eval_task, skip]
        eval_task >> upload
        skip >> skip_cleanup

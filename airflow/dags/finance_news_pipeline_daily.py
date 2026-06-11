"""
Daily news pipeline: collect → preprocess/S3 → LLM regime summary → DB upload.

Schedule: 01:00 UTC (10:00 KST) 평일
  Stage 1. collect_news       — 전일 뉴스 크롤링 (10개 종목)
  Stage 2. preprocess_upload  — 전처리 후 S3 preprocessed/{ticker}/ 업로드
  Stage 3. regime_summary_*   — 종목별 LLM 분석 (DB 마지막 end_date+1 ~ 7일 전)
  Stage 4. load_db_*          — regime JSON → MySQL (중복 스킵)

LLM 분석은 "닫힌 국면"만 처리하기 위해 --end를 7일 전으로 설정.
새로운 국면이 없으면 자동 스킵.
"""

import os
import subprocess
import sys
from datetime import datetime, timedelta, date
from pathlib import Path

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.utils.task_group import TaskGroup

ROOT = Path(__file__).resolve().parents[2]

TICKER_META = {
    "005930": ("삼성전자",              "반도체"),
    "000660": ("SK하이닉스",            "반도체"),
    "005380": ("현대차",               "자동차"),
    "000270": ("기아",                 "자동차"),
    "079550": ("LIG디펜스앤에어로스페이스", "방산"),
    "012450": ("한화에어로스페이스",      "방산"),
    "105560": ("KB금융",               "금융"),
    "055550": ("신한지주",              "금융"),
    "051910": ("LG화학",               "화학"),
    "096770": ("SK이노베이션",           "화학"),
}

# USD는 S3 폴더명이 다름 — 별도 처리
USD_META = {
    "ticker_code": "USD",
    "ticker_name": "달러/원 환율",
    "sector":      "환율",
    "s3_ticker":   "USD_KRW",
}

# KOSPI: 가격은 KS11, 뉴스는 KOSPI200
KOSPI_META = {
    "ticker_code": "000000",
    "ticker_name": "KOSPI",
    "sector":      "지수",
    "s3_ticker":   "KOSPI200",
    "fdr_ticker":  "KS11",
}

LLM_BUFFER_DAYS = 7   # 현재 열린 국면 분석 방지용 버퍼
LLM_PROVIDER    = "openrouter"

default_args = {
    "owner":            "data-eng",
    "depends_on_past":  False,
    "start_date":       datetime(2026, 6, 10),
    "email_on_failure": True,
    "email_on_retry":   False,
    "retries":          1,
    "retry_delay":      timedelta(minutes=10),
}

dag = DAG(
    "finance_news_pipeline_daily",
    default_args=default_args,
    description="뉴스 수집 → S3 전처리 → LLM 국면 분석 → DB 업로드 (일별)",
    schedule="0 15 * * *",  # 15:00 UTC = 00:00 KST 매일 (주말 뉴스도 수집)
    catchup=False,
    tags=["finance", "news", "llm", "pipeline"],
)

dag.doc_md = __doc__


# ──────────────────────────────────────────────
# Stage 1: 전일 뉴스 수집
# ──────────────────────────────────────────────

task_collect = BashOperator(
    task_id="collect_news",
    bash_command=(
        f"cd {ROOT} && "
        ".venv/bin/python script/news_data/news_collector.py "
        "--start {{ ds }} --end {{ ds }}"
    ),
    dag=dag,
)

task_collect_kospi200 = BashOperator(
    task_id="collect_kospi200_news",
    bash_command=(
        f"cd {ROOT} && "
        ".venv/bin/python script/news_data/collect_kospi200_news.py "
        "--start {{ ds }} --end {{ ds }}"
    ),
    dag=dag,
)


# ──────────────────────────────────────────────
# Stage 1.5: raw S3 업로드 (수집 완료 후, 전처리 전)
# ──────────────────────────────────────────────

task_upload_raw = BashOperator(
    task_id="upload_raw_to_s3",
    bash_command=(
        f"cd {ROOT} && "
        ".venv/bin/python script/news_data/upload_raw_to_s3.py "
        "--since {{ ds }}"
    ),
    dag=dag,
)


# ──────────────────────────────────────────────
# Stage 2: 전처리 + S3 업로드
# ──────────────────────────────────────────────

task_preprocess = BashOperator(
    task_id="preprocess_upload",
    bash_command=(
        f"cd {ROOT} && "
        ".venv/bin/python script/news_data/preprocess_and_upload.py "
        "--since {{ ds }}"
    ),
    dag=dag,
)

task_preprocess_kospi200 = BashOperator(
    task_id="preprocess_upload_kospi200",
    bash_command=(
        f"cd {ROOT} && "
        ".venv/bin/python script/news_data/preprocess_and_upload_kospi200.py "
        "--since {{ ds }}"
    ),
    dag=dag,
)


# ──────────────────────────────────────────────
# Stage 3 + 4: 종목별 LLM 분석 → DB 업로드
# ──────────────────────────────────────────────

def _regime_summary_task(ticker_code: str, ticker_name: str, sector: str,
                         s3_ticker: str | None = None, fdr_ticker: str | None = None,
                         **context) -> None:
    """마지막 regime의 start_date부터 7일 전까지 재분석 (마지막 국면 재오픈)."""
    sys.path.insert(0, str(ROOT))
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env.local", override=True)

    import pymysql

    ca_path = str(ROOT / "config" / "certs" / "ca.pem")
    conn = pymysql.connect(
        host="mysql-12676458-whai.b.aivencloud.com", port=16935,
        db="whai_service",
        user=os.environ["BACKEND_DB_USER"], password=os.environ["BACKEND_DB_PASSWORD"],
        charset="utf8mb4", ssl={"ca": ca_path},
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT start_date, end_date FROM regime WHERE ticker = %s ORDER BY end_date DESC LIMIT 1",
                (ticker_code,),
            )
            row = cur.fetchone()
    finally:
        conn.close()

    end_date = date.today() - timedelta(days=LLM_BUFFER_DAYS)
    end_str  = end_date.isoformat()

    if row is None:
        start_str = "2020-01-01"
    else:
        last_start = row["start_date"]
        last_end   = row["end_date"]
        if last_end >= end_date:
            print(f"[{ticker_code}] 이미 최신 (last_end={last_end}, buffer_end={end_str}) — 스킵")
            return
        # 마지막 국면을 재오픈해서 start_date부터 재분석
        start_str = last_start.isoformat()

    if start_str > end_str:
        print(f"[{ticker_code}] 분석 기간 없음 (start={start_str}, buffer_end={end_str}) — 스킵")
        return

    print(f"[{ticker_code}] LLM 분석: {start_str} ~ {end_str}")

    cmd = [
        str(ROOT / ".venv" / "bin" / "python"),
        str(ROOT / "script" / "news_data" / "regime_news_summary.py"),
        "--provider",    LLM_PROVIDER,
        "--ticker-code", ticker_code,
        "--ticker-name", ticker_name,
        "--sector",      sector,
        "--start",       start_str,
        "--end",         end_str,
    ]
    if s3_ticker:
        cmd += ["--s3-ticker", s3_ticker]
    if fdr_ticker:
        cmd += ["--fdr-ticker", fdr_ticker]

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
    print(result.stdout)
    if result.returncode != 0:
        raise RuntimeError(f"regime_news_summary 실패 [{ticker_code}]:\n{result.stderr}")


def _load_db_task(ticker_code: str, **context) -> None:
    """regime JSON → MySQL 업로드 (마지막 국면 재삽입)."""
    sys.path.insert(0, str(ROOT))
    cmd = [
        str(ROOT / ".venv" / "bin" / "python"),
        str(ROOT / "script" / "load_regime_to_db.py"),
        "--ticker", ticker_code,
        "--auto-since",  # JSON 최초 start_date 이후 DB 삭제 후 재삽입
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
    print(result.stdout)
    if result.returncode != 0:
        raise RuntimeError(f"load_regime_to_db 실패 [{ticker_code}]:\n{result.stderr}")


# 10개 KRX 종목 태스크 생성
for ticker_code, (ticker_name, sector) in TICKER_META.items():
    with TaskGroup(group_id=f"ticker_{ticker_code}", dag=dag) as tg:
        t_summary = PythonOperator(
            task_id="regime_summary",
            python_callable=_regime_summary_task,
            op_kwargs={
                "ticker_code": ticker_code,
                "ticker_name": ticker_name,
                "sector":      sector,
            },
            dag=dag,
        )
        t_load = PythonOperator(
            task_id="load_db",
            python_callable=_load_db_task,
            op_kwargs={"ticker_code": ticker_code},
            dag=dag,
        )
        t_summary >> t_load

    task_preprocess >> tg

# USD 태스크
with TaskGroup(group_id="ticker_USD", dag=dag) as tg_usd:
    t_usd_summary = PythonOperator(
        task_id="regime_summary",
        python_callable=_regime_summary_task,
        op_kwargs=USD_META,
        dag=dag,
    )
    t_usd_load = PythonOperator(
        task_id="load_db",
        python_callable=_load_db_task,
        op_kwargs={"ticker_code": "USD"},
        dag=dag,
    )
    t_usd_summary >> t_usd_load

task_preprocess >> tg_usd

# KOSPI(000000) 태스크
with TaskGroup(group_id="ticker_000000", dag=dag) as tg_kospi:
    t_kospi_summary = PythonOperator(
        task_id="regime_summary",
        python_callable=_regime_summary_task,
        op_kwargs=KOSPI_META,
        dag=dag,
    )
    t_kospi_load = PythonOperator(
        task_id="load_db",
        python_callable=_load_db_task,
        op_kwargs={"ticker_code": "000000"},
        dag=dag,
    )
    t_kospi_summary >> t_kospi_load

task_preprocess_kospi200 >> tg_kospi

# Stage 1 → Stage 1.5 → Stage 2
# 두 수집 태스크가 모두 끝난 뒤 raw 한 번 업로드, 그 다음 각 전처리 실행
[task_collect, task_collect_kospi200] >> task_upload_raw
task_upload_raw >> task_preprocess
task_upload_raw >> task_preprocess_kospi200

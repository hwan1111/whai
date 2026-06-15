"""
Daily news pipeline: collect → preprocess/S3 → LLM regime summary → DB upload.

Schedule: 15:00 UTC (00:00 KST) every day.
News collection starts immediately, while regime analysis waits for market data.
  Stage 1. collect_all_news   — 전일 뉴스 크롤링 (주식 10종 + USD/KRW + KOSPI200)
  Stage 2. preprocess_upload  — 전처리 후 S3 preprocessed/{ticker}/ 업로드
  Stage 3. regime_summary_*   — 마지막 국면 시작일 ~ S3 최신 전처리 날짜 재분석
  Stage 4. load_db_*          — 마지막 국면 삭제 후 재삽입

최신 국면은 새 전처리 데이터가 들어올 때마다 다시 열어 분석한다.
"""

import os
import subprocess
import sys
from datetime import datetime, timedelta, date
from pathlib import Path
from zoneinfo import ZoneInfo

import boto3
from airflow import DAG
from airflow.exceptions import AirflowSkipException
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.utils.task_group import TaskGroup

try:
    from airflow.providers.standard.sensors.external_task import ExternalTaskSensor
except ImportError:
    from airflow.sensors.external_task import ExternalTaskSensor

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
    "ticker_name": "USD/KRW 환율",
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

LLM_PROVIDER    = "openrouter"
S3_BUCKET       = "fisa-news-archive"

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
    schedule="0 15 * * 1-5",  # 15:00 UTC = 00:00 KST 평일
    catchup=False,
    tags=["finance", "news", "llm", "pipeline"],
)

dag.doc_md = __doc__


# 시장 데이터와 뉴스 수집은 자정에 동시에 시작한다.
# 국면 분석만 같은 logical date의 시장 데이터 적재 완료를 기다린다.
wait_for_market_data = ExternalTaskSensor(
    task_id="wait_for_market_data",
    external_dag_id="finance_market_data_daily",
    external_task_id=None,  # DAG 전체 완료 대기
    allowed_states=["success"],
    failed_states=["failed"],
    mode="reschedule",
    poke_interval=60,
    timeout=60 * 60 * 3,
    dag=dag,
)


# 항상 3일 전부터 소급 수집: 주말·공휴일 공백을 요일 분기 없이 메운다.
# 수집기는 이미 받은 날짜를 네트워크 요청 전에 파일 존재로 스킵하므로 재수집 비용은 0에 가깝다.
_since = "{{ macros.ds_add(ds, -3) }}"

# ──────────────────────────────────────────────
# Stage 1: 전일 뉴스 수집
# ──────────────────────────────────────────────

task_collect_all = BashOperator(
    task_id="collect_all_news",
    bash_command=(
        f"cd {ROOT} && "
        "python script/news_data/collect_all_news.py "
        f"--start {_since} --end {{{{ ds }}}}"
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
        "python script/news_data/upload_raw_to_s3.py "
        f"--since {_since}"
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
        "python script/news_data/preprocess/preprocess_and_upload.py "
        f"--since {_since}"
    ),
    dag=dag,
)

task_preprocess_kospi200 = BashOperator(
    task_id="preprocess_upload_kospi200",
    bash_command=(
        f"cd {ROOT} && "
        "python script/news_data/preprocess/preprocess_and_upload_kospi200.py "
        f"--since {_since}"
    ),
    dag=dag,
)


# ──────────────────────────────────────────────
# Stage 3 + 4: 종목별 LLM 분석 → DB 업로드
# ──────────────────────────────────────────────

def _latest_s3_date(prefix: str) -> date | None:
    """S3 prefix 아래 날짜 JSON 중 최신 날짜를 반환한다."""
    latest = None
    paginator = boto3.client("s3").get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            filename = obj["Key"].rsplit("/", 1)[-1]
            if not filename.endswith(".json"):
                continue
            try:
                current = date.fromisoformat(filename[:-5])
            except ValueError:
                continue
            if latest is None or current > latest:
                latest = current
    return latest


def _latest_news_date(s3_ticker: str) -> date | None:
    """뉴스 데이터가 존재하면 완료된 전일을 분석 종료일로 사용한다."""
    candidates = [
        _latest_s3_date(f"raw/{s3_ticker}/"),
        _latest_s3_date(f"preprocessed/{s3_ticker}/"),
    ]
    valid = [current for current in candidates if current is not None]
    if not valid:
        return None
    return datetime.now(ZoneInfo("Asia/Seoul")).date() - timedelta(days=1)


def _regime_summary_task(ticker_code: str, ticker_name: str, sector: str,
                         s3_ticker: str | None = None, fdr_ticker: str | None = None,
                         **context) -> None:
    """마지막 국면 시작일부터 최신 전처리 날짜까지 재분석한다."""
    sys.path.insert(0, str(ROOT))
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=True)

    import pymysql

    news_ticker = s3_ticker or ticker_code
    end_date = _latest_news_date(news_ticker)
    if end_date is None:
        raise AirflowSkipException(f"[{ticker_code}] 전처리 뉴스 없음 ({news_ticker})")

    ca_path = str(Path("/opt/certs/ca.pem"))
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

    end_str  = end_date.isoformat()

    if row is None:
        start_str = "2020-01-01"
    else:
        last_start = row["start_date"]
        last_end   = row["end_date"]
        if last_end >= end_date:
            raise AirflowSkipException(
                f"[{ticker_code}] 이미 최신 (last_end={last_end}, preprocessed_end={end_str})"
            )
        # 마지막 국면을 재오픈해서 start_date부터 재분석
        start_str = last_start.isoformat()

    if start_str > end_str:
        raise AirflowSkipException(
            f"[{ticker_code}] 분석 기간 없음 (start={start_str}, preprocessed_end={end_str})"
        )

    print(f"[{ticker_code}] LLM 분석: {start_str} ~ {end_str}")

    cmd = [
        sys.executable,
        str(ROOT / "script" / "news_data" / "eval" / "regime_news_summary.py"),
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
    """regime JSON → MySQL 업로드 (신규 국면만 append)."""
    sys.path.insert(0, str(ROOT))

    # DB ticker(000000, USD)와 파일 ticker(KOSPI200, USD_KRW) 매핑
    _FILE_TICKER = {"000000": "KOSPI200", "USD": "USD_KRW"}
    _DB_TICKER   = {"KOSPI200": "000000", "USD_KRW": "USD"}

    file_ticker = _FILE_TICKER.get(ticker_code, ticker_code)
    db_ticker   = _DB_TICKER.get(file_ticker, file_ticker)

    cmd = [
        sys.executable,
        str(ROOT / "script" / "others" / "upload_regime_to_db.py"),
        "--ticker", file_ticker,
        "--mode",   "append",
    ]
    if db_ticker != file_ticker:
        cmd += ["--db-ticker", db_ticker]

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

    [task_preprocess, wait_for_market_data] >> tg

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

[task_preprocess, wait_for_market_data] >> tg_usd

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

[task_preprocess_kospi200, wait_for_market_data] >> tg_kospi

# Stage 1 → Stage 1.5 → Stage 2
# 통합 수집이 끝난 뒤 raw 한 번 업로드, 그 다음 각 전처리 실행
task_collect_all >> task_upload_raw
task_upload_raw >> task_preprocess
task_upload_raw >> task_preprocess_kospi200

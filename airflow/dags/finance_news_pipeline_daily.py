"""
Daily news pipeline: collect → raw S3 → preprocess/S3.

Schedule: 15:00 UTC (00:00 KST) every day.
  Stage 1.   collect_all_news          — 뉴스 크롤링 (주식 10종 + USD/KRW + KOSPI200)
  Stage 1.5. upload_raw_to_s3          — raw S3 업로드
  Stage 2.   preprocess_upload(_*)     — 전처리 후 S3 preprocessed/{ticker}/ 업로드

국면(regime) × 뉴스 LLM 요약은 별도 DAG(finance_regime_news_summary_daily)에서
regime_update와 이 파이프라인이 모두 끝난 뒤 수행한다.
"""

from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.operators.bash import BashOperator

ROOT = Path(__file__).resolve().parents[2]

default_args = {
    "owner":                     "data-eng",
    "depends_on_past":           False,
    "start_date":                datetime(2026, 6, 10),
    "email_on_failure":          True,
    "email_on_retry":            False,
    "retries":                   3,
    "retry_delay":               timedelta(minutes=10),
    "retry_exponential_backoff": True,
    "max_retry_delay":           timedelta(hours=1),
}

dag = DAG(
    "finance_news_pipeline_daily",
    default_args=default_args,
    description="뉴스 수집 → S3 raw → S3 전처리 (일별)",
    schedule="0 15 * * *",  # 15:00 UTC = 00:00 KST 매일
    catchup=False,
    max_active_runs=1,
    tags=["finance", "news", "pipeline"],
)

dag.doc_md = __doc__


# 항상 3일 전부터 소급 수집: 주말·공휴일 공백을 요일 분기 없이 메운다.
# 수집기는 이미 받은 날짜를 네트워크 요청 전에 파일 존재로 스킵하므로 재수집 비용은 0에 가깝다.
_since = "{{ macros.ds_add(ds, -3) }}"

# ──────────────────────────────────────────────
# Stage 1: 뉴스 수집
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


# Stage 1 → Stage 1.5 → Stage 2
# 통합 수집이 끝난 뒤 raw 한 번 업로드, 그 다음 각 전처리 실행
task_collect_all >> task_upload_raw
task_upload_raw >> task_preprocess
task_upload_raw >> task_preprocess_kospi200

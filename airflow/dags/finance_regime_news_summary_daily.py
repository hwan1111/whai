"""
Daily regime news LLM summary pipeline.

Schedule: 03:00 UTC (12:00 KST) every day
Depends on: finance_news_pipeline_daily 완료

흐름:
  1. regime_update_daily 완료 대기
  2. 주요 종목(삼성, SK하이닉스, 현대차 등)의 국면별 뉴스 요약 생성
  3. 요약 결과를 S3 summary/{ticker}/{start}_{end}.json에 저장
  4. MLflow에 토큰/비용/처리 통계 기록
"""

import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

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

# 모든 티커를 DB에서 동적으로 조회
# DAG 실행 시 regime 테이블의 모든 종목 자동 처리
TICKERS = None  # None이면 스크립트에서 자동으로 DB 조회

GATEWAY_ENDPOINT = os.getenv("REGIME_LLM_ENDPOINT", "low_performance_llm")
MAX_TOKENS = int(os.getenv("REGIME_LLM_MAX_TOKENS", "800"))
TEMPERATURE = float(os.getenv("REGIME_LLM_TEMPERATURE", "0.3"))

default_args = {
    "owner": "data-eng",
    "depends_on_past": False,
    "start_date": datetime(2026, 6, 10),
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=15),
}

dag = DAG(
    "finance_regime_news_summary_daily",
    default_args=default_args,
    description="국면별 뉴스 LLM 요약 생성 (일별)",
    schedule="30 16 * * 1-5",  # 16:30 UTC = 01:30 KST 평일 (regime_update 완료 후)
    catchup=False,
    tags=["finance", "news", "llm", "regime", "summary"],
)

dag.doc_md = __doc__

logger = logging.getLogger(__name__)


# 국면 업데이트 DAG가 완료될 때까지 대기
wait_for_regime_update = ExternalTaskSensor(
    task_id="wait_for_regime_update",
    external_dag_id="finance_regime_update_daily",
    external_task_id=None,  # DAG 전체 완료 대기
    allowed_states=["success"],
    failed_states=["failed"],
    mode="reschedule",
    poke_interval=60,
    timeout=60 * 60 * 6,  # 최대 6시간 (15:30 UTC 시작 기준 여유)
    dag=dag,
)


validate_env = BashOperator(
    task_id="validate_python_env",
    bash_command="python -c 'import mlflow, boto3; from model.llm.prompt_loader import load_prompt; print(\"✓ 의존성 확인 완료\")'",
    dag=dag,
)


# 모든 티커 처리 (스크립트가 DB에서 자동으로 조회)
run_summary = BashOperator(
    task_id="run_regime_summary_all_tickers",
    bash_command="""
    cd /app
    python script/llm/regime_news_summary_pipeline.py \\
      --endpoint low_performance_llm \\
      --max-tokens 800 \\
      --temperature 0.3
    """,
    dag=dag,
)


# 의존성 설정
wait_for_regime_update >> validate_env >> run_summary

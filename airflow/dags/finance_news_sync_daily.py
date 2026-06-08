"""
Daily news data sync to S3.

Schedule: 02:00 UTC (11:00 KST) daily
Tickers: Read from config/news_tickers.json

This DAG:
1. Reads ticker list from config
2. Fetches daily news for each ticker (from local or Data team API)
3. Uploads to S3 with date-based partitioning
4. Logs results
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.utils.task_group import TaskGroup
from airflow.exceptions import AirflowException


# Default DAG arguments
default_args = {
    "owner": "data-eng",
    "depends_on_past": False,
    "start_date": datetime(2026, 1, 1),
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

# DAG definition
dag = DAG(
    "finance_news_sync_daily",
    default_args=default_args,
    description="Daily sync of news data to S3",
    schedule="0 2 * * *",  # 02:00 UTC = 11:00 KST
    catchup=False,
    tags=["finance", "news", "data-pipeline"],
)


# ========================
# Helper Functions
# ========================

def load_ticker_config() -> Dict:
    """Load ticker configuration from config/news_tickers.json"""
    config_path = Path("/home/airflow/dags/../../../config/news_tickers.json")

    # Try relative to DAG file location
    if not config_path.exists():
        config_path = Path(__file__).parent.parent.parent / "config" / "news_tickers.json"

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r") as f:
        return json.load(f)


def validate_config() -> Dict:
    """Validate ticker config and return tickers list"""
    config = load_ticker_config()

    if not config.get("tickers"):
        raise AirflowException("No tickers configured in config/news_tickers.json")

    return config


def fetch_news_data(**context) -> List[str]:
    """
    Fetch news data for configured tickers.

    Returns:
        List of (ticker, data_path) tuples ready for upload
    """
    config = load_ticker_config()
    execution_date = context["execution_date"]
    tickers_to_process = []

    for ticker_config in config["tickers"]:
        ticker = ticker_config["ticker"]
        company = ticker_config["company"]
        data_source = ticker_config.get("data_source", "local")

        try:
            if data_source == "local":
                # Current: read from local file system
                news_data_path = (
                    Path("/home/airflow/dags/../../../data")
                    / f"News_{company}_{ticker}"
                )

                # For development/testing
                if not news_data_path.exists():
                    news_data_path = Path(f"data/News_{company}_{ticker}")

                if news_data_path.exists():
                    tickers_to_process.append({
                        "ticker": ticker,
                        "company": company,
                        "data_source": data_source,
                        "data_path": str(news_data_path),
                    })
                    print(f"✓ Found data for {company} ({ticker}): {news_data_path}")
                else:
                    print(f"⚠️  No data found for {company} ({ticker}): {news_data_path}")

            elif data_source == "data_team_api":
                # TODO: Implement Data team API integration
                print(f"⏳ Data team API not yet implemented for {company} ({ticker})")

            else:
                print(f"⚠️  Unknown data source: {data_source}")

        except Exception as e:
            print(f"✗ Error processing {ticker}: {str(e)}")
            raise

    # Push to XCom for downstream tasks
    context["task_instance"].xcom_push(
        key="tickers_to_process",
        value=tickers_to_process,
    )

    return tickers_to_process


def upload_ticker_news(ticker_info: Dict, **context) -> Dict:
    """
    Upload news data for a single ticker to S3.

    This task is dynamically created for each ticker.
    """
    import boto3

    ticker = ticker_info["ticker"]
    company = ticker_info["company"]
    data_path = ticker_info["data_path"]
    config = load_ticker_config()

    bucket_name = config["s3_bucket"]

    try:
        # Run upload script
        upload_script = (
            Path(__file__).parent.parent.parent / "script" / "upload_news_to_s3.py"
        )

        import subprocess

        result = subprocess.run(
            [
                "python",
                str(upload_script),
                "--local-dir", data_path,
                "--bucket", bucket_name,
                "--ticker", ticker,
                "--company", company,
                "--workers", "3",
            ],
            capture_output=True,
            text=True,
            timeout=3600,  # 1 hour timeout
        )

        if result.returncode != 0:
            raise AirflowException(
                f"Upload failed for {company} ({ticker}):\n{result.stderr}"
            )

        print(result.stdout)

        return {
            "ticker": ticker,
            "company": company,
            "status": "success",
            "output": result.stdout,
        }

    except Exception as e:
        print(f"✗ Error uploading {company} ({ticker}): {str(e)}")
        raise


# ========================
# DAG Tasks
# ========================

# Task 1: Validate config
task_validate = PythonOperator(
    task_id="validate_config",
    python_callable=validate_config,
    dag=dag,
)

# Task 2: Fetch news data
task_fetch = PythonOperator(
    task_id="fetch_news_data",
    python_callable=fetch_news_data,
    dag=dag,
)

# Task 3: Dynamic upload tasks (one per ticker)
def dynamic_upload_tasks(**context):
    """Create upload task for each ticker"""
    tickers = context["task_instance"].xcom_pull(
        task_ids="fetch_news_data",
        key="tickers_to_process",
    )

    if not tickers:
        print("⚠️  No tickers to process")
        return []

    task_ids = []
    for i, ticker_info in enumerate(tickers):
        ticker = ticker_info["ticker"]
        task_id = f"upload_news_{ticker}_{i}"

        task = PythonOperator(
            task_id=task_id,
            python_callable=upload_ticker_news,
            op_kwargs={"ticker_info": ticker_info},
    
            dag=dag,
        )
        task_ids.append(task_id)

    return task_ids


task_upload_dynamic = PythonOperator(
    task_id="prepare_upload_tasks",
    python_callable=lambda **ctx: dynamic_upload_tasks(**ctx),
    dag=dag,
)

# Task 4: Final summary
def final_summary(**context):
    """Print final summary"""
    execution_date = context["execution_date"]
    print(f"\n{'='*50}")
    print(f"Daily News Sync Complete")
    print(f"Execution Date: {execution_date}")
    print(f"{'='*50}\n")


task_summary = PythonOperator(
    task_id="final_summary",
    python_callable=final_summary,
    dag=dag,
)

# ========================
# Task Dependencies
# ========================

task_validate >> task_fetch >> task_upload_dynamic >> task_summary


# ========================
# DAG Metadata
# ========================

# Set DAG docstring for UI
dag.doc_md = __doc__

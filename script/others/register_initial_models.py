"""
S3에 올라간 SU sklearn pkl 파일들을 MLflow Model Registry에 최초 등록.

실행:
    python script/others/register_initial_models.py

등록 후 MLflow UI → Models 탭에서 종목별 모델 버전 확인 가능.
  모델명 패턴: stock-{ticker}  (예: stock-096770)
  초기 stage: Production
"""

import os
import pickle
import sys
import tempfile
from pathlib import Path

import boto3
import mlflow
import mlflow.sklearn
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env", override=True)
sys.stdout.reconfigure(encoding="utf-8")

# auth env 설정 후 URI는 직접 지정 (.env의 구 loclx URI 덮어쓰기 방지)
os.environ["MLFLOW_TRACKING_USERNAME"] = os.environ.get("MLFLOW_TRACKING_USERNAME", "admin")
os.environ["MLFLOW_TRACKING_PASSWORD"] = os.environ.get("MLFLOW_TRACKING_PASSWORD", "Woorifisateam4")
MLFLOW_URI = "http://52.78.237.104:5001"
mlflow.set_tracking_uri(MLFLOW_URI)

S3_BUCKET = "whai-stock-models"

# sklearn 종목만 등록 (PatchTST는 torch 모델이라 별도 처리 필요)
SKLEARN_TICKERS = {
    "096770": {"name": "SK이노베이션", "model": "LGBMRegressor",       "mape": 5.21, "priority": "1"},
    "079550": {"name": "LIG넥스원",    "model": "HuberRegressor",      "mape": 5.68, "priority": "1"},
    "005930": {"name": "삼성전자",     "model": "ExtraTreesRegressor", "mape": 5.09, "priority": "1"},
    "105560": {"name": "KB금융",       "model": "LGBMRegressor",       "mape": 7.07, "priority": "2"},
    "055550": {"name": "신한지주",     "model": "XGBRegressor",        "mape": 2.08, "priority": "2"},
    "012450": {"name": "한화에어로스페이스", "model": "LGBMRegressor", "mape": 11.94,"priority": "2"},
    "000270": {"name": "기아",         "model": "ElasticNet",          "mape": 7.44, "priority": "2"},
}


def register_ticker(ticker: str, info: dict, s3_client, tmp_dir: str):
    s3_key     = f"pretrained/saved_models/{ticker}.pkl"
    local_path = Path(tmp_dir) / f"{ticker}.pkl"

    print(f"[{ticker}] {info['name']} ({info['model']}) 다운로드 중...")
    s3_client.download_file(S3_BUCKET, s3_key, str(local_path))

    with open(local_path, "rb") as f:
        model = pickle.load(f)

    model_name = f"stock-{ticker}"
    mlflow.set_experiment(f"stock_prediction/{ticker}")

    with mlflow.start_run(run_name=f"initial_registration_{ticker}"):
        mlflow.log_params({
            "ticker":        ticker,
            "name":          info["name"],
            "model_type":    info["model"],
            "baseline_mape": info["mape"],
            "priority":      info["priority"],
            "s3_key":        s3_key,
        })
        mlflow.log_metrics({"baseline_mape": info["mape"]})
        mlflow.set_tags({
            "registration_type": "initial",
            "s3_bucket":         S3_BUCKET,
        })
        mlflow.sklearn.log_model(
            sk_model=model,
            artifact_path="model",
            registered_model_name=model_name,
        )

    # Production으로 승격
    client = mlflow.tracking.MlflowClient()
    versions = client.get_latest_versions(model_name)
    latest_ver = max(v.version for v in versions)
    client.transition_model_version_stage(
        name=model_name,
        version=latest_ver,
        stage="Production",
        archive_existing_versions=True,
    )
    print(f"  → MLflow Registry: {model_name} v{latest_ver} (Production) 등록 완료")


def main():
    s3_client = boto3.client("s3")

    with tempfile.TemporaryDirectory() as tmp_dir:
        for ticker, info in SKLEARN_TICKERS.items():
            try:
                register_ticker(ticker, info, s3_client, tmp_dir)
            except Exception as e:
                print(f"[{ticker}] 실패: {e}")

    print("\n초기 모델 등록 완료. MLflow UI → Models 탭에서 확인하세요.")


if __name__ == "__main__":
    main()

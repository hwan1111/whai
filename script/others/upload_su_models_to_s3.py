"""
SU 모델 pkl 파일을 S3에 최초 1회 업로드하는 스크립트.

S3 경로:
  whai-stock-models/su/saved_models/{ticker}.pkl   ← sklearn 7종목
  whai-stock-models/su/patchtst_v18_model.pkl      ← PatchTST 3종목 공용

실행:
    python script/others/upload_su_models_to_s3.py
"""

import sys
from pathlib import Path

import boto3
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env.local", override=True)
MODEL_ROOT = ROOT / "model" / "주가예측모델"
S3_BUCKET  = "whai-stock-models"

sys.stdout.reconfigure(encoding="utf-8")

SKLEARN_TICKERS = ["096770", "079550", "005930", "105560", "055550", "012450", "000270"]

UPLOAD_MAP = {
    # 로컬 경로: S3 key
    **{
        str(MODEL_ROOT / "su" / "data" / "saved_models" / f"{t}.pkl"):
        f"pretrained/saved_models/{t}.pkl"
        for t in SKLEARN_TICKERS
    },
    str(MODEL_ROOT / "su" / "model" / "patchtst_v18_model.pkl"):
        "pretrained/patchtst_v18_model.pkl",
}


def main():
    s3 = boto3.client("s3")

    for local_path, s3_key in UPLOAD_MAP.items():
        p = Path(local_path)
        if not p.exists():
            print(f"[SKIP] 로컬 파일 없음: {p.name}")
            continue

        size_mb = round(p.stat().st_size / 1_048_576, 2)
        print(f"[UPLOAD] {p.name} ({size_mb} MB) → s3://{S3_BUCKET}/{s3_key}")
        s3.upload_file(str(p), S3_BUCKET, s3_key)
        print(f"  완료")

    print("\n전체 업로드 완료.")


if __name__ == "__main__":
    main()

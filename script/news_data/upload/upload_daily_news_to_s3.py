"""
수집된 특정 날짜의 뉴스 JSON을 S3에 업로드.

data/news/{company}_{ticker}/{date}.json
  → s3://fisa-news-archive/raw/{ticker}/{year}/{month}/{date}.json

로컬 파일은 삭제하지 않음 (collect 스크립트의 skip 체크용으로 유지).

실행:
    python script/news_data/upload/upload_daily_news_to_s3.py --date 2026-06-11
"""

import argparse
import glob
import json
import logging
import os
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(ROOT / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

BUCKET   = "fisa-news-archive"
DATA_DIR = ROOT / "data" / "news"


def upload(date_str: str) -> None:
    year, month = date_str[:4], date_str[5:7]
    pattern = str(DATA_DIR / "*" / f"{date_str}.json")
    files = glob.glob(pattern)

    if not files:
        log.info(f"업로드 대상 없음: {date_str} (수집 파일 없거나 비영업일)")
        return

    s3 = boto3.client("s3")
    success = 0
    for filepath in files:
        folder = os.path.basename(os.path.dirname(filepath))
        ticker = folder.split("_")[-1]
        key = f"raw/{ticker}/{year}/{month}/{date_str}.json"

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                doc = json.load(f)
            doc["fulltext_length"] = len(doc.get("fulltext") or "")

            s3.put_object(
                Bucket=BUCKET,
                Key=key,
                Body=json.dumps(doc, ensure_ascii=False, indent=2).encode("utf-8"),
                ContentType="application/json; charset=utf-8",
            )
            log.info(f"  uploaded: {key}")
            success += 1
        except ClientError as e:
            log.error(f"  S3 오류 {key}: {e}")
        except Exception as e:
            log.error(f"  업로드 실패 {key}: {e}")

    log.info(f"완료: {success}/{len(files)}건 업로드")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="날짜별 뉴스 S3 업로드")
    parser.add_argument("--date", required=True, help="업로드 날짜 YYYY-MM-DD")
    args = parser.parse_args()
    upload(args.date)

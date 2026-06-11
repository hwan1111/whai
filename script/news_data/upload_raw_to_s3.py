"""
로컬 data/news/ raw 파일 → S3 raw/{ticker}/{year}/{month}/{date}.json 업로드

Usage:
    python script/news_data/upload_raw_to_s3.py
    python script/news_data/upload_raw_to_s3.py --since 2026-05-13
"""

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

import boto3
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env.local", override=True)

BUCKET   = "fisa-news-archive"
DATA_DIR = ROOT / "data" / "news"

# 폴더명 → S3 ticker 매핑 (폴더명의 마지막 _ 이후가 ticker)
# 예: 삼성전자_005930 → 005930 / 코스피200_KOSPI200 → KOSPI200
def folder_to_ticker(folder_name: str) -> str:
    return folder_name.rsplit("_", 1)[-1]


def collect_files(since: date | None) -> list[tuple[Path, str]]:
    """(로컬파일, s3_key) 목록 반환"""
    items = []
    for folder in DATA_DIR.iterdir():
        if not folder.is_dir():
            continue
        ticker = folder_to_ticker(folder.name)
        for f in folder.glob("*.json"):
            date_str = f.stem  # YYYY-MM-DD
            if len(date_str) != 10:
                continue
            if since and date_str < since.isoformat():
                continue
            year, month = date_str[:4], date_str[5:7]
            s3_key = f"raw/{ticker}/{year}/{month}/{f.name}"
            items.append((f, s3_key))
    return items


def upload_file(s3_client, local_path: Path, s3_key: str) -> str:
    with open(local_path, "rb") as fh:
        s3_client.put_object(
            Bucket=BUCKET,
            Key=s3_key,
            Body=fh.read(),
            ContentType="application/json; charset=utf-8",
        )
    return s3_key


def main() -> None:
    parser = argparse.ArgumentParser(description="로컬 raw 뉴스 → S3 업로드")
    parser.add_argument("--since", default=None, help="이 날짜 이후만 업로드 YYYY-MM-DD")
    args = parser.parse_args()
    since_date = date.fromisoformat(args.since) if args.since else None

    sys.stdout.reconfigure(encoding="utf-8")

    items = collect_files(since_date)
    if not items:
        print("업로드할 파일 없음")
        return

    print(f"[시작] {len(items)}개 파일 S3 raw/ 업로드 (since={since_date or '전체'})")

    s3 = boto3.client("s3")
    success = error = 0

    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(upload_file, s3, p, k): k for p, k in items}
        for i, future in enumerate(as_completed(futures), 1):
            try:
                future.result()
                success += 1
            except Exception as e:
                print(f"  [오류] {futures[future]}: {e}")
                error += 1
            if i % 100 == 0 or i == len(items):
                print(f"  진행: {i}/{len(items)}")

    print(f"\n[완료] 성공 {success}개 / 오류 {error}개")


if __name__ == "__main__":
    main()

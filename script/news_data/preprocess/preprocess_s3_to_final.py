"""
S3 raw → preprocessed_final 전처리 적재 스크립트

기존 preprocess_and_upload.py는 로컬(data/news)을 읽어 S3 'preprocessed/'에 올렸다.
본 스크립트는 **로컬 없이 S3 'raw/'를 직접 읽어** 동일 구조로 'preprocessed_final/'에
적재한다. 전처리는 금융 기호(., %, +, -, ,)를 보존하는 clean_financial_news 사용.

키 구조 (prefix만 교체, 나머지 동일):
    raw/{ticker}/{YYYY}/{MM}/{YYYY-MM-DD}.json
    → preprocessed_final/{ticker}/{YYYY}/{MM}/{YYYY-MM-DD}.json

버킷: fisa-news-archive

실행:
    python script/news_data/preprocess/preprocess_s3_to_final.py            # 전체
    python script/news_data/preprocess/preprocess_s3_to_final.py --ticker 005930   # 특정 종목만
    python script/news_data/preprocess/preprocess_s3_to_final.py --limit 20 --dry-run  # 미리보기
"""

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import boto3
from dotenv import load_dotenv

# clean_financial_news 단일 출처 재사용 (preprocess_and_upload.py)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from preprocess_and_upload import clean_financial_news

load_dotenv(".env")

BUCKET_NAME = "fisa-news-archive"
SRC_PREFIX  = "raw/"
DST_PREFIX  = "preprocessed_final/"

s3 = boto3.client("s3")


def list_raw_keys(ticker: str | None = None) -> list[str]:
    """raw/ 하위 모든 .json 키 목록 (ticker 지정 시 해당 종목만)."""
    prefix = f"{SRC_PREFIX}{ticker}/" if ticker else SRC_PREFIX
    keys: list[str] = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix=prefix):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(".json"):
                keys.append(obj["Key"])
    return keys


def process_key(src_key: str, dry_run: bool = False) -> str:
    """raw 키 1건을 전처리해 preprocessed_final로 적재. 처리한 dst_key 반환."""
    dst_key = src_key.replace(SRC_PREFIX, DST_PREFIX, 1)

    obj  = s3.get_object(Bucket=BUCKET_NAME, Key=src_key)
    data = json.loads(obj["Body"].read().decode("utf-8"))

    fulltext = data.get("fulltext", "")
    cleaned  = clean_financial_news(fulltext)
    data["fulltext"]        = cleaned
    data["fulltext_length"] = len(cleaned)

    if not dry_run:
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        s3.put_object(
            Bucket=BUCKET_NAME, Key=dst_key, Body=body,
            ContentType="application/json; charset=utf-8",
        )
    return dst_key


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", type=str, default="", help="특정 종목코드만 (기본 전체)")
    ap.add_argument("--limit", type=int, default=0, help="처리할 최대 파일 수 (0=전체)")
    ap.add_argument("--dry-run", action="store_true", help="S3 쓰기 없이 목록/카운트만")
    ap.add_argument("--workers", type=int, default=10, help="병렬 스레드 수")
    args = ap.parse_args()

    ticker = args.ticker.strip() or None
    print(f"[목록 수집] s3://{BUCKET_NAME}/{SRC_PREFIX}{ticker or ''} ...")
    keys = list_raw_keys(ticker)
    if args.limit:
        keys = keys[: args.limit]
    total = len(keys)
    print(f"[시작] raw 파일 {total}개 → {DST_PREFIX} 적재 "
          f"(dry_run={args.dry_run}, workers={args.workers})\n")

    if args.dry_run:
        for k in keys[:10]:
            print("  ", k, "→", k.replace(SRC_PREFIX, DST_PREFIX, 1))
        if total > 10:
            print(f"  ... 외 {total - 10}건")

    ok = fail = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(process_key, k, args.dry_run): k for k in keys}
        for idx, fut in enumerate(as_completed(futures), 1):
            try:
                fut.result()
                ok += 1
            except Exception as e:
                fail += 1
                print(f"오류 {futures[fut]}: {e}")
            if idx % 1000 == 0 or idx == total:
                print(f"진행: {idx}/{total} (성공 {ok}, 실패 {fail})")

    print(f"\n[완료] 성공 {ok} / 실패 {fail} / 전체 {total}")


if __name__ == "__main__":
    main()

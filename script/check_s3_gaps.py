"""S3 preprocessed 폴더별 누락 날짜 체크 (영업일 무관, 캘린더 기준)"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
from datetime import date, timedelta
import boto3
from dotenv import load_dotenv
load_dotenv(".env", override=True)

s3 = boto3.client("s3")
BUCKET = "fisa-news-archive"

# 체크할 prefix 목록
PREFIXES = [
    "preprocessed/005930",   # 삼성전자
    "preprocessed/000660",   # SK하이닉스
    "preprocessed/005380",   # 현대차
    "preprocessed/000270",   # 기아
    "preprocessed/079550",   # LIG
    "preprocessed/012450",   # 한화
    "preprocessed/105560",   # KB금융
    "preprocessed/055550",   # 신한지주
    "preprocessed/051910",   # LG화학
    "preprocessed/096770",   # SK이노베이션
    "preprocessed/USD_KRW",
    "preprocessed/KOSPI200",
]

START = date(2020, 1, 1)
END   = date(2026, 6, 8)   # 자정 기준 어제까지

def get_all_dates(prefix: str) -> set[str]:
    pag = s3.get_paginator("list_objects_v2")
    dates = set()
    for page in pag.paginate(Bucket=BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            fname = obj["Key"].split("/")[-1]
            if fname.endswith(".json") and len(fname) == 15:  # YYYY-MM-DD.json
                dates.add(fname[:10])
    return dates

def calendar_dates(start: date, end: date) -> list[str]:
    cur, result = start, []
    while cur <= end:
        result.append(cur.isoformat())
        cur += timedelta(days=1)
    return result

all_days = set(calendar_dates(START, END))

print(f"기준: {START} ~ {END}  총 {len(all_days)}일\n")
print(f"{'prefix':<30} {'파일수':>6}  {'첫날':<12} {'마지막날':<12} {'누락':>5}  첫 누락 5건")
print("-" * 100)

for prefix in PREFIXES:
    found = get_all_dates(prefix)
    missing = sorted(all_days - found)
    first = min(found) if found else "-"
    last  = max(found) if found else "-"
    sample = ", ".join(missing[:5]) if missing else "없음"
    print(f"{prefix:<30} {len(found):>6}  {first:<12} {last:<12} {len(missing):>5}  {sample}")

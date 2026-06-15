"""
S3 갭 날짜만 골라서 뉴스 수집 → 전처리 → S3 업로드

Usage:
    python script/fill_s3_gaps.py
"""
import sys, subprocess, json
sys.stdout.reconfigure(encoding="utf-8")
from datetime import date, timedelta
from pathlib import Path
import boto3
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env", override=True)

s3 = boto3.client("s3")
BUCKET = "fisa-news-archive"

# 누락 확인할 종목 (ticker → s3 prefix)
TICKERS = {
    "005930": "005930", "000660": "000660", "005380": "005380",
    "000270": "000270", "079550": "079550", "012450": "012450",
    "105560": "105560", "055550": "055550", "051910": "051910",
    "096770": "096770",
}
START = date(2020, 1, 1)
END   = date(2026, 6, 8)

def get_s3_dates(prefix: str) -> set[str]:
    pag = s3.get_paginator("list_objects_v2")
    dates = set()
    for page in pag.paginate(Bucket=BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            fname = obj["Key"].split("/")[-1]
            if fname.endswith(".json") and len(fname) == 15:
                dates.add(fname[:10])
    return dates

def run(cmd: list[str]) -> None:
    print(f"  $ {' '.join(cmd[-4:])}")
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  [ERROR] {r.stderr[-300:]}")
    else:
        last = r.stdout.strip().split("\n")[-1] if r.stdout.strip() else ""
        if last:
            print(f"  {last}")

python = sys.executable  # 현재 실행 중인 Python 그대로 사용
all_days = set()
cur = START
while cur <= END:
    all_days.add(cur.isoformat())
    cur += timedelta(days=1)

# ── 1. 종목 뉴스 갭 ──────────────────────────────────────────
print("=== 종목 뉴스 갭 수집 ===")
missing_dates: set[str] = set()
for ticker, prefix in TICKERS.items():
    found = get_s3_dates(f"preprocessed/{prefix}")
    gaps  = sorted(all_days - found)
    if gaps:
        print(f"[{ticker}] {len(gaps)}건 누락: {gaps[:5]}{'...' if len(gaps)>5 else ''}")
        missing_dates.update(gaps)

if missing_dates:
    sorted_gaps = sorted(missing_dates)
    print(f"\n종목 전체 누락일: {len(sorted_gaps)}건")
    # 날짜별로 수집 (news_collector --start D --end D)
    for d in sorted_gaps:
        print(f"\n[수집] {d}")
        run([python, "script/news_data/news_collector.py", "--start", d, "--end", d])
    # 전처리 + S3 업로드 (최초 누락일부터)
    print(f"\n[전처리/S3] {sorted_gaps[0]} 이후 업로드")
    run([python, "script/news_data/preprocess_and_upload.py", "--since", sorted_gaps[0]])
else:
    print("종목 뉴스 갭 없음")

# ── 2. KOSPI200 갭 ────────────────────────────────────────────
print("\n=== KOSPI200 뉴스 갭 수집 ===")
kospi_found   = get_s3_dates("preprocessed/KOSPI200")
kospi_missing = sorted(all_days - kospi_found)
if kospi_missing:
    print(f"{len(kospi_missing)}건 누락: {kospi_missing[:5]}{'...' if len(kospi_missing)>5 else ''}")
    run([python, "script/news_data/collect_kospi200_news.py",
         "--start", kospi_missing[0], "--end", kospi_missing[-1]])
    run([python, "script/news_data/preprocess_and_upload_kospi200.py",
         "--since", kospi_missing[0]])
else:
    print("KOSPI200 갭 없음")

print("\n=== 완료 ===")

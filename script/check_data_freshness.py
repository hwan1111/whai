"""전체 테이블 데이터 범위 및 누락일 확인"""
import os, sys, pymysql
sys.stdout.reconfigure(encoding="utf-8")
from dotenv import load_dotenv
from pathlib import Path
import boto3

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env", override=True)

conn = pymysql.connect(
    host="mysql-12676458-whai.b.aivencloud.com", port=16935, db="whai_service",
    user=os.environ["BACKEND_DB_USER"], password=os.environ["BACKEND_DB_PASSWORD"],
    charset="utf8mb4", ssl={"ca": str(ROOT / "config" / "certs" / "ca.pem")},
    cursorclass=pymysql.cursors.DictCursor,
)

print("=" * 65)
print("DB 테이블 데이터 현황")
print("=" * 65)

with conn.cursor() as cur:
    # 1. price 테이블 - 종목별
    print("\n[1] price 테이블 (주가)")
    cur.execute("""
        SELECT ticker,
               COUNT(*)          AS cnt,
               MIN(date)         AS first,
               MAX(date)         AS last
        FROM price
        GROUP BY ticker
        ORDER BY ticker
    """)
    rows = cur.fetchall()
    print(f"  {'ticker':<10} {'cnt':>5}  {'first':<12} {'last':<12}")
    print("  " + "-" * 42)
    for r in rows:
        print(f"  {r['ticker']:<10} {r['cnt']:>5}  {str(r['first']):<12} {str(r['last']):<12}")

    # 2. fundamental 테이블
    print("\n[2] fundamental 테이블")
    cur.execute("""
        SELECT ticker,
               COUNT(*)  AS cnt,
               MIN(date) AS first,
               MAX(date) AS last
        FROM fundamental
        GROUP BY ticker
        ORDER BY ticker
    """)
    rows = cur.fetchall()
    if rows:
        print(f"  {'ticker':<10} {'cnt':>5}  {'first':<12} {'last':<12}")
        print("  " + "-" * 42)
        for r in rows:
            print(f"  {r['ticker']:<10} {r['cnt']:>5}  {str(r['first']):<12} {str(r['last']):<12}")
    else:
        print("  (데이터 없음)")

    # 3. exchange_rate 또는 유사 테이블
    print("\n[3] 기타 테이블 목록")
    cur.execute("SHOW TABLES")
    tables = [list(r.values())[0] for r in cur.fetchall()]
    print("  ", tables)

    # exchange_rate 테이블 확인
    for tbl in ["exchange_rate", "kospi", "index_price", "market_index"]:
        if tbl in tables:
            cur.execute(f"SELECT COUNT(*) as cnt, MIN(date) as first, MAX(date) as last FROM `{tbl}`")
            r = cur.fetchone()
            print(f"\n[{tbl}]  cnt={r['cnt']}  {r['first']} ~ {r['last']}")

conn.close()

# S3 raw 뉴스
print("\n" + "=" * 65)
print("S3 raw 뉴스 현황")
print("=" * 65)
s3 = boto3.client("s3")
BUCKET = "fisa-news-archive"
for prefix in ["preprocessed/USD_KRW", "preprocessed/KOSPI200"]:
    pag = s3.get_paginator("list_objects_v2")
    keys = []
    for page in pag.paginate(Bucket=BUCKET, Prefix=prefix):
        keys.extend(obj["Key"] for obj in page.get("Contents", []))
    if keys:
        keys.sort()
        print(f"  {prefix:<30} {len(keys):>5}개  {keys[0].split('/')[-1]} ~ {keys[-1].split('/')[-1]}")

# 종목 뉴스 샘플링 (첫번째 종목만)
for ticker in ["005930", "000660", "005380"]:
    pag = s3.get_paginator("list_objects_v2")
    keys = []
    for page in pag.paginate(Bucket=BUCKET, Prefix=f"preprocessed/{ticker}"):
        keys.extend(obj["Key"] for obj in page.get("Contents", []))
    if keys:
        keys.sort()
        print(f"  preprocessed/{ticker:<20} {len(keys):>5}개  {keys[0].split('/')[-1]} ~ {keys[-1].split('/')[-1]}")

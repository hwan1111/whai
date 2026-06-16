"""
최근 15일 regime 겹침(overlap) 진단 스크립트

실행:
    python script/others/check_regime_overlaps.py
    python script/others/check_regime_overlaps.py --days 30   # 기간 변경
"""

import argparse
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse

import pymysql
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env", override=True)

_CA_CANDIDATES = [
    Path("/opt/certs/ca.pem"),
    ROOT / "config" / "certs" / "ca.pem",
]
CA_PATH = next((str(p) for p in _CA_CANDIDATES if p.exists()), str(_CA_CANDIDATES[-1]))


def get_conn():
    raw = os.environ["SERVICE_DATABASE_URL"]
    url = urlparse(raw.replace("mysql+pymysql://", "mysql://", 1).split("?")[0])
    return pymysql.connect(
        host=url.hostname, port=url.port or 3306,
        db=url.path.lstrip("/"), user=url.username, password=url.password,
        charset="utf8mb4", ssl={"ca": CA_PATH},
        cursorclass=pymysql.cursors.DictCursor, autocommit=True,
    )


def check(days: int = 15):
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    conn = get_conn()
    with conn.cursor() as cur:
        # 최근 N일 기준으로 겹치는 국면 쌍 조회
        cur.execute("""
            SELECT
                a.ticker,
                a.id        AS id_a,  a.regime_id AS rid_a,
                a.start_date AS s_a,  a.end_date  AS e_a,  a.direction AS dir_a,
                b.id        AS id_b,  b.regime_id AS rid_b,
                b.start_date AS s_b,  b.end_date  AS e_b,  b.direction AS dir_b
            FROM regime a
            JOIN regime b
              ON a.ticker = b.ticker
             AND a.id < b.id
             AND a.end_date >= b.start_date   -- 날짜 범위 겹침 조건
             AND a.start_date <= b.end_date  -- 양방향 체크 필수
             AND b.start_date >= %s           -- 최근 N일 이내
            ORDER BY a.ticker, a.start_date
        """, (cutoff,))
        overlaps = cur.fetchall()

        # 전체 ticker 별 총 건수
        cur.execute("""
            SELECT ticker, COUNT(*) as cnt
            FROM regime
            WHERE end_date >= %s
            GROUP BY ticker
            ORDER BY ticker
        """, (cutoff,))
        counts = cur.fetchall()

    conn.close()

    print(f"\n{'='*60}")
    print(f"  최근 {days}일 (기준: {cutoff}) regime 현황")
    print(f"{'='*60}")
    print(f"\n[ticker별 국면 건수]")
    for r in counts:
        print(f"  {r['ticker']:>8}  {r['cnt']}건")

    print(f"\n[겹치는 국면 쌍: {len(overlaps)}건]")
    if not overlaps:
        print("  겹침 없음 ✓")
    else:
        prev_ticker = None
        for r in overlaps:
            if r["ticker"] != prev_ticker:
                print(f"\n  ── {r['ticker']} ──")
                prev_ticker = r["ticker"]
            print(
                f"  A) id={r['id_a']} rid={r['rid_a']}  {r['s_a']}~{r['e_a']}  {r['dir_a']}"
            )
            print(
                f"  B) id={r['id_b']} rid={r['rid_b']}  {r['s_b']}~{r['e_b']}  {r['dir_b']}"
                f"  ← 더 나중에 삽입됨\n"
            )

    return overlaps


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=15)
    args = parser.parse_args()
    check(args.days)

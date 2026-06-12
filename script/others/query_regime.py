#!/usr/bin/env python3
"""
국면 조회 스크립트: ticker + date 또는 ticker + regime_id 기반

Usage:
    python script/query_regime.py --ticker 005930 --date 2020-01-15
    python script/query_regime.py --ticker 005930 --regime_id 3
"""

import argparse
import os
import sys
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
from urllib.parse import urlparse

import pymysql
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env", override=True)

CA_PATH = str(ROOT / "config" / "certs" / "ca.pem")


def get_conn() -> pymysql.Connection:
    raw_url = os.environ["SERVICE_DATABASE_URL"]
    # strip driver prefix (mysql+pymysql:// → mysql://) for urlparse
    url = urlparse(raw_url.replace("mysql+pymysql://", "mysql://", 1).split("?")[0])
    return pymysql.connect(
        host=url.hostname,
        port=url.port or 3306,
        db=url.path.lstrip("/"),
        user=url.username,
        password=url.password,
        charset="utf8mb4",
        ssl={"ca": CA_PATH},
        cursorclass=pymysql.cursors.DictCursor,
    )


def query_by_date(cur, ticker: str, date: str) -> dict | None:
    cur.execute(
        """
        SELECT r.*, rs.cause, rs.vol_insight, rs.confidence,
               rs.reasoning, rs.tokens_out,
               rs.coverage, rs.novelty, rs.sem_max, rs.sem_mean
        FROM regime r
        LEFT JOIN regime_summary rs ON rs.regime_pk = r.id
        WHERE r.ticker = %s
          AND r.start_date <= %s
          AND r.end_date   >= %s
        LIMIT 1
        """,
        (ticker, date, date),
    )
    return cur.fetchone()


def query_by_regime_id(cur, ticker: str, regime_id: int) -> dict | None:
    cur.execute(
        """
        SELECT r.*, rs.cause, rs.vol_insight, rs.confidence,
               rs.reasoning, rs.tokens_out,
               rs.coverage, rs.novelty, rs.sem_max, rs.sem_mean
        FROM regime r
        LEFT JOIN regime_summary rs ON rs.regime_pk = r.id
        WHERE r.ticker = %s AND r.regime_id = %s
        LIMIT 1
        """,
        (ticker, regime_id),
    )
    return cur.fetchone()


def print_result(row: dict) -> None:
    sep = "=" * 60
    print(sep)
    print(f"  [{row['ticker']}]  국면 #{row['regime_id']}")
    print(sep)

    dir_sym = "▲" if row.get("direction") == "상승" else "▼"
    cum = row.get("cum_return")
    cum_str = f"{cum:+.1%}" if cum is not None else "N/A"
    print(f"  기간     : {row['start_date']} ~ {row['end_date']}  ({row.get('days', '?')}일)")
    print(f"  방향     : {dir_sym} {row.get('direction', 'N/A')}  ({cum_str})")
    print(f"  거래량   : {row.get('vol_trend', 'N/A')}")
    print(f"  뉴스수   : {row.get('news_count', 'N/A')}건  |  입력토큰: {row.get('tokens_in', 'N/A')}")
    print()

    print("── LLM 요약 " + "─" * 48)
    print(f"  신뢰도   : {row.get('confidence', 'N/A')}")
    print()
    print(f"  [원인]\n  {row.get('cause') or '없음'}")
    print()
    print(f"  [거래량 인사이트]\n  {row.get('vol_insight') or '없음'}")
    print()
    print(f"  [종합 추론]\n  {row.get('reasoning') or '없음'}")
    print()

    cov  = row.get("coverage")
    nov  = row.get("novelty")
    smax = row.get("sem_max")
    smn  = row.get("sem_mean")
    print("── 평가 지표 " + "─" * 47)
    print(f"  Coverage : {cov:.4f}" if cov is not None else "  Coverage : N/A")
    print(f"  Novelty  : {nov:.4f}" if nov is not None else "  Novelty  : N/A")
    print(f"  Sem-Max  : {smax:.4f}" if smax is not None else "  Sem-Max  : N/A")
    print(f"  Sem-Mean : {smn:.4f}" if smn is not None else "  Sem-Mean : N/A")
    print(sep)


def main() -> None:
    parser = argparse.ArgumentParser(description="국면 + LLM 요약 조회")
    parser.add_argument("--ticker",    required=True, help="종목 코드 (예: 005930)")
    parser.add_argument("--date",      default=None,  help="조회 날짜 YYYY-MM-DD (해당 날짜가 속한 국면)")
    parser.add_argument("--regime_id", default=None,  type=int, help="국면 순번")
    args = parser.parse_args()

    if args.date is None and args.regime_id is None:
        parser.error("--date 또는 --regime_id 중 하나는 반드시 지정해야 합니다.")

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            if args.regime_id is not None:
                row = query_by_regime_id(cur, args.ticker, args.regime_id)
                label = f"regime_id={args.regime_id}"
            else:
                row = query_by_date(cur, args.ticker, args.date)
                label = f"date={args.date}"

            if row is None:
                print(f"결과 없음: ticker={args.ticker}, {label}")
                sys.exit(1)

            print_result(row)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
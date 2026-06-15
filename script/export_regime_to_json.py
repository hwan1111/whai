"""
DB의 regime + regime_summary 데이터를 regime_news_summary_{ticker}.json 형식으로 export

Usage:
    python script/export_regime_to_json.py --ticker 000000
    python script/export_regime_to_json.py --ticker 000000 --dry-run
"""

import argparse
import json
import logging
import os
import sys
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

import pymysql
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env", override=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

CA_PATH = str(ROOT / "config" / "certs" / "ca.pem")


def get_conn() -> pymysql.Connection:
    return pymysql.connect(
        host="mysql-12676458-whai.b.aivencloud.com",
        port=16935,
        db="whai_service",
        user=os.environ["BACKEND_DB_USER"],
        password=os.environ["BACKEND_DB_PASSWORD"],
        charset="utf8mb4",
        ssl={"ca": CA_PATH},
        cursorclass=pymysql.cursors.DictCursor,
    )


def export(ticker_code: str, dry_run: bool = False) -> None:
    output_path = ROOT / "data" / ticker_code / f"regime_news_summary_{ticker_code}.json"

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    r.regime_id,
                    DATE_FORMAT(r.start_date, '%%Y-%%m-%%d') AS start,
                    DATE_FORMAT(r.end_date,   '%%Y-%%m-%%d') AS end,
                    r.days,
                    r.direction,
                    r.cum_return,
                    r.vol_trend,
                    r.news_count,
                    r.tokens_in,
                    COALESCE(rs.tokens_out, 0)   AS tokens_out,
                    COALESCE(rs.cause, '')        AS cause,
                    COALESCE(rs.vol_insight, '')  AS vol_insight,
                    COALESCE(rs.confidence, '')   AS confidence,
                    COALESCE(rs.reasoning, '')    AS reasoning
                FROM regime r
                LEFT JOIN regime_summary rs ON r.id = rs.regime_pk
                WHERE r.ticker = %s
                ORDER BY r.start_date, r.regime_id
            """, (ticker_code,))
            rows = cur.fetchall()

    finally:
        conn.close()

    if not rows:
        log.error(f"DB에 {ticker_code} 데이터 없음")
        sys.exit(1)

    records = []
    for row in rows:
        start = str(row["start"])
        end   = str(row["end"])
        records.append({
            "regime_id":   row["regime_id"],
            "regime_key":  f"{start}_{end}",
            "start":       start,
            "end":         end,
            "days":        row["days"],
            "direction":   row["direction"],
            "cum_return":  float(row["cum_return"]) if row["cum_return"] is not None else 0.0,
            "vol_trend":   row["vol_trend"] or "",
            "news_count":  row["news_count"] or 0,
            "tokens_in":   row["tokens_in"] or 0,
            "tokens_out":  row["tokens_out"] or 0,
            "llm_analysis": {
                "cause":       row["cause"],
                "evidence":    [],
                "vol_insight": row["vol_insight"],
                "confidence":  row["confidence"],
                "reasoning":   row["reasoning"],
            },
        })

    log.info(f"DB에서 {len(records)}건 추출 ({ticker_code})")

    if dry_run:
        log.info("[DRY] 저장 생략")
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"저장: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DB regime → JSON export")
    parser.add_argument("--ticker",  required=True, help="종목 코드 (예: 000000)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    export(ticker_code=args.ticker, dry_run=args.dry_run)

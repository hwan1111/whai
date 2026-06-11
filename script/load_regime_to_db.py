"""
regime_news_summary_{ticker}.json → MySQL regime + regime_summary 테이블 업로드

Usage:
    python script/load_regime_to_db.py --ticker 105560
    python script/load_regime_to_db.py --ticker 055550
    python script/load_regime_to_db.py --ticker 105560 --dry-run
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
load_dotenv(ROOT / ".env.local", override=True)

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


def load(ticker_code: str, dry_run: bool = False, since: str | None = None,
         auto_since: bool = False) -> None:
    json_path = ROOT / "data" / ticker_code / f"regime_news_summary_{ticker_code}.json"
    if not json_path.exists():
        log.error(f"JSON 파일 없음: {json_path}")
        sys.exit(1)

    records = json.loads(json_path.read_text(encoding="utf-8"))
    log.info(f"JSON 로드: {len(records)}건  ({json_path})")

    # --auto-since: JSON 첫 레코드의 start_date를 since로 자동 사용
    if auto_since and not since and records:
        since = min(r["start"] for r in records)
        log.info(f"auto-since: {since} (JSON 최초 start_date 기준)")

    conn = get_conn()
    try:
        # since 지정 시: 해당 날짜 이후 regime 삭제 후 재삽입
        if since:
            if dry_run:
                log.info(f"[DRY] DELETE regime WHERE ticker={ticker_code} AND start_date >= {since}")
            else:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM regime WHERE ticker = %s AND start_date >= %s",
                        (ticker_code, since),
                    )
                    deleted = cur.rowcount
                conn.commit()
                log.info(f"DELETE 완료: {deleted}건 (start_date >= {since})")

        with conn.cursor() as cur:
            # 현재 DB에 있는 (start_date, end_date) 집합 조회 — 중복 방지
            cur.execute(
                "SELECT start_date, end_date FROM regime WHERE ticker = %s",
                (ticker_code,),
            )
            existing = {(str(r["start_date"]), str(r["end_date"])) for r in cur.fetchall()}
            log.info(f"DB 기존 국면: {len(existing)}건")

            # 현재 DB 최대 regime_id 조회
            cur.execute(
                "SELECT COALESCE(MAX(regime_id), 0) AS max_id FROM regime WHERE ticker = %s",
                (ticker_code,),
            )
            max_regime_id = cur.fetchone()["max_id"]
            log.info(f"현재 최대 regime_id: {max_regime_id}")

        inserted = skipped = 0
        for rec in records:
            start = rec["start"]
            end   = rec["end"]

            if (start, end) in existing:
                skipped += 1
                continue

            analysis   = rec.get("llm_analysis", {})
            max_regime_id += 1

            if dry_run:
                log.info(f"  [DRY] 삽입 예정: regime_id={max_regime_id}  {start}~{end}  {rec['direction']}")
                inserted += 1
                continue

            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO regime
                        (ticker, regime_id, start_date, end_date, days, direction,
                         cum_return, vol_trend, news_count, tokens_in, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    """,
                    (
                        ticker_code,
                        max_regime_id,
                        start,
                        end,
                        rec["days"],
                        rec["direction"],
                        rec["cum_return"],
                        rec["vol_trend"],
                        rec["news_count"],
                        rec.get("tokens_in", 0),
                    ),
                )
                regime_pk = cur.lastrowid

                cur.execute(
                    """
                    INSERT INTO regime_summary
                        (regime_pk, cause, vol_insight, confidence, reasoning,
                         tokens_out, coverage, novelty, sem_max, sem_mean, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, NULL, NULL, NULL, NULL, NOW())
                    """,
                    (
                        regime_pk,
                        analysis.get("cause", ""),
                        analysis.get("vol_insight", ""),
                        analysis.get("confidence", ""),
                        analysis.get("reasoning", ""),
                        rec.get("tokens_out", 0),
                    ),
                )
            conn.commit()
            log.info(f"  삽입: regime_id={max_regime_id}  {start}~{end}  {rec['direction']}")
            inserted += 1

        log.info(f"완료 — 삽입: {inserted}건  스킵(중복): {skipped}건")

    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="JSON → MySQL regime/regime_summary 업로드")
    parser.add_argument("--ticker",     required=True, help="종목 코드 (예: 105560)")
    parser.add_argument("--dry-run",    action="store_true", help="실제 DB 변경 없이 시뮬레이션")
    parser.add_argument("--since",      default=None, help="이 날짜 이후 regime 삭제 후 재삽입 YYYY-MM-DD")
    parser.add_argument("--auto-since", action="store_true",
                        help="JSON 최초 start_date를 --since로 자동 사용 (마지막 국면 재처리)")
    args = parser.parse_args()
    load(ticker_code=args.ticker, dry_run=args.dry_run, since=args.since,
         auto_since=args.auto_since)

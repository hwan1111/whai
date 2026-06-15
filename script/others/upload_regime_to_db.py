"""
국면 요약 DB 업로드 스크립트

regime_news_summary_{ticker}.json + eval_regime_summary_{ticker}.json 을 읽어
Aiven MySQL의 regime / regime_summary 테이블에 업로드한다.

사전 조건:
  - company 테이블에 해당 ticker가 등록되어 있어야 함 (FK 제약)
  - regime_news_summary_{ticker}.json 이 존재해야 함
  - eval_regime_summary_{ticker}.json 은 없어도 동작 (eval 컬럼 NULL 처리)

실행:
    python script/upload_regime_to_db.py --ticker 005930
    python script/upload_regime_to_db.py --ticker 000660
    python script/upload_regime_to_db.py --ticker 005930 --mode replace  # 기존 데이터 덮어쓰기
    python script/upload_regime_to_db.py --ticker 005930 --dry-run        # DB 반영 없이 확인만
"""

import argparse
import json
import sys
import os
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
from urllib.parse import urlparse

import pymysql
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / ".env", override=True)

_CA_CANDIDATES = [
    Path("/opt/certs/ca.pem"),              # Airflow container
    ROOT / "config" / "certs" / "ca.pem",  # local dev
]
CA_PATH = next((str(p) for p in _CA_CANDIDATES if p.exists()), str(_CA_CANDIDATES[-1]))


# ── DB 연결 ───────────────────────────────────────────────────────────

def get_conn() -> pymysql.Connection:
    raw_url = os.environ["SERVICE_DATABASE_URL"]
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
        autocommit=False,
    )


# ── 데이터 로드 ───────────────────────────────────────────────────────

def load_summaries(ticker: str) -> list[dict]:
    path = ROOT / "data" / ticker / f"regime_news_summary_{ticker}.json"
    if not path.exists():
        raise FileNotFoundError(f"요약 파일 없음: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_eval(ticker: str) -> dict[int, dict]:
    path = ROOT / "data" / ticker / f"eval_regime_summary_{ticker}.json"
    if not path.exists():
        print(f"  [경고] eval 파일 없음 — coverage/sem 컬럼 NULL로 처리: {path}")
        return {}
    records = json.loads(path.read_text(encoding="utf-8"))
    return {r["regime_id"]: r for r in records}


# ── 사전 검증 ─────────────────────────────────────────────────────────

def check_company(cur, ticker: str) -> bool:
    cur.execute("SELECT ticker FROM asset WHERE ticker = %s", (ticker,))
    return cur.fetchone() is not None


def count_existing(cur, ticker: str) -> int:
    cur.execute("SELECT COUNT(*) as cnt FROM regime WHERE ticker = %s", (ticker,))
    return cur.fetchone()["cnt"]


# ── INSERT ───────────────────────────────────────────────────────────

INSERT_REGIME = """
INSERT INTO regime
    (ticker, regime_id, start_date, end_date, days, direction,
     cum_return, vol_trend, news_count, tokens_in)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

UPDATE_REGIME = """
INSERT INTO regime
    (ticker, regime_id, start_date, end_date, days, direction,
     cum_return, vol_trend, news_count, tokens_in)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    start_date  = VALUES(start_date),
    end_date    = VALUES(end_date),
    days        = VALUES(days),
    direction   = VALUES(direction),
    cum_return  = VALUES(cum_return),
    vol_trend   = VALUES(vol_trend),
    news_count  = VALUES(news_count),
    tokens_in   = VALUES(tokens_in)
"""

INSERT_SUMMARY = """
INSERT INTO regime_summary
    (regime_pk, cause, vol_insight, confidence, reasoning, tokens_out,
     coverage, novelty, sem_max, sem_mean)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

UPDATE_SUMMARY = """
INSERT INTO regime_summary
    (regime_pk, cause, vol_insight, confidence, reasoning, tokens_out,
     coverage, novelty, sem_max, sem_mean)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    cause       = VALUES(cause),
    vol_insight = VALUES(vol_insight),
    confidence  = VALUES(confidence),
    reasoning   = VALUES(reasoning),
    tokens_out  = VALUES(tokens_out),
    coverage    = VALUES(coverage),
    novelty     = VALUES(novelty),
    sem_max     = VALUES(sem_max),
    sem_mean    = VALUES(sem_mean)
"""

# append 모드: 이미 존재하는 행은 건드리지 않고 신규 행만 INSERT
APPEND_REGIME = """
INSERT IGNORE INTO regime
    (ticker, regime_id, start_date, end_date, days, direction,
     cum_return, vol_trend, news_count, tokens_in)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

APPEND_SUMMARY = """
INSERT IGNORE INTO regime_summary
    (regime_pk, cause, vol_insight, confidence, reasoning, tokens_out,
     coverage, novelty, sem_max, sem_mean)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


_S3_BUCKET    = "fisa-news-archive"
_S3_PROCESSED = "processed"


def _cleanup_local(ticker: str) -> None:
    import boto3
    s3 = boto3.client("s3")

    summary_path = ROOT / "data" / ticker / f"regime_news_summary_{ticker}.json"
    eval_path    = ROOT / "data" / ticker / f"eval_regime_summary_{ticker}.json"

    if summary_path.exists():
        s3_key = f"{_S3_PROCESSED}/{ticker}/regime_news_summary_{ticker}.json"
        s3.put_object(
            Bucket=_S3_BUCKET, Key=s3_key,
            Body=summary_path.read_bytes(),
            ContentType="application/json; charset=utf-8",
        )
        print(f"  [cleanup] S3 backup: {s3_key}")
        summary_path.unlink()
        print(f"  [cleanup] 삭제: {summary_path}")

    if eval_path.exists():
        eval_path.unlink()
        print(f"  [cleanup] 삭제: {eval_path}")


def upload(ticker: str, mode: str = "skip", dry_run: bool = False,
           skip_company_check: bool = False, db_ticker: str | None = None,
           cleanup: bool = True) -> None:
    """
    mode:
      skip    - 이미 존재하는 ticker 국면이 하나라도 있으면 전체 건너뜀 (기본)
      replace - ON DUPLICATE KEY UPDATE 로 전체 덮어쓰기
      append  - 이미 존재하는 행은 유지, 신규 행만 INSERT (DAG 증분 적재용)

    db_ticker:
      파일 경로 조회는 ticker 로, DB INSERT는 db_ticker 로 수행 (예: KOSPI200 파일 → 000000 행)

    cleanup:
      True(기본) — DB 적재 성공 후 로컬 JSON 파일 삭제
    """
    db_ticker = db_ticker or ticker

    summaries = load_summaries(ticker)
    eval_map  = load_eval(ticker)

    print(f"\n{'='*55}")
    print(f"  ticker: {ticker}  db_ticker: {db_ticker}  국면: {len(summaries)}건  mode: {mode}")
    print(f"{'='*55}")

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # asset FK 확인
            if not skip_company_check and not check_company(cur, db_ticker):
                print(f"  [오류] asset 테이블에 ticker={db_ticker} 없음 — 업로드 중단")
                print(f"         asset 테이블에 먼저 등록하거나 --skip-company-check 사용하세요.")
                return

            existing = count_existing(cur, db_ticker)
            if existing > 0 and mode == "skip":
                print(f"  [스킵] 이미 {existing}건 존재 (--mode replace 또는 append 로 변경 가능)")
                return

            if mode == "replace":
                regime_sql, summary_sql = UPDATE_REGIME, UPDATE_SUMMARY
            elif mode == "append":
                regime_sql, summary_sql = APPEND_REGIME, APPEND_SUMMARY
            else:
                regime_sql, summary_sql = INSERT_REGIME, INSERT_SUMMARY

            inserted_regime  = 0
            inserted_summary = 0

            for rec in summaries:
                rid       = rec["regime_id"]
                llm       = rec.get("llm_analysis", {})
                ev        = eval_map.get(rid, {})

                regime_params = (
                    db_ticker,
                    rid,
                    rec["start"],
                    rec["end"],
                    rec.get("days"),
                    rec.get("direction"),
                    rec.get("cum_return"),
                    rec.get("vol_trend"),
                    rec.get("news_count"),
                    rec.get("tokens_in"),
                )

                if dry_run:
                    print(f"  [DRY] regime  #{rid}  {rec['start']}~{rec['end']}  {rec.get('direction')}")
                    continue

                cur.execute(regime_sql, regime_params)

                # replace/append 모드: lastrowid가 0이면 기존 행 id 조회
                regime_pk = cur.lastrowid
                if not regime_pk:
                    cur.execute(
                        "SELECT id FROM regime WHERE ticker=%s AND regime_id=%s",
                        (db_ticker, rid)
                    )
                    row = cur.fetchone()
                    regime_pk = row["id"] if row else None

                if not regime_pk:
                    print(f"  [경고] regime_pk 획득 실패 — #{rid} summary 스킵")
                    continue

                inserted_regime += 1

                summary_params = (
                    regime_pk,
                    llm.get("cause"),
                    llm.get("vol_insight"),
                    llm.get("confidence"),
                    llm.get("reasoning"),
                    rec.get("tokens_out"),
                    ev.get("coverage"),
                    ev.get("novelty"),
                    ev.get("sem_max"),
                    ev.get("sem_mean"),
                )
                cur.execute(summary_sql, summary_params)
                inserted_summary += 1

            conn.commit()

        if dry_run:
            print(f"\n  [DRY-RUN] 실제 DB 반영 없음")
            return

        # 결과 검증
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) as cnt FROM regime WHERE ticker=%s", (db_ticker,))
            regime_cnt = cur.fetchone()["cnt"]
            cur.execute(
                "SELECT COUNT(*) as cnt FROM regime_summary rs "
                "JOIN regime r ON rs.regime_pk=r.id WHERE r.ticker=%s",
                (db_ticker,)
            )
            summary_cnt = cur.fetchone()["cnt"]

        print(f"\n  regime 입력:         {inserted_regime}건")
        print(f"  regime_summary 입력: {inserted_summary}건")
        print(f"  DB 확인 — regime: {regime_cnt}건  regime_summary: {summary_cnt}건")

        # 샘플 출력
        with conn.cursor() as cur:
            cur.execute(
                "SELECT r.regime_id, r.start_date, r.end_date, r.direction, r.cum_return, "
                "       rs.confidence, rs.coverage, rs.sem_mean "
                "FROM regime r JOIN regime_summary rs ON rs.regime_pk=r.id "
                "WHERE r.ticker=%s ORDER BY r.regime_id LIMIT 3",
                (db_ticker,)
            )
            rows = cur.fetchall()

        print(f"\n  [샘플 3건]")
        for row in rows:
            print(
                f"  #{row['regime_id']:>3}  {row['start_date']}~{row['end_date']}"
                f"  {row['direction']}  {row['cum_return']:+.1%}"
                f"  conf={row['confidence']}  cov={row['coverage']}  sem={row['sem_mean']}"
            )

        if cleanup and not dry_run:
            _cleanup_local(ticker)

    finally:
        conn.close()


if __name__ == "__main__":
    AVAILABLE = ["005930", "000660", "005380", "000270", "079550",
                 "051910", "096770", "055550", "105560", "012450", "KOSPI200", "USD_KRW"]

    parser = argparse.ArgumentParser(description="국면 요약 Aiven DB 업로드")
    parser.add_argument(
        "--ticker", required=True, choices=AVAILABLE,
        help=f"종목 코드 ({', '.join(AVAILABLE)})",
    )
    parser.add_argument(
        "--mode", choices=["skip", "replace", "append"], default="skip",
        help="skip=기존 데이터 전체 유지(기본)  replace=덮어쓰기  append=신규만 INSERT",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="DB 반영 없이 처리 대상만 확인",
    )
    parser.add_argument(
        "--skip-company-check", action="store_true",
        help="asset 테이블 FK 확인 생략",
    )
    parser.add_argument(
        "--db-ticker", default=None,
        help="DB에 저장할 ticker 코드 (파일과 다를 때 사용, 예: --ticker KOSPI200 --db-ticker 000000)",
    )
    parser.add_argument(
        "--no-cleanup", action="store_true",
        help="DB 적재 후 로컬 JSON 파일 유지 (기본: 적재 성공 후 삭제)",
    )
    parser.add_argument(
        "--cleanup-only", action="store_true",
        help="DB 적재 없이 로컬 JSON 파일 S3 백업 + 삭제만 수행 (skip 경로용)",
    )
    args = parser.parse_args()

    if args.cleanup_only:
        _cleanup_local(args.ticker)
    else:
        upload(
            ticker=args.ticker,
            mode=args.mode,
            dry_run=args.dry_run,
            skip_company_check=args.skip_company_check,
            db_ticker=args.db_ticker,
            cleanup=not args.no_cleanup,
        )

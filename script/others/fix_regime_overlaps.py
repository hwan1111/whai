"""
겹치는 regime 정리 스크립트

전략: 열린 국면(open regime)은 매일 시작점부터 재분석되므로
      B = 오늘 재분석된 최신 버전, A = 어제의 구버전
      → A(구버전)를 삭제하고 B(최신버전)로 교체

실행:
    python script/others/fix_regime_overlaps.py --dry-run   # 확인만
    python script/others/fix_regime_overlaps.py             # 실제 반영
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
        cursorclass=pymysql.cursors.DictCursor, autocommit=False,
    )


def fix(dry_run: bool = False):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # 겹치는 모든 쌍 조회 (전체 기간)
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
                 AND a.end_date >= b.start_date
                ORDER BY a.ticker, a.start_date
            """)
            overlaps = cur.fetchall()

        if not overlaps:
            print("겹치는 국면 없음 ✓")
            return

        print(f"겹치는 쌍: {len(overlaps)}건\n")

        # A가 여러 B와 겹칠 수 있으므로 중복 제거 (가장 오래된 버전들만 삭제)
        to_delete_ids = list({r["id_a"] for r in overlaps})
        to_delete_summary_ids: list[int] = []

        with conn.cursor() as cur:
            # 삭제 대상 상세 출력
            for r in overlaps:
                print(
                    f"  [{r['ticker']}] 삭제(구버전) id={r['id_a']} rid={r['rid_a']}  "
                    f"{r['s_a']}~{r['e_a']} ({r['dir_a']})"
                )
                print(
                    f"    → 유지(최신버전) id={r['id_b']} rid={r['rid_b']}  "
                    f"{r['s_b']}~{r['e_b']} ({r['dir_b']})\n"
                )

            if not dry_run:
                placeholders = ",".join(["%s"] * len(to_delete_ids))

                # regime_summary 먼저 삭제 (FK 제약)
                cur.execute(
                    f"DELETE FROM regime_summary WHERE regime_pk IN ({placeholders})",
                    to_delete_ids,
                )
                deleted_summaries = cur.rowcount

                # regime 삭제
                cur.execute(
                    f"DELETE FROM regime WHERE id IN ({placeholders})",
                    to_delete_ids,
                )
                deleted_regimes = cur.rowcount

        if not dry_run:
            conn.commit()
            print(f"완료 — regime {deleted_regimes}건 / regime_summary {deleted_summaries}건 삭제")
        else:
            print(f"[DRY-RUN] 실제 반영 없음. 삭제 대상 id: {to_delete_ids}")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="실제 DB 변경 없이 확인만")
    args = parser.parse_args()
    fix(dry_run=args.dry_run)

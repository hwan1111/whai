"""
regime_news_summary_{ticker}.json + eval_regime_summary_{ticker}.json
→ MySQL regime / regime_summary 테이블 업로드

실행:
    python script/upload_regime_to_mysql.py --ticker 105560
    python script/upload_regime_to_mysql.py --ticker 055550
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env", override=True)
sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

CA_PATH = str(ROOT / "config" / "certs" / "ca.pem")


def get_engine():
    raw_url = os.environ["SERVICE_DATABASE_URL"]
    if "ssl_ca=" in raw_url:
        base_url = raw_url.split("?")[0]
        url = f"{base_url}?charset=utf8mb4"
        connect_args = {"ssl": {"ca": CA_PATH}}
    else:
        url = raw_url
        connect_args = {}
    return create_engine(url, connect_args=connect_args, pool_pre_ping=True)


def load_json(path: Path) -> list[dict]:
    if not path.exists():
        log.warning(f"파일 없음: {path}")
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def upload(ticker: str) -> None:
    summary_path = ROOT / f"data/{ticker}/regime_news_summary_{ticker}.json"
    eval_path    = ROOT / f"data/{ticker}/eval_regime_summary_{ticker}.json"

    summary_data = load_json(summary_path)
    eval_data    = load_json(eval_path)

    if not summary_data:
        log.error(f"regime_news_summary_{ticker}.json 없음 — 중단")
        return

    eval_map = {r["regime_id"]: r for r in eval_data}

    engine = get_engine()
    inserted_regime = 0
    inserted_summary = 0
    skipped = 0

    with engine.begin() as conn:
        for row in summary_data:
            regime_id = row["regime_id"]
            llm = row.get("llm_analysis", {})
            ev  = eval_map.get(regime_id, {})

            # ── regime 테이블 ──────────────────────────────────────────
            existing = conn.execute(
                text("SELECT id FROM regime WHERE ticker=:t AND regime_id=:r"),
                {"t": ticker, "r": regime_id},
            ).fetchone()

            if existing:
                regime_pk = existing[0]
                skipped += 1
            else:
                result = conn.execute(
                    text("""
                        INSERT INTO regime
                            (ticker, regime_id, start_date, end_date, days,
                             direction, cum_return, vol_trend, news_count, tokens_in)
                        VALUES
                            (:ticker, :regime_id, :start_date, :end_date, :days,
                             :direction, :cum_return, :vol_trend, :news_count, :tokens_in)
                    """),
                    {
                        "ticker":     ticker,
                        "regime_id":  regime_id,
                        "start_date": row["start"],
                        "end_date":   row["end"],
                        "days":       row.get("days"),
                        "direction":  row.get("direction"),
                        "cum_return": row.get("cum_return"),
                        "vol_trend":  row.get("vol_trend"),
                        "news_count": row.get("news_count"),
                        "tokens_in":  row.get("tokens_in"),
                    },
                )
                regime_pk = result.lastrowid
                inserted_regime += 1

            # ── regime_summary 테이블 ──────────────────────────────────
            exists_summary = conn.execute(
                text("SELECT id FROM regime_summary WHERE regime_pk=:pk"),
                {"pk": regime_pk},
            ).fetchone()

            if exists_summary:
                continue

            conn.execute(
                text("""
                    INSERT INTO regime_summary
                        (regime_pk, cause, vol_insight, confidence, reasoning,
                         tokens_out, coverage, novelty, sem_max, sem_mean)
                    VALUES
                        (:regime_pk, :cause, :vol_insight, :confidence, :reasoning,
                         :tokens_out, :coverage, :novelty, :sem_max, :sem_mean)
                """),
                {
                    "regime_pk":  regime_pk,
                    "cause":      llm.get("cause"),
                    "vol_insight":llm.get("vol_insight"),
                    "confidence": llm.get("confidence"),
                    "reasoning":  llm.get("reasoning"),
                    "tokens_out": row.get("tokens_out"),
                    "coverage":   ev.get("coverage"),
                    "novelty":    ev.get("novelty"),
                    "sem_max":    ev.get("sem_max"),
                    "sem_mean":   ev.get("sem_mean"),
                },
            )
            inserted_summary += 1

    log.info(f"[{ticker}] regime 신규: {inserted_regime}건 / 스킵(기존): {skipped}건")
    log.info(f"[{ticker}] regime_summary 신규: {inserted_summary}건")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="regime JSON → MySQL 업로드")
    parser.add_argument("--ticker", required=True, help="종목 코드 (예: 105560)")
    args = parser.parse_args()
    upload(ticker=args.ticker)

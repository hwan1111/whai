#!/usr/bin/env python3
"""
공통 이동 이벤트 평가: ks200_ew 분해 + 요약 품질 지표 통합

기존 eval_regime_summary_{ticker}.json (coverage, sem_max, sem_mean)과
calc_ex_index.py 출력 (beta, r2, total_cum, market_cum, idio_cum)을
common_events_*_ex.json 기준으로 regime_id 매칭하여 통합.

Usage:
    python script/eval_common_events.py
    python script/eval_common_events.py --input data/common_events_005930_005380_ex.json
"""

import argparse
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
_h = logging.StreamHandler()
_h.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
logger.addHandler(_h)
logger.propagate = False

project_root = Path(__file__).parent.parent


def load_eval(ticker: str) -> dict[int, dict]:
    path = project_root / "data" / ticker / f"eval_regime_summary_{ticker}.json"
    if not path.exists():
        logger.warning(f"eval 파일 없음: {path}")
        return {}
    with open(path, encoding="utf-8") as f:
        records = json.load(f)
    return {r["regime_id"]: r for r in records}


def build_ticker_eval(ev_ticker: dict, eval_map: dict[int, dict]) -> dict:
    regime_id = ev_ticker["regime_id"]
    ks200     = ev_ticker.get("ks200_ew", {})
    eval_rec  = eval_map.get(regime_id, {})

    return {
        "regime_id":  regime_id,
        "period":     ev_ticker["period"],
        "direction":  ev_ticker["direction"],
        "cum_return": ev_ticker["cum_return"],
        "cause":      ev_ticker.get("cause"),
        "confidence": ev_ticker.get("confidence"),
        "ks200_ew": {
            "beta":       ks200.get("beta"),
            "r2":         ks200.get("r2"),
            "total_cum":  ks200.get("total_cum"),
            "market_cum": ks200.get("market_cum"),
            "idio_cum":   ks200.get("idio_cum"),
        },
        "eval": {
            "coverage":  eval_rec.get("coverage"),
            "novelty":   eval_rec.get("novelty"),
            "sem_max":   eval_rec.get("sem_max"),
            "sem_mean":  eval_rec.get("sem_mean"),
        },
    }


def print_summary(results: list[dict], tickers: list[str]) -> None:
    logger.info("\n" + "=" * 70)
    logger.info("공통 이벤트 평가 요약")
    logger.info("=" * 70)

    for ticker in tickers:
        cov_vals, sem_vals, r2_vals = [], [], []
        for ev in results:
            t = ev.get(ticker, {})
            if t.get("eval", {}).get("coverage") is not None:
                cov_vals.append(t["eval"]["coverage"])
            if t.get("eval", {}).get("sem_mean") is not None:
                sem_vals.append(t["eval"]["sem_mean"])
            if t.get("ks200_ew", {}).get("r2") is not None:
                r2_vals.append(t["ks200_ew"]["r2"])

        logger.info(f"\n[{ticker}]")
        if cov_vals:
            logger.info(f"  Coverage  평균: {sum(cov_vals)/len(cov_vals):.4f}  범위: {min(cov_vals):.4f}~{max(cov_vals):.4f}")
        if sem_vals:
            logger.info(f"  Sem-Mean  평균: {sum(sem_vals)/len(sem_vals):.4f}  범위: {min(sem_vals):.4f}~{max(sem_vals):.4f}")
        if r2_vals:
            logger.info(f"  R²        평균: {sum(r2_vals)/len(r2_vals):.4f}  범위: {min(r2_vals):.4f}~{max(r2_vals):.4f}")


def main() -> None:
    parser = argparse.ArgumentParser(description="공통 이벤트 통합 평가")
    parser.add_argument(
        "--input",
        default=str(project_root / "data" / "common_events_000660_079550_ex.json"),
        help="common_events_*_ex.json 경로",
    )
    args = parser.parse_args()

    input_path  = Path(args.input)
    output_path = input_path.with_name(input_path.stem + "_eval.json")

    with open(input_path, encoding="utf-8") as f:
        data = json.load(f)

    events  = data["events"]
    tickers = sorted({t for ev in events for t in ev if len(t) == 6 and t.isdigit()})
    logger.info(f"✓ 이벤트: {len(events)}건  종목: {tickers}")

    eval_maps = {ticker: load_eval(ticker) for ticker in tickers}
    missing = {t: sum(1 for ev in events if ev.get(t, {}).get("regime_id") not in eval_maps[t]) for t in tickers}
    for t, n in missing.items():
        if n:
            logger.warning(f"[{t}] eval 미매칭: {n}건")

    enriched = []
    for ev in events:
        rec = {
            "rank":     ev["rank"],
            "date":     ev["date"],
            "relation": ev["relation"],
            "weight":   ev["weight"],
            "gap_days": ev["gap_days"],
        }
        for ticker in tickers:
            if ticker in ev:
                rec[ticker] = build_ticker_eval(ev[ticker], eval_maps[ticker])
        enriched.append(rec)

    output = {**{k: v for k, v in data.items() if k != "events"}, "events": enriched}
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    logger.info(f"✓ 저장 완료: {output_path}")
    print_summary(enriched, tickers)


if __name__ == "__main__":
    main()

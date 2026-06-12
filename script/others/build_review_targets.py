"""
재수집/검토 대상 국면 목록 생성

eval_regime_summary_{ticker}.json + regime_news_summary_{ticker}.json 조인 후
아래 세 조건의 합집합으로 대상을 선별해 JSON 파일로 저장한다.

  · sem_max  < SEM_THRESHOLD   (의미적 유사도 낮음)
  · coverage < COV_THRESHOLD   (원문 근거 비율 낮음)
  · confidence != "high"       (LLM 자기보고 불확실)

참고: sem_max 전체 최솟값 0.832 — SEM_THRESHOLD < 0.832 이면 해당 조건은 0건

출력: data/review_targets_{ticker}.json

실행:
    python script/build_review_targets.py
    python script/build_review_targets.py --ticker 000660
"""

import argparse
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════
# ★ 필터 기준
# ══════════════════════════════════════════════════════════════════════
SEM_THRESHOLD = 0.87   # sem_max   이 이보다 낮으면 대상 (p10 기준 0.8701)
COV_THRESHOLD = 0.70   # coverage  이 이보다 낮으면 대상
REF_THRESHOLD = 650    # ref_tokens 이 이보다 낮으면 대상 (원문 토큰 부족)
# confidence != "high" 는 항상 적용
# ══════════════════════════════════════════════════════════════════════


def run(ticker_code: str = "005930") -> None:
    eval_path  = Path(f"data/{ticker_code}/eval_regime_summary_{ticker_code}.json")
    summ_path  = Path(f"data/{ticker_code}/regime_news_summary_{ticker_code}.json")
    out_path   = Path(f"data/{ticker_code}/review_targets_{ticker_code}.json")

    if not eval_path.exists():
        raise FileNotFoundError(f"{eval_path} 없음 — eval_regime_summary.py 먼저 실행")
    if not summ_path.exists():
        raise FileNotFoundError(f"{summ_path} 없음 — regime_news_summary.py 먼저 실행")

    eval_data: list[dict] = json.loads(eval_path.read_text(encoding="utf-8"))
    summ_data: list[dict] = json.loads(summ_path.read_text(encoding="utf-8"))

    summ_map = {f"{r['start']}_{r['end']}": r for r in summ_data}

    joined: list[dict] = []
    for e in eval_data:
        key = f"{e['start']}_{e['end']}"
        s   = summ_map.get(key, {})
        joined.append({
            **e,
            "confidence":  s.get("llm_analysis", {}).get("confidence", "N/A"),
            "cause":       s.get("llm_analysis", {}).get("cause", ""),
            "tokens_in":   s.get("tokens_in"),
            "tokens_out":  s.get("tokens_out"),
            "news_count":  s.get("news_count"),
        })

    total = len(joined)

    flag_sem  = {r["regime_id"] for r in joined if r["sem_max"]  < SEM_THRESHOLD}
    flag_cov  = {r["regime_id"] for r in joined if r["coverage"] < COV_THRESHOLD}
    flag_ref  = {r["regime_id"] for r in joined if r["ref_tokens"] < REF_THRESHOLD}
    flag_conf = {r["regime_id"] for r in joined if r["confidence"] != "high"}
    union_ids = flag_sem | flag_cov | flag_ref | flag_conf

    log.info(f"전체 국면: {total}건")
    log.info(f"sem_max    < {SEM_THRESHOLD}  : {len(flag_sem)}건")
    log.info(f"coverage   < {COV_THRESHOLD}  : {len(flag_cov)}건")
    log.info(f"ref_tokens < {REF_THRESHOLD}  : {len(flag_ref)}건")
    log.info(f"confidence != high            : {len(flag_conf)}건")
    log.info(f"합집합 대상                   : {len(union_ids)}건")

    targets = []
    for r in sorted(joined, key=lambda x: x["regime_id"]):
        if r["regime_id"] not in union_ids:
            continue

        reasons = []
        if r["regime_id"] in flag_sem:
            reasons.append(f"sem_max={r['sem_max']:.4f}<{SEM_THRESHOLD}")
        if r["regime_id"] in flag_cov:
            reasons.append(f"coverage={r['coverage']:.4f}<{COV_THRESHOLD}")
        if r["regime_id"] in flag_ref:
            reasons.append(f"ref_tokens={r['ref_tokens']}<{REF_THRESHOLD}")
        if r["regime_id"] in flag_conf:
            reasons.append(f"confidence={r['confidence']}")

        targets.append({
            "regime_id":  r["regime_id"],
            "start":      r["start"],
            "end":        r["end"],
            "days":       r["days"],
            "direction":  r["direction"],
            "cum_return": r["cum_return"],
            "vol_trend":  r.get("vol_trend"),
            "news_count": r.get("news_count"),
            "tokens_in":  r.get("tokens_in"),
            "sem_max":    r["sem_max"],
            "sem_mean":   r["sem_mean"],
            "coverage":   r["coverage"],
            "novelty":    r["novelty"],
            "confidence": r["confidence"],
            "cause":      r.get("cause", ""),
            "flags":      reasons,
        })

    print(f"\n{'ID':>5}  {'기간':<23}  {'sem':>6}  {'cov':>6}  {'conf':<7}  {'flags'}")
    print("-" * 90)
    for t in targets:
        print(
            f"  [{t['regime_id']:>3}]  "
            f"{t['start']}~{t['end']}  "
            f"{t['sem_max']:.4f}  "
            f"{t['coverage']:.4f}  "
            f"{t['confidence']:<7}  "
            f"{', '.join(t['flags'])}"
        )

    print(f"\n총 {len(targets)}건 / 전체 {total}건")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({
            "ticker_code":    ticker_code,
            "total_regimes":  total,
            "target_count":   len(targets),
            "thresholds": {
                "sem_max":    SEM_THRESHOLD,
                "coverage":   COV_THRESHOLD,
                "ref_tokens": REF_THRESHOLD,
                "confidence": "!= high",
            },
            "flag_counts": {
                "sem":        len(flag_sem),
                "coverage":   len(flag_cov),
                "ref_tokens": len(flag_ref),
                "confidence": len(flag_conf),
            },
            "targets": targets,
        },
        ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info(f"저장: {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="재검토 대상 국면 목록 생성")
    parser.add_argument("--ticker", default="005930", help="종목 코드 (기본: 005930)")
    args = parser.parse_args()
    run(ticker_code=args.ticker)

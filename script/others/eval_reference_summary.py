#!/usr/bin/env python3
"""
reference JSON 요약본 평가: Claude 모범답안 vs 원문

reference_{ticker}/reference_*.json 의 reference_summary(Claude 생성)를
동일 파일 내 original_news(원문)와 비교하여 coverage, 코사인유사도 계산.

Coverage  : reference_summary 토큰 중 원문에 존재하는 비율
Novelty   : 원문에 없는 토큰 비율
Sem-Max   : reference_summary 임베딩 ↔ 원문 임베딩 코사인 유사도 (최대)
Sem-Mean  : reference_summary 임베딩 ↔ 원문 임베딩 코사인 유사도 (평균)

토크나이저: kiwipiepy 우선 → 정규식 fallback
임베더    : fastembed/intfloat/multilingual-e5-large → sentence-transformers fallback

Usage:
    python script/eval_reference_summary.py
    python script/eval_reference_summary.py --input data/005930/reference_20200501_20200505.json
    python script/eval_reference_summary.py --no-embed
"""

import argparse
import json
import logging
import re
from pathlib import Path

import numpy as np

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
_h = logging.StreamHandler()
_h.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
logger.addHandler(_h)
logger.propagate = False

project_root = Path(__file__).parent.parent
EMBED_MODEL  = "jhgan/ko-sroberta-multitask"


# ── 토크나이저 ────────────────────────────────────────────────────────────────

def _build_tokenizer():
    try:
        from kiwipiepy import Kiwi
        kiwi = Kiwi()
        SKIP = {"SF", "SP", "SS", "SE", "SO", "SW", "SB", "NF", "NV", "XSN"}
        def _tok(text: str) -> list[str]:
            return [t.form for t in kiwi.tokenize(text) if t.tag not in SKIP]
        logger.info("토크나이저: kiwipiepy")
        return _tok
    except ImportError:
        def _tok(text: str) -> list[str]:
            return re.findall(r"[가-힣a-zA-Z0-9]+", text)
        logger.info("토크나이저: 정규식 fallback")
        return _tok


# ── 임베더 ────────────────────────────────────────────────────────────────────

class _FastEmbedWrapper:
    def __init__(self, model):
        self._model = model

    def encode(self, texts: list[str], normalize_embeddings: bool = True,
               show_progress_bar: bool = False) -> np.ndarray:
        vecs = np.array(list(self._model.embed(texts)))
        if normalize_embeddings:
            norms = np.linalg.norm(vecs, axis=1, keepdims=True)
            vecs  = vecs / np.maximum(norms, 1e-9)
        return vecs


def _build_embedder():
    try:
        from fastembed import TextEmbedding
        model = TextEmbedding("intfloat/multilingual-e5-large")
        logger.info("임베더: fastembed/multilingual-e5-large")
        return _FastEmbedWrapper(model)
    except Exception as e:
        logger.info(f"fastembed 실패 ({e}), sentence-transformers 시도")
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(EMBED_MODEL)
        logger.info(f"임베더: sentence-transformers/{EMBED_MODEL}")
        return model
    except Exception as e:
        logger.warning(f"임베더 로드 실패 — Sem-* 생략: {e}")
    return None


# ── 지표 계산 ─────────────────────────────────────────────────────────────────

def _coverage(hyp_tokens: list[str], ref_tokens: list[str]) -> dict:
    if not hyp_tokens:
        return {"coverage": 0.0, "novelty": 1.0, "overlap_n": 0,
                "hyp_unique": 0, "ref_unique": len(set(ref_tokens))}
    hyp_set, ref_set = set(hyp_tokens), set(ref_tokens)
    covered  = hyp_set & ref_set
    coverage = len(covered) / len(hyp_set)
    return {
        "coverage":   round(coverage, 4),
        "novelty":    round(1 - coverage, 4),
        "overlap_n":  len(covered),
        "hyp_unique": len(hyp_set),
        "ref_unique": len(ref_set),
    }


def _semantic(embedder, hyp: str, ref: str) -> dict:
    if embedder is None or not hyp or not ref:
        return {"sem_max": None, "sem_mean": None}
    vecs = embedder.encode([hyp, ref], normalize_embeddings=True, show_progress_bar=False)
    sim  = float(vecs[0] @ vecs[1])
    return {"sem_max": round(sim, 4), "sem_mean": round(sim, 4)}


# ── 메인 ─────────────────────────────────────────────────────────────────────

def run(input_path: Path, output_path: Path, use_embed: bool = True) -> None:
    with open(input_path, encoding="utf-8") as f:
        data = json.load(f)

    ticker     = data.get("ticker", "unknown")
    date_range = data.get("date_range", "")
    summaries  = data.get("summaries", [])
    logger.info(f"✓ {ticker} / {date_range}  {len(summaries)}건 로드")

    embedder = _build_embedder() if use_embed else None
    tokenize = _build_tokenizer()

    HDR = (f"\n{'news_id':<30} {'coverage':>8} {'novelty':>8}"
           f" {'sem':>7} {'hyp_tok':>8} {'ref_tok':>8}")
    SEP = "-" * 74
    print(HDR)
    print(SEP)

    results = []
    for s in summaries:
        if s.get("status") != "success":
            continue

        news_id   = s["news_id"]
        hyp_text  = s.get("reference_summary", "")
        ref_text  = s.get("original_news", "")

        if not hyp_text or not ref_text:
            logger.warning(f"  [{news_id}] 텍스트 없음 — 스킵")
            continue

        hyp_tokens = tokenize(hyp_text)
        ref_tokens = tokenize(ref_text)

        cov = _coverage(hyp_tokens, ref_tokens)
        sem = _semantic(embedder, hyp_text, ref_text)

        s_val = f"{sem['sem_max']:.4f}" if sem["sem_max"] is not None else "  N/A"
        print(f"{news_id:<30} {cov['coverage']:>8.4f} {cov['novelty']:>8.4f}"
              f" {s_val:>7} {cov['hyp_unique']:>8} {cov['ref_unique']:>8}")

        results.append({
            "news_id":    news_id,
            "pub_date":   news_id.split("_")[1] if "_" in news_id else None,
            "coverage":   cov["coverage"],
            "novelty":    cov["novelty"],
            "overlap_n":  cov["overlap_n"],
            "hyp_unique": cov["hyp_unique"],
            "ref_unique": cov["ref_unique"],
            "sem_max":    sem["sem_max"],
            "sem_mean":   sem["sem_mean"],
            "hyp_text":   hyp_text,
        })

    if not results:
        logger.warning("결과 없음")
        return

    print(SEP)
    for metric in ["coverage", "novelty"]:
        vals = [r[metric] for r in results]
        print(f"  {metric:<10} 평균: {sum(vals)/len(vals):.4f}  "
              f"범위: {min(vals):.4f}~{max(vals):.4f}")
    sem_vals = [r["sem_max"] for r in results if r["sem_max"] is not None]
    if sem_vals:
        print(f"  {'sem'::<10} 평균: {sum(sem_vals)/len(sem_vals):.4f}  "
              f"범위: {min(sem_vals):.4f}~{max(sem_vals):.4f}")

    output = {
        "ticker":     ticker,
        "date_range": date_range,
        "n":          len(results),
        "summary": {
            "coverage_mean": round(sum(r["coverage"] for r in results) / len(results), 4),
            "novelty_mean":  round(sum(r["novelty"]  for r in results) / len(results), 4),
            "sem_mean":      round(sum(sem_vals) / len(sem_vals), 4) if sem_vals else None,
        },
        "items": results,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    logger.info(f"✓ 저장 완료: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="reference 요약본 coverage/SEM 평가")
    parser.add_argument(
        "--input",
        default=str(project_root / "data" / "005930" / "reference_20200501_20200505.json"),
        help="reference_{ticker}/reference_*.json 경로",
    )
    parser.add_argument("--no-embed", action="store_true", help="임베딩 생략 (빠름)")
    args = parser.parse_args()

    input_path  = Path(args.input)
    output_path = input_path.with_name(input_path.stem + "_eval.json")

    run(input_path, output_path, use_embed=not args.no_embed)

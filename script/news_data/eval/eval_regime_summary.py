"""
국면 요약 평가: LLM 생성 텍스트 vs 뉴스 원문 비교

지표
  Coverage  : LLM 텍스트 토큰 중 원문에 등장하는 비율
  Novelty   : 원문에 없는 토큰 비율 → 잠재 할루시네이션 지표
  Sem-Max   : LLM 임베딩 ↔ 가장 유사한 기사 임베딩 코사인 유사도
  Sem-Mean  : LLM 임베딩 ↔ 전체 기사 임베딩 평균 코사인 유사도

토크나이저: kiwipiepy 우선 → 정규식 fallback
임베더:     fastembed/intfloat/multilingual-e5-large (ONNX, torch 불필요)
            → sentence-transformers/jhgan/ko-sroberta-multitask (torch 기반) fallback

입력: data/regime_news_summary_{ticker_code}.json  (regime_news_summary.py 출력)
출력: 콘솔 테이블 + data/eval_regime_summary_{ticker_code}.json

실행:
    python script/eval_regime_summary.py                          # 기본(005930)
    python script/eval_regime_summary.py --ticker 000660         # SK하이닉스
    python script/eval_regime_summary.py --input  data/my.json --output data/my_eval.json
    python script/eval_regime_summary.py --no-s3                 # S3 재fetch 생략
    python script/eval_regime_summary.py --no-embed              # 임베딩 생략
"""

import argparse
import json
import logging
import re
from datetime import timedelta
from pathlib import Path

import boto3
import numpy as np
import pandas as pd
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv(".env")
load_dotenv(".env.local", override=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

S3_BUCKET      = "fisa-news-archive"
S3_PREFIX      = "raw"
MAX_NEWS_CHARS = 1_300
MAX_NEWS_COUNT = 20
NEWS_PRE       = 2
NEWS_POST      = 1

EMBED_MODEL = "jhgan/ko-sroberta-multitask"


# ── 토크나이저 ────────────────────────────────────────────────────────

def _build_tokenizer():
    """kiwipiepy 우선, 없으면 정규식 fallback."""
    try:
        from kiwipiepy import Kiwi
        kiwi = Kiwi()
        SKIP_TAGS = {"SF", "SP", "SS", "SE", "SO", "SW", "SB", "NF", "NV", "XSN"}
        def _tokenize(text: str) -> list[str]:
            return [t.form for t in kiwi.tokenize(text) if t.tag not in SKIP_TAGS]
        log.info("토크나이저: kiwipiepy (형태소)")
        return _tokenize
    except ImportError:
        def _tokenize(text: str) -> list[str]:
            return re.findall(r"[가-힣a-zA-Z0-9]+", text)
        log.info("토크나이저: 정규식 fallback (kiwipiepy 미설치)")
        return _tokenize


# ── 임베더 ────────────────────────────────────────────────────────────

class _FastEmbedWrapper:
    """fastembed TextEmbedding을 .encode() 인터페이스로 감싼다."""
    def __init__(self, model):
        self._model = model

    def encode(self, texts: list[str], normalize_embeddings: bool = True,
               show_progress_bar: bool = False) -> np.ndarray:
        vecs = np.array(list(self._model.embed(texts)))
        if normalize_embeddings:
            norms = np.linalg.norm(vecs, axis=1, keepdims=True)
            vecs = vecs / np.maximum(norms, 1e-9)
        return vecs


def _build_embedder():
    """임베더 로드. 우선순위: fastembed(ONNX) → sentence-transformers(torch) → None.

    fastembed를 먼저 시도하는 이유: torch DLL 오류가 발생할 경우
    sys.modules 오염으로 이후 import가 연달아 실패하기 때문.
    """
    try:
        from fastembed import TextEmbedding
        model = TextEmbedding("intfloat/multilingual-e5-large")
        log.info("임베더: fastembed/intfloat/multilingual-e5-large (ONNX)")
        return _FastEmbedWrapper(model)
    except ImportError as e:
        log.info(f"fastembed ImportError, sentence-transformers 시도: {e}")
    except Exception as e:
        log.info(f"fastembed 로드 실패, sentence-transformers 시도: {e}")

    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(EMBED_MODEL)
        log.info(f"임베더: sentence-transformers/{EMBED_MODEL}")
        return model
    except ImportError:
        log.warning("sentence-transformers 미설치 — Sem-* 생략")
    except OSError as e:
        log.warning(f"sentence-transformers torch DLL 오류 — Sem-* 생략: {e}")

    return None


# ── LLM 텍스트 추출 ───────────────────────────────────────────────────

def _extract_llm_text(llm_analysis: dict) -> str:
    evidence = llm_analysis.get("evidence", [])
    ev_text  = " ".join(
        f"{e.get('quote', '')} {e.get('point', '')}" for e in evidence if isinstance(e, dict)
    )
    parts = [
        llm_analysis.get("cause", ""),
        ev_text,
        llm_analysis.get("vol_insight", ""),
        llm_analysis.get("reasoning", ""),
    ]
    return " ".join(p for p in parts if p)


# ── S3 원문 수집 ──────────────────────────────────────────────────────

def _fetch_regime_articles(
    s3_client, ticker_code: str, start: pd.Timestamp, end: pd.Timestamp
) -> list[str]:
    """해당 구간 뉴스 기사를 개별 문자열 리스트로 반환."""
    cur = start - timedelta(days=NEWS_PRE)
    fin = end   + timedelta(days=NEWS_POST)
    articles, seen = [], set()

    while cur <= fin:
        key = (
            f"{S3_PREFIX}/{ticker_code}/{cur.year}/{cur.month:02d}"
            f"/{cur.strftime('%Y-%m-%d')}.json"
        )
        try:
            obj  = s3_client.get_object(Bucket=S3_BUCKET, Key=key)
            data = json.loads(obj["Body"].read().decode("utf-8"))
            uid  = f"{data.get('pub_date','')}|{data.get('title','')}"
            if uid not in seen:
                seen.add(uid)
                articles.append(data)
        except ClientError as e:
            if e.response["Error"]["Code"] not in ("NoSuchKey", "404"):
                log.warning(f"S3 오류 {key}: {e}")
        except Exception as e:
            log.warning(f"S3 fetch 실패 {key}: {e}")
        cur += timedelta(days=1)

    articles = sorted(articles, key=lambda x: x.get("pub_date", ""))[:MAX_NEWS_COUNT]
    return [
        a.get("title", "") + " " + (a.get("fulltext") or "")[:MAX_NEWS_CHARS]
        for a in articles
    ]


# ── 지표 계산 ─────────────────────────────────────────────────────────

def _overlap_metrics(
    ref_tokens: list[str], hyp_tokens: list[str]
) -> dict[str, float]:
    """Coverage (LLM→원문 지지율) 및 Novelty."""
    if not hyp_tokens:
        return {"coverage": 0.0, "novelty": 1.0, "hyp_unique": 0, "ref_unique": 0, "overlap_n": 0}
    ref_set = set(ref_tokens)
    hyp_set = set(hyp_tokens)
    covered = hyp_set & ref_set
    coverage = len(covered) / len(hyp_set)
    return {
        "coverage":   round(coverage, 4),
        "novelty":    round(1 - coverage, 4),
        "hyp_unique": len(hyp_set),
        "ref_unique": len(ref_set),
        "overlap_n":  len(covered),
    }


def _semantic_similarity(
    embedder, llm_text: str, articles: list[str]
) -> dict[str, float | None]:
    """LLM 임베딩 ↔ 개별 기사 임베딩 코사인 유사도 (최대/평균).

    normalize_embeddings=True → L2 정규화 → 내적 == 코사인 유사도.
    """
    if embedder is None or not articles:
        return {"sem_max": None, "sem_mean": None}

    texts = [llm_text] + articles
    vecs  = embedder.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    llm_vec      = vecs[0]
    article_vecs = vecs[1:]
    sims = article_vecs @ llm_vec
    return {
        "sem_max":  round(float(sims.max()),  4),
        "sem_mean": round(float(sims.mean()), 4),
    }


# ── 메인 ─────────────────────────────────────────────────────────────

def run(
    ticker_code:  str         = "005930",
    summary_path: Path | None = None,
    output_path:  Path | None = None,
    use_s3:       bool        = True,
    use_embed:    bool        = True,
) -> None:
    summary_path = summary_path or Path(f"data/regime_news_summary_{ticker_code}.json")
    output_path  = output_path  or Path(f"data/eval_regime_summary_{ticker_code}.json")

    if not summary_path.exists():
        raise FileNotFoundError(f"{summary_path} 없음 — regime_news_summary.py 먼저 실행")

    summaries: list[dict] = json.loads(summary_path.read_text(encoding="utf-8"))
    log.info(f"요약 {len(summaries)}건 로드  ({summary_path})")

    # 임베더를 먼저 초기화: kiwipiepy의 네이티브 DLL이 onnxruntime과 충돌하기 때문
    embedder  = _build_embedder() if use_embed else None
    tokenize  = _build_tokenizer()
    s3_client = boto3.client("s3") if use_s3 else None

    eval_results = []

    HDR = (
        f"\n{'구간':<6} {'기간':<24} {'방향':<5}"
        f" {'Coverage':>9} {'Novelty':>8}"
        f" {'Sem-Max':>8} {'Sem-Mean':>9}"
        f" {'LLM토큰':>7} {'원문토큰':>8}"
    )
    SEP = "-" * 90
    print(HDR)
    print(SEP)

    for rec in summaries:
        regime_id = rec.get("regime_id", "?")
        start     = pd.Timestamp(rec["start"])
        end       = pd.Timestamp(rec["end"])
        direction = rec.get("direction", "")
        llm_text  = _extract_llm_text(rec.get("llm_analysis", {}))

        if not llm_text.strip():
            log.warning(f"  [{regime_id}] LLM 텍스트 없음 — 스킵")
            continue

        articles: list[str] = []
        if use_s3 and s3_client:
            articles = _fetch_regime_articles(s3_client, ticker_code, start, end)

        original_text = " ".join(articles)

        hyp_tokens = tokenize(llm_text)
        ref_tokens = tokenize(original_text) if original_text else []

        overlap = _overlap_metrics(ref_tokens, hyp_tokens)
        sem     = _semantic_similarity(embedder, llm_text, articles)

        dir_sym = "▲" if direction == "상승" else "▼"
        period  = f"{rec['start']}~{rec['end']}"
        cov = f"{overlap['coverage']:.3f}"
        nov = f"{overlap['novelty']:.3f}"
        smx = f"{sem['sem_max']:.3f}"  if sem["sem_max"]  is not None else "  N/A"
        smn = f"{sem['sem_mean']:.3f}" if sem["sem_mean"] is not None else "   N/A"

        print(
            f"[{regime_id:>2}]  {period:<23} {dir_sym:<4}"
            f" {cov:>9} {nov:>8}"
            f" {smx:>8} {smn:>9}"
            f" {overlap['hyp_unique']:>7} {overlap['ref_unique']:>8}"
        )

        eval_results.append({
            "regime_id":  regime_id,
            "start":      rec["start"],
            "end":        rec["end"],
            "days":       rec.get("days"),
            "direction":  direction,
            "cum_return": rec.get("cum_return"),
            "vol_trend":  rec.get("vol_trend"),
            "news_count": rec.get("news_count"),
            "tokens_in":  rec.get("tokens_in"),
            "tokens_out": rec.get("tokens_out"),
            "hyp_tokens": overlap["hyp_unique"],
            "ref_tokens": overlap["ref_unique"],
            "overlap_n":  overlap["overlap_n"],
            "coverage":   overlap["coverage"],
            "novelty":    overlap["novelty"],
            "sem_max":    sem["sem_max"],
            "sem_mean":   sem["sem_mean"],
            "llm_text":   llm_text,
        })

    if not eval_results:
        log.warning("평가 결과 없음")
        return

    # ── 집계 통계 ─────────────────────────────────────────────────────
    print(SEP)
    metrics = ["coverage", "novelty", "sem_max", "sem_mean"]
    avgs: dict[str, float] = {}
    for m in metrics:
        vals = [r[m] for r in eval_results if r.get(m) is not None]
        avgs[m] = sum(vals) / len(vals) if vals else float("nan")

    smx_avg = f"{avgs['sem_max']:.3f}"  if not np.isnan(avgs["sem_max"])  else "  N/A"
    smn_avg = f"{avgs['sem_mean']:.3f}" if not np.isnan(avgs["sem_mean"]) else "   N/A"
    print(
        f"{'평균':<32}"
        f" {avgs['coverage']:>9.3f} {avgs['novelty']:>8.3f}"
        f" {smx_avg:>8} {smn_avg:>9}"
    )

    print("\n해석 가이드:")
    print("  Coverage > 0.5  → LLM 절반 이상이 원문에서 확인 가능 (충실도 높음)")
    print("  Novelty  > 0.5  → LLM 절반 이상이 원문 밖 표현 (할루시네이션 위험 또는 추론)")
    print("  Sem-Max  > 0.7  → LLM이 적어도 한 기사와 의미적으로 일치")
    print("  Sem-Mean > 0.5  → 전체 기사 대비 평균 의미 충실도 양호")

    # ── 저장 ─────────────────────────────────────────────────────────
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(eval_results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.info(f"저장: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="국면 요약 평가 (Coverage + 시맨틱 유사도)")
    parser.add_argument("--ticker",   default="005930",
                        help="종목 코드 (기본: 005930). 입출력 경로 자동 결정")
    parser.add_argument("--input",    default=None,
                        help="입력 JSON 경로 (지정 시 --ticker 무시)")
    parser.add_argument("--output",   default=None,
                        help="출력 JSON 경로 (지정 시 --ticker 무시)")
    parser.add_argument("--no-s3",    action="store_true", help="S3 재fetch 생략")
    parser.add_argument("--no-embed", action="store_true", help="임베딩 생략 (빠름)")
    args = parser.parse_args()

    run(
        ticker_code  = args.ticker,
        summary_path = Path(args.input)  if args.input  else None,
        output_path  = Path(args.output) if args.output else None,
        use_s3       = not args.no_s3,
        use_embed    = not args.no_embed,
    )

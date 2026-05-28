#!/usr/bin/env python3
"""
국면 요약 결과 MLflow 평가 파이프라인

data/{ticker}/regime_news_summary_{ticker}.json  (LLM 분석 결과)
data/{ticker}/eval_regime_summary_{ticker}.json  (sem/coverage/ref_tokens 메트릭)
→ mlflow.genai.evaluate 로 품질 메트릭 로깅
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging
import json
import os
import mlflow
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

_env_file = Path(__file__).parent.parent / ".env.local"
if _env_file.exists():
    load_dotenv(_env_file, override=True)

_CONFIDENCE_SCORE = {"high": 1.0, "medium": 0.5, "low": 0.0}


# ─── Custom Scorers ───────────────────────────────────────────────────────────

@mlflow.genai.scorer
def sem_max_scorer(_outputs: str, expectations: dict) -> float:
    """LLM 출력과 참조 뉴스 간 최대 코사인 유사도"""
    return float(expectations.get("sem_max", 0.0))


@mlflow.genai.scorer
def coverage_scorer(_outputs: str, expectations: dict) -> float:
    """LLM 출력 토큰의 참조 뉴스 커버리지"""
    return float(expectations.get("coverage", 0.0))


@mlflow.genai.scorer
def confidence_scorer(_outputs: str, expectations: dict) -> float:
    """LLM 자체 신뢰도 (high=1.0, medium=0.5, low=0.0)"""
    conf = expectations.get("confidence", "low")
    return _CONFIDENCE_SCORE.get(conf, 0.0)


@mlflow.genai.scorer
def ref_tokens_scorer(_outputs: str, expectations: dict) -> float:
    """참조 뉴스 원문 토큰 수 (데이터 충분도 지표)"""
    return float(expectations.get("ref_tokens", 0))


# ─── Data Loaders ─────────────────────────────────────────────────────────────

def load_regime_data(ticker: str) -> tuple[list[dict], list[dict]]:
    """
    regime_news_summary + eval_regime_summary 로드

    Returns:
        (summary_records, eval_records)
    """
    data_dir = project_root / "data" / ticker

    summary_path = data_dir / f"regime_news_summary_{ticker}.json"
    eval_path    = data_dir / f"eval_regime_summary_{ticker}.json"

    if not summary_path.exists():
        raise FileNotFoundError(f"regime_news_summary 파일 없음: {summary_path}")
    if not eval_path.exists():
        raise FileNotFoundError(f"eval_regime_summary 파일 없음: {eval_path}")

    with open(summary_path, encoding="utf-8") as f:
        summary_records = json.load(f)
    with open(eval_path, encoding="utf-8") as f:
        eval_records = json.load(f)

    logger.info(f"✓ 국면 요약 로드: {len(summary_records)}건")
    logger.info(f"✓ 평가 메트릭 로드: {len(eval_records)}건")

    return summary_records, eval_records


def build_mlflow_data(
    summary_records: list[dict],
    eval_records: list[dict],
) -> tuple[list[dict], dict]:
    """
    mlflow.genai.evaluate 입력 데이터 및 outputs 사전 구성

    Returns:
        (mlflow_data, outputs_by_regime_id)
    """
    eval_by_id = {r["regime_id"]: r for r in eval_records}

    mlflow_data: list[dict] = []
    outputs_by_id: dict[int, str] = {}

    for rec in summary_records:
        rid      = rec["regime_id"]
        analysis = rec.get("llm_analysis", {})
        eval_r   = eval_by_id.get(rid, {})

        if not analysis:
            continue

        # 평가 대상 텍스트: cause + reasoning
        output_text = "\n".join(filter(None, [
            analysis.get("cause", ""),
            analysis.get("reasoning", ""),
        ]))
        outputs_by_id[rid] = output_text

        mlflow_data.append({
            "inputs": {
                "regime_id":  rid,
                "ticker":     rec.get("ticker_code", ""),
                "period":     f"{rec['start']}~{rec['end']}",
                "direction":  rec["direction"],
                "cum_return": rec["cum_return"],
                "days":       rec["days"],
                "news_count": rec["news_count"],
                "tokens_in":  rec["tokens_in"],
            },
            "expectations": {
                "confidence": analysis.get("confidence", "low"),
                "sem_max":    eval_r.get("sem_max",    0.0),
                "coverage":   eval_r.get("coverage",   0.0),
                "ref_tokens": eval_r.get("ref_tokens", 0),
            },
        })

    return mlflow_data, outputs_by_id


# ─── Pipeline ─────────────────────────────────────────────────────────────────

def run_evaluation_pipeline(
    ticker: str,
    mlflow_experiment: str = "regime_analysis_eval",
) -> bool:
    """국면 요약 결과 MLflow 평가 파이프라인"""
    logger.info("=" * 60)
    logger.info("국면 요약 MLflow 평가 파이프라인")
    logger.info("=" * 60)

    # MLflow 연결 설정
    mlflow_uri      = os.getenv("MLFLOW_TRACKING_URI", "")
    mlflow_username = os.getenv("MLFLOW_TRACKING_USERNAME", "")
    mlflow_password = os.getenv("MLFLOW_TRACKING_PASSWORD", "")

    if not mlflow_uri:
        logger.error("❌ MLFLOW_TRACKING_URI 미설정")
        return False

    mlflow.set_tracking_uri(mlflow_uri)
    if mlflow_username and mlflow_password:
        os.environ["MLFLOW_TRACKING_USERNAME"] = mlflow_username
        os.environ["MLFLOW_TRACKING_PASSWORD"] = mlflow_password
        logger.info("✓ MLflow 인증 설정 완료")

    mlflow.set_experiment(mlflow_experiment)

    try:
        # 1. 데이터 로드
        logger.info(f"\n[1/3] 데이터 로드 중... ({ticker})")
        summary_records, eval_records = load_regime_data(ticker)

        # 2. MLflow 데이터 구성
        logger.info("\n[2/3] 평가 데이터 구성 중...")
        mlflow_data, _ = build_mlflow_data(summary_records, eval_records)

        if not mlflow_data:
            logger.error("❌ 평가 데이터 없음")
            return False

        logger.info(f"✓ 평가 대상: {len(mlflow_data)}건")

        # 3. 집계 통계 계산 및 summary run 기록
        logger.info("\n[3/3] MLflow 기록 중...")
        eval_by_id = {r["regime_id"]: r for r in eval_records}
        n = len(summary_records)

        conf_counts: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
        sem_vals, cov_vals, ref_vals = [], [], []

        for rec in summary_records:
            rid  = rec["regime_id"]
            conf = rec.get("llm_analysis", {}).get("confidence", "low")
            conf_counts[conf] = conf_counts.get(conf, 0) + 1
            ev = eval_by_id.get(rid, {})
            if ev:
                sem_vals.append(ev.get("sem_max",    0.0))
                cov_vals.append(ev.get("coverage",   0.0))
                ref_vals.append(ev.get("ref_tokens", 0))

        run_name = f"{ticker}_regime_eval"
        with mlflow.start_run(run_name=run_name) as run:
            mlflow.log_param("ticker",        ticker)
            mlflow.log_param("regime_count",  n)
            mlflow.log_param("eval_count",    len(mlflow_data))

            if sem_vals:
                mlflow.log_metric("sem_max_mean",    sum(sem_vals) / len(sem_vals))
                mlflow.log_metric("sem_max_min",     min(sem_vals))
                mlflow.log_metric("coverage_mean",   sum(cov_vals) / len(cov_vals))
                mlflow.log_metric("ref_tokens_mean", sum(ref_vals) / len(ref_vals))

            mlflow.log_metric("confidence_high_ratio",
                              conf_counts.get("high",   0) / n if n else 0.0)
            mlflow.log_metric("confidence_medium_ratio",
                              conf_counts.get("medium", 0) / n if n else 0.0)
            mlflow.log_metric("confidence_low_ratio",
                              conf_counts.get("low",    0) / n if n else 0.0)

            logger.info(f"✓ 집계 Run 기록 완료: {run.info.run_id}")

        # per-regime 점수를 직접 집계해서 단일 run에 기록
        logger.info("📊 per-regime 점수 집계 중...")
        score_rows = []
        for item in mlflow_data:
            exp = item["expectations"]
            score_rows.append({
                "regime_id":  item["inputs"]["regime_id"],
                "period":     item["inputs"]["period"],
                "direction":  item["inputs"]["direction"],
                "sem_max":    exp.get("sem_max",    0.0),
                "coverage":   exp.get("coverage",   0.0),
                "confidence": exp.get("confidence", "low"),
                "conf_score": _CONFIDENCE_SCORE.get(exp.get("confidence", "low"), 0.0),
                "ref_tokens": exp.get("ref_tokens", 0),
            })

        # per-regime 결과를 JSON 아티팩트로 저장 (MLflow UI에서 확인 가능)
        import tempfile
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", encoding="utf-8", delete=False
        ) as f:
            json.dump(score_rows, f, ensure_ascii=False, indent=2)
            tmp = Path(f.name)

        with mlflow.start_run(run_name=f"{ticker}_regime_quality") as qrun:
            mlflow.log_artifact(str(tmp), artifact_path="per_regime")
            mlflow.log_metric("sem_max_mean",  sum(r["sem_max"]    for r in score_rows) / len(score_rows))
            mlflow.log_metric("coverage_mean", sum(r["coverage"]   for r in score_rows) / len(score_rows))
            mlflow.log_metric("conf_mean",     sum(r["conf_score"] for r in score_rows) / len(score_rows))
            mlflow.log_metric("ref_tokens_mean", sum(r["ref_tokens"] for r in score_rows) / len(score_rows))
            logger.info(f"✓ per-regime 품질 Run: {qrun.info.run_id}")

        tmp.unlink(missing_ok=True)

        # 결과 요약 출력
        logger.info("\n" + "=" * 60)
        logger.info("✅ 국면 요약 평가 완료!")
        logger.info("=" * 60)
        logger.info(f"\n  총 국면 수:   {n}")
        logger.info(f"  confidence high:   {conf_counts['high']}건  "
                    f"({100 * conf_counts['high']   / n:.1f}%)")
        logger.info(f"  confidence medium: {conf_counts['medium']}건  "
                    f"({100 * conf_counts['medium'] / n:.1f}%)")
        logger.info(f"  confidence low:    {conf_counts.get('low', 0)}건  "
                    f"({100 * conf_counts.get('low', 0) / n:.1f}%)")
        if sem_vals:
            logger.info(f"\n  sem_max 평균:      {sum(sem_vals) / len(sem_vals):.4f}")
            logger.info(f"  coverage 평균:     {sum(cov_vals) / len(cov_vals):.4f}")
            logger.info(f"  ref_tokens 평균:   {sum(ref_vals) / len(ref_vals):.0f}")
        logger.info(f"\n  MLflow 실험: {mlflow_experiment}")

        return True

    except Exception as e:
        logger.error(f"❌ 파이프라인 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    import argparse

    default_experiment = os.getenv("MLFLOW_EXPERIMENT", "regime_analysis_eval")

    parser = argparse.ArgumentParser(description="국면 요약 MLflow 평가 파이프라인")
    parser.add_argument(
        "--ticker",
        type=str,
        default="005930",
        help="티커 (기본값: 005930)",
    )
    parser.add_argument(
        "--experiment",
        type=str,
        default=default_experiment,
        help=f"MLflow 실험 이름 (기본값: {default_experiment})",
    )

    args = parser.parse_args()

    success = run_evaluation_pipeline(
        ticker=args.ticker,
        mlflow_experiment=args.experiment,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

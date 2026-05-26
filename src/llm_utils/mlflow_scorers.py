"""
MLflow Quality 통합을 위한 커스텀 Scorer

ROUGE, BERTScore를 @mlflow.genai.scorer 데코레이터로 구현합니다.
"""

import logging
from typing import Any, Dict, Optional
import mlflow

logger = logging.getLogger(__name__)


@mlflow.genai.scorer
def rouge_scorer(outputs: str, expectations: dict) -> float:
    """
    ROUGE-1 기반 스코어러

    Args:
        outputs: 생성된 요약
        expectations: 참조 요약을 포함한 기대값 dict {"reference_summary": "..."}

    Returns:
        ROUGE-1 F1 점수 (0~1)
    """
    try:
        from rouge_score import rouge_scorer as rs

        reference = expectations.get("reference_summary", "")
        if not reference:
            return 0.0

        scorer = rs.RougeScorer(["rouge1"], use_stemmer=True)
        result = scorer.score(reference, outputs)
        return result["rouge1"].fmeasure
    except Exception as e:
        logger.error(f"ROUGE 계산 실패: {str(e)}")
        return 0.0


@mlflow.genai.scorer
def bert_score_scorer(outputs: str, expectations: dict) -> float:
    """
    BERTScore 기반 스코어러 (한국어)

    Args:
        outputs: 생성된 요약
        expectations: 참조 요약을 포함한 기대값 dict {"reference_summary": "..."}

    Returns:
        BERTScore F1 점수 (0~1)
    """
    try:
        from bert_score import score

        reference = expectations.get("reference_summary", "")
        if not reference:
            return 0.0

        P, R, F1 = score(
            [outputs],
            [reference],
            model_type="bert-base-multilingual-cased",
            lang="ko",
            batch_size=32,
            rescale_with_baseline=True,
        )

        return float(F1[0].item() if hasattr(F1[0], 'item') else F1[0])
    except Exception as e:
        logger.error(f"BERTScore 계산 실패: {str(e)}")
        return 0.0


@mlflow.genai.scorer
def summary_similarity_score(outputs: str, expectations: dict) -> float:
    """
    요약 유사도 종합 스코어러 (ROUGE + BERTScore 평균)

    Args:
        outputs: 생성된 요약
        expectations: 참조 요약을 포함한 기대값 dict {"reference_summary": "..."}

    Returns:
        종합 유사도 점수 (0~1)
    """
    try:
        rouge_score = rouge_scorer(outputs, expectations)
        bert_score = bert_score_scorer(outputs, expectations)
        return (rouge_score + bert_score) / 2
    except Exception as e:
        logger.error(f"종합 유사도 계산 실패: {str(e)}")
        return 0.0

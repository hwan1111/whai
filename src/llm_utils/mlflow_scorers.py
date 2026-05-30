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


@mlflow.genai.scorer
def entity_preservation_scorer(outputs: str, expectations: dict) -> float:
    """
    엔티티 보존도 스코어러 (금융 뉴스 특화)

    금융 뉴스에서 중요한 엔티티(티커, 가격, 수치 등)의 보존도를 평가합니다.
    Task #3에서 구현한 EntityPreservationMetrics를 MLflow와 통합합니다.

    Args:
        outputs: 생성된 요약
        expectations: 참조 요약을 포함한 기대값 dict {"reference_summary": "..."}

    Returns:
        엔티티 보존도 F1 점수 (0~1)
    """
    try:
        from src.llm_utils.evaluation_metrics import EntityPreservationMetrics

        reference = expectations.get("reference_summary", "")
        if not reference:
            logger.debug("엔티티 보존도: 참조 요약이 없음")
            return 0.0

        scores = EntityPreservationMetrics.calculate(reference, outputs)
        logger.debug(
            f"엔티티 보존도 계산: "
            f"overall_f1={scores.overall_f1:.3f}, "
            f"missing={len(scores.missing_entities)}, "
            f"extra={len(scores.extra_entities)}"
        )
        return scores.overall_f1

    except Exception as e:
        logger.error(f"엔티티 보존도 계산 실패: {str(e)}")
        return 0.0


@mlflow.genai.scorer
def number_accuracy_scorer(outputs: str, expectations: dict) -> float:
    """
    수치 정확도 스코어러 (금융 뉴스 특화)

    금융 뉴스에서 중요한 수치(퍼센트, 가격, 거래량 등)의 정확도를 평가합니다.
    Task #3에서 구현한 NumberAccuracyMetrics를 MLflow와 통합합니다.

    Args:
        outputs: 생성된 요약
        expectations: 참조 요약을 포함한 기대값 dict {"reference_summary": "..."}

    Returns:
        수치 정확도 점수 (0~1)
    """
    try:
        from src.llm_utils.evaluation_metrics import NumberAccuracyMetrics

        reference = expectations.get("reference_summary", "")
        if not reference:
            logger.debug("수치 정확도: 참조 요약이 없음")
            return 0.0

        scores = NumberAccuracyMetrics.calculate(reference, outputs)
        logger.debug(
            f"수치 정확도 계산: "
            f"overall={scores.overall_number_accuracy:.3f}, "
            f"false_numbers={scores.false_numbers}"
        )
        return scores.overall_number_accuracy

    except Exception as e:
        logger.error(f"수치 정확도 계산 실패: {str(e)}")
        return 0.0


@mlflow.genai.scorer
def financial_quality_score(outputs: str, expectations: dict) -> float:
    """
    금융 뉴스 종합 품질 스코어러

    엔티티 보존도와 수치 정확도의 가중 평균으로 금융 뉴스의 종합 품질을 평가합니다.
    - 엔티티 보존도: 50% (금융 정보 핵심 유지)
    - 수치 정확도: 50% (금융 수치 정확성)

    Args:
        outputs: 생성된 요약
        expectations: 참조 요약을 포함한 기대값 dict {"reference_summary": "..."}

    Returns:
        종합 품질 점수 (0~1)
    """
    try:
        entity_score = entity_preservation_scorer(outputs, expectations)
        number_score = number_accuracy_scorer(outputs, expectations)

        # 가중 평균: 엔티티 50%, 수치 50%
        quality_score = (entity_score * 0.5) + (number_score * 0.5)

        logger.debug(
            f"금융 종합 품질 점수: {quality_score:.3f} "
            f"(엔티티={entity_score:.3f}, 수치={number_score:.3f})"
        )
        return quality_score

    except Exception as e:
        logger.error(f"금융 종합 품질 계산 실패: {str(e)}")
        return 0.0

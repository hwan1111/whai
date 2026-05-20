"""
평가 실행 엔진

요약 품질을 평가하고 결과를 MLflow에 로깅합니다.
"""

import logging
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

import mlflow

from .evaluation_metrics import (
    RougeMetrics,
    BertScoreMetrics,
    QualitativeMetrics,
    RougeScores,
    BertScores,
    QualitativeScore,
)

logger = logging.getLogger(__name__)


@dataclass
class EvaluationResult:
    """평가 결과 종합"""
    summary_id: str
    article: str
    reference_summary: str
    generated_summary: str
    rouge_scores: Dict
    bert_scores: Dict
    qualitative_score: Dict
    overall_score: float

    def to_dict(self) -> Dict:
        """딕셔너리로 변환"""
        return asdict(self)


class NewsEvaluator:
    """뉴스 요약 평가 엔진"""

    def __init__(self, use_bert_score: bool = True):
        """
        NewsEvaluator 초기화

        Args:
            use_bert_score: BERTScore 사용 여부 (리소스 많이 사용)
        """
        self.rouge_metrics = RougeMetrics()
        self.bert_metrics = None
        self.use_bert_score = use_bert_score

        if use_bert_score:
            try:
                self.bert_metrics = BertScoreMetrics()
            except RuntimeError as e:
                logger.warning(f"⚠️ BERTScore 사용 불가: {str(e)}")
                self.use_bert_score = False

        logger.info(
            f"✓ NewsEvaluator 초기화 완료 "
            f"(BERTScore: {'활성' if self.use_bert_score else '비활성'})"
        )

    def evaluate_single(
        self,
        article: str,
        reference_summary: str,
        generated_summary: str,
        summary_id: Optional[str] = None,
    ) -> EvaluationResult:
        """
        단일 요약 평가

        Args:
            article: 원본 기사
            reference_summary: 참조 요약 (정답)
            generated_summary: 생성된 요약 (예측)
            summary_id: 요약 ID (선택사항)

        Returns:
            EvaluationResult 객체
        """
        if summary_id is None:
            summary_id = f"summary_{hash(generated_summary) % 10000}"

        logger.info(f"평가 시작: {summary_id}")

        # ROUGE 점수 계산
        logger.debug("ROUGE 점수 계산 중...")
        rouge_result: RougeScores = self.rouge_metrics.calculate(
            reference_summary,
            generated_summary,
        )
        rouge_dict = rouge_result.to_dict()
        logger.debug(f"  ROUGE-1 F1: {rouge_result.rouge1_f:.4f}")

        # BERTScore 계산 (선택사항)
        bert_dict = {}
        if self.use_bert_score:
            logger.debug("BERTScore 계산 중...")
            try:
                bert_result, avg_p, avg_r, avg_f1 = self.bert_metrics.calculate(
                    [reference_summary],
                    [generated_summary],
                )
                bert_dict = bert_result.to_dict()
                logger.debug(f"  BERTScore F1: {avg_f1:.4f}")
            except Exception as e:
                logger.warning(f"⚠️ BERTScore 계산 실패: {str(e)}")

        # 정성적 평가 (기본값)
        qualitative = QualitativeScore()
        qualitative_dict = qualitative.to_dict()

        # 종합 점수 계산 (ROUGE와 정성적 평가 평균)
        overall_score = (rouge_result.rouge1_f + qualitative.average() / 5) / 2

        result = EvaluationResult(
            summary_id=summary_id,
            article=article,
            reference_summary=reference_summary,
            generated_summary=generated_summary,
            rouge_scores=rouge_dict,
            bert_scores=bert_dict,
            qualitative_score=qualitative_dict,
            overall_score=overall_score,
        )

        logger.info(
            f"평가 완료: {summary_id} (종합 점수: {overall_score:.4f})"
        )

        return result

    def evaluate_batch(
        self,
        summaries: List[Dict],
        log_to_mlflow: bool = True,
        run_name: Optional[str] = None,
    ) -> List[EvaluationResult]:
        """
        배치 평가

        Args:
            summaries: 평가 대상 요약 리스트
                [{
                    "article": "...",
                    "reference_summary": "...",
                    "generated_summary": "...",
                    "id": "..."
                }]
            log_to_mlflow: MLflow 로깅 여부
            run_name: MLflow Run 이름

        Returns:
            EvaluationResult 리스트
        """
        logger.info(f"배치 평가 시작 ({len(summaries)}개 항목)")

        results = []
        total_rouge1_f = 0
        total_bert_f1 = 0
        bert_count = 0

        if log_to_mlflow:
            mlflow.log_param("evaluation_count", len(summaries))
            mlflow.log_param("use_bert_score", self.use_bert_score)

        for i, summary in enumerate(summaries, 1):
            try:
                result = self.evaluate_single(
                    article=summary.get("article", ""),
                    reference_summary=summary.get("reference_summary", ""),
                    generated_summary=summary.get("generated_summary", ""),
                    summary_id=summary.get("id"),
                )

                results.append(result)
                total_rouge1_f += result.rouge_scores["rouge1_f"]

                if result.bert_scores:
                    total_bert_f1 += result.bert_scores["avg_f1"]
                    bert_count += 1

                if log_to_mlflow:
                    self._log_result_to_mlflow(result)

            except Exception as e:
                logger.error(f"❌ 항목 {i} 평가 실패: {str(e)}")
                continue

        # 평균 점수 계산 및 로깅
        if results:
            avg_rouge1_f = total_rouge1_f / len(results)
            avg_bert_f1 = total_bert_f1 / bert_count if bert_count > 0 else 0

            logger.info(f"\n{'=' * 60}")
            logger.info(f"배치 평가 완료")
            logger.info(f"{'=' * 60}")
            logger.info(f"평가 항목: {len(results)}개")
            logger.info(f"평균 ROUGE-1 F1: {avg_rouge1_f:.4f}")
            if self.use_bert_score and bert_count > 0:
                logger.info(f"평균 BERTScore F1: {avg_bert_f1:.4f}")

            if log_to_mlflow:
                mlflow.log_metric("avg_rouge1_f1", avg_rouge1_f)
                if self.use_bert_score and bert_count > 0:
                    mlflow.log_metric("avg_bert_f1", avg_bert_f1)

        return results

    def _log_result_to_mlflow(self, result: EvaluationResult) -> None:
        """
        평가 결과를 MLflow에 로깅

        Args:
            result: EvaluationResult 객체
        """
        try:
            # 지표 로깅 (summary_id는 run 이름으로 구분)
            mlflow.log_metric("rouge1_f", result.rouge_scores["rouge1_f"])
            mlflow.log_metric("rouge2_f", result.rouge_scores["rouge2_f"])
            mlflow.log_metric("rougeL_f", result.rouge_scores["rougeL_f"])

            if result.bert_scores:
                mlflow.log_metric("bert_f1", result.bert_scores["avg_f1"])

            mlflow.log_metric("overall_score", result.overall_score)

            # 아티팩트 로깅 (선택사항)
            # TODO: 요약 텍스트를 파일로 저장하고 아티팩트로 등록

        except Exception as e:
            logger.warning(f"⚠️ MLflow 로깅 실패: {str(e)}")

    def get_evaluation_summary(
        self,
        results: List[EvaluationResult],
    ) -> Dict:
        """
        평가 결과 요약

        Args:
            results: EvaluationResult 리스트

        Returns:
            요약 정보
        """
        if not results:
            return {}

        rouge1_scores = [r.rouge_scores["rouge1_f"] for r in results]
        bert_scores = [r.bert_scores["avg_f1"] for r in results if r.bert_scores]

        summary = {
            "total_count": len(results),
            "rouge1_avg": sum(rouge1_scores) / len(rouge1_scores),
            "rouge1_min": min(rouge1_scores),
            "rouge1_max": max(rouge1_scores),
        }

        if bert_scores:
            summary.update({
                "bert_avg": sum(bert_scores) / len(bert_scores),
                "bert_min": min(bert_scores),
                "bert_max": max(bert_scores),
            })

        return summary

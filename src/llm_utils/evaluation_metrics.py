"""
뉴스 요약 평가 메트릭

ROUGE, BERTScore, 정성적 지표를 계산합니다.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class RougeScores:
    """ROUGE 점수 결과"""
    rouge1_f: float  # ROUGE-1 F1 점수
    rouge1_p: float  # ROUGE-1 Precision
    rouge1_r: float  # ROUGE-1 Recall
    rouge2_f: float  # ROUGE-2 F1 점수
    rouge2_p: float
    rouge2_r: float
    rougeL_f: float  # ROUGE-L F1 점수
    rougeL_p: float
    rougeL_r: float

    def to_dict(self) -> Dict[str, float]:
        """딕셔너리로 변환"""
        return {
            "rouge1_f": self.rouge1_f,
            "rouge1_p": self.rouge1_p,
            "rouge1_r": self.rouge1_r,
            "rouge2_f": self.rouge2_f,
            "rouge2_p": self.rouge2_p,
            "rouge2_r": self.rouge2_r,
            "rougeL_f": self.rougeL_f,
            "rougeL_p": self.rougeL_p,
            "rougeL_r": self.rougeL_r,
        }


@dataclass
class BertScores:
    """BERTScore 결과"""
    precision: float  # 개별 정밀도
    recall: float     # 개별 재현율
    f1: float        # 개별 F1 점수
    avg_precision: float  # 배치 평균 정밀도
    avg_recall: float     # 배치 평균 재현율
    avg_f1: float        # 배치 평균 F1 점수

    def to_dict(self) -> Dict[str, float]:
        """딕셔너리로 변환"""
        return {
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "avg_precision": self.avg_precision,
            "avg_recall": self.avg_recall,
            "avg_f1": self.avg_f1,
        }


@dataclass
class QualitativeScore:
    """정성적 평가 점수 (1-5 스케일)"""
    fluency: int = 3  # 문장의 자연스러움
    accuracy: int = 3  # 원본과의 정확성
    relevance: int = 3  # 관련성 및 핵심 내용 포함
    comments: str = ""  # 평가자 코멘트

    def average(self) -> float:
        """평균 점수 계산"""
        return (self.fluency + self.accuracy + self.relevance) / 3

    def to_dict(self) -> Dict:
        """딕셔너리로 변환"""
        return {
            "fluency": self.fluency,
            "accuracy": self.accuracy,
            "relevance": self.relevance,
            "comments": self.comments,
            "average": self.average(),
        }


class RougeMetrics:
    """ROUGE 메트릭 계산"""

    def __init__(self):
        """RougeMetrics 초기화"""
        try:
            from rouge_score import rouge_scorer
            self.scorer = rouge_scorer.RougeScorer(
                ["rouge1", "rouge2", "rougeL"],
                use_stemmer=True,
            )
            logger.info("✓ ROUGE 계산기 초기화 완료")
        except ImportError:
            raise RuntimeError(
                "❌ rouge-score 라이브러리가 설치되지 않았습니다.\n"
                "설치: pip install rouge-score --break-system-packages"
            )

    def calculate(
        self,
        reference: str,
        hypothesis: str,
    ) -> RougeScores:
        """
        ROUGE 점수 계산

        Args:
            reference: 참조 요약 (정답)
            hypothesis: 생성된 요약 (예측)

        Returns:
            RougeScores 객체
        """
        try:
            scores = self.scorer.score(reference, hypothesis)

            return RougeScores(
                rouge1_f=scores["rouge1"].fmeasure,
                rouge1_p=scores["rouge1"].precision,
                rouge1_r=scores["rouge1"].recall,
                rouge2_f=scores["rouge2"].fmeasure,
                rouge2_p=scores["rouge2"].precision,
                rouge2_r=scores["rouge2"].recall,
                rougeL_f=scores["rougeL"].fmeasure,
                rougeL_p=scores["rougeL"].precision,
                rougeL_r=scores["rougeL"].recall,
            )

        except Exception as e:
            logger.error(f"❌ ROUGE 계산 실패: {str(e)}")
            raise


class BertScoreMetrics:
    """BERTScore 메트릭 계산"""

    def __init__(self, model_type: str = "bert-base-multilingual-cased"):
        """
        BertScoreMetrics 초기화

        Args:
            model_type: 사용할 모델 (기본값: 다국어 BERT)
        """
        try:
            from bert_score import score
            self.score_fn = score
            self.model_type = model_type
            logger.info(f"✓ BERTScore 계산기 초기화 완료 (모델: {model_type})")
        except ImportError:
            raise RuntimeError(
                "❌ bert-score 라이브러리가 설치되지 않았습니다.\n"
                "설치: pip install bert-score --break-system-packages"
            )

    def calculate(
        self,
        references: List[str],
        hypotheses: List[str],
        lang: str = "ko",
    ) -> Tuple[BertScores, float, float, float]:
        """
        BERTScore 점수 계산

        Args:
            references: 참조 요약 리스트 (정답들)
            hypotheses: 생성된 요약 리스트 (예측들)
            lang: 언어 코드 (기본값: "ko")

        Returns:
            (BertScores 객체, 평균 정밀도, 평균 재현율, 평균 F1)
        """
        if len(references) != len(hypotheses):
            raise ValueError("참조와 예측의 개수가 일치하지 않습니다")

        try:
            P, R, F1 = self.score_fn(
                hypotheses,
                references,
                model_type=self.model_type,
                lang=lang,
                batch_size=32,
                rescale_with_baseline=True,
            )

            # 개별 점수 (첫 번째 항목)
            individual_p = P[0].item() if hasattr(P[0], 'item') else P[0]
            individual_r = R[0].item() if hasattr(R[0], 'item') else R[0]
            individual_f1 = F1[0].item() if hasattr(F1[0], 'item') else F1[0]

            # 배치 평균
            avg_p = P.mean().item() if hasattr(P.mean(), 'item') else P.mean()
            avg_r = R.mean().item() if hasattr(R.mean(), 'item') else R.mean()
            avg_f1 = F1.mean().item() if hasattr(F1.mean(), 'item') else F1.mean()

            return (
                BertScores(
                    precision=individual_p,
                    recall=individual_r,
                    f1=individual_f1,
                    avg_precision=avg_p,
                    avg_recall=avg_r,
                    avg_f1=avg_f1,
                ),
                avg_p,
                avg_r,
                avg_f1,
            )

        except Exception as e:
            logger.error(f"❌ BERTScore 계산 실패: {str(e)}")
            raise


class QualitativeMetrics:
    """정성적 평가 메트릭"""

    @staticmethod
    def create_evaluation_prompt(
        article: str,
        reference_summary: str,
        generated_summary: str,
    ) -> str:
        """
        정성적 평가를 위한 프롬프트 생성

        Args:
            article: 원본 기사
            reference_summary: 참조 요약
            generated_summary: 생성된 요약

        Returns:
            평가 프롬프트
        """
        return f"""다음 요약을 1-5 점수로 평가하세요:

[원본 기사]
{article[:500]}...

[참조 요약 (정답)]
{reference_summary}

[생성된 요약 (평가 대상)]
{generated_summary}

평가 기준:
1. Fluency (자연스러움): 문장이 자연스럽고 읽기 쉬운가?
2. Accuracy (정확성): 원본 기사의 내용을 정확하게 전달하는가?
3. Relevance (관련성): 핵심 내용을 포함하고 관련성이 높은가?

각 항목을 1-5로 평가해주세요.
"""

    @staticmethod
    def batch_calculate(
        article_summaries: List[Dict],
        score_fn=None,
    ) -> List[QualitativeScore]:
        """
        배치 정성적 평가

        Args:
            article_summaries: 평가 대상 요약 리스트
                [{"article": "...", "reference": "...", "generated": "..."}]
            score_fn: 점수 계산 함수 (외부 LLM 활용 시)

        Returns:
            QualitativeScore 리스트
        """
        results = []

        for item in article_summaries:
            if score_fn:
                # 외부 함수로 점수 계산 (예: LLM 활용)
                score = score_fn(
                    item["article"],
                    item["reference"],
                    item["generated"],
                )
            else:
                # 기본값: 중간 점수
                score = QualitativeScore(
                    fluency=3,
                    accuracy=3,
                    relevance=3,
                    comments="수동 평가 대기 중",
                )

            results.append(score)

        logger.info(f"✓ {len(results)}개 항목 정성적 평가 완료")
        return results

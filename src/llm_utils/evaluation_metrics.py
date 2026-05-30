"""
뉴스 요약 평가 메트릭

ROUGE, BERTScore, 정성적 지표를 계산합니다.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

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


@dataclass
class FinancialEntities:
    """금융 뉴스에서 추출된 엔티티"""
    tickers: Set[str] = field(default_factory=set)  # AAPL, 005930.KS 등
    companies: Set[str] = field(default_factory=set)  # 애플, 삼성 등
    percentages: Set[str] = field(default_factory=set)  # 15%, -3.5% 등
    prices: Set[str] = field(default_factory=set)  # $150, 100,000원 등
    volumes: Set[str] = field(default_factory=set)  # 1M주, 500K주 등
    dates: Set[str] = field(default_factory=set)  # 1월 15일, 2026-05-27 등
    actions: Set[str] = field(default_factory=set)  # 상승, 하락, 발표, 인수 등

    def to_dict(self) -> Dict[str, list]:
        """딕셔너리로 변환"""
        return {
            "tickers": sorted(list(self.tickers)),
            "companies": sorted(list(self.companies)),
            "percentages": sorted(list(self.percentages)),
            "prices": sorted(list(self.prices)),
            "volumes": sorted(list(self.volumes)),
            "dates": sorted(list(self.dates)),
            "actions": sorted(list(self.actions)),
        }


@dataclass
class EntityPreservationScores:
    """엔티티 보존 평가 점수"""
    ticker_f1: float  # 티커 보존률
    percentage_f1: float  # 퍼센트 보존률
    price_f1: float  # 가격 보존률
    volume_f1: float  # 거래량 보존률
    date_f1: float  # 날짜 보존률
    action_f1: float  # 액션 보존률
    overall_f1: float  # 전체 엔티티 F1
    missing_entities: Dict[str, list] = field(default_factory=dict)  # 누락된 엔티티
    extra_entities: Dict[str, list] = field(default_factory=dict)  # 추가된 엔티티

    def to_dict(self) -> Dict:
        """딕셔너리로 변환"""
        return {
            "ticker_f1": self.ticker_f1,
            "percentage_f1": self.percentage_f1,
            "price_f1": self.price_f1,
            "volume_f1": self.volume_f1,
            "date_f1": self.date_f1,
            "action_f1": self.action_f1,
            "overall_f1": self.overall_f1,
            "missing_entities": self.missing_entities,
            "extra_entities": self.extra_entities,
        }


@dataclass
class NumberAccuracyScores:
    """수치 정확도 평가 점수"""
    percentage_match_ratio: float  # 퍼센트 정확도
    price_match_ratio: float  # 가격 정확도
    volume_match_ratio: float  # 거래량 정확도
    overall_number_accuracy: float  # 전체 수치 정확도
    false_numbers: int  # 실제로 없는 수치 개수
    number_errors: List[str] = field(default_factory=list)  # 수치 오류 상세

    def to_dict(self) -> Dict:
        """딕셔너리로 변환"""
        return {
            "percentage_match_ratio": self.percentage_match_ratio,
            "price_match_ratio": self.price_match_ratio,
            "volume_match_ratio": self.volume_match_ratio,
            "overall_number_accuracy": self.overall_number_accuracy,
            "false_numbers": self.false_numbers,
            "number_errors": self.number_errors,
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


class FinancialEntityExtractor:
    """금융 뉴스에서 엔티티 추출"""

    # 금융 특화 패턴 정의
    PATTERNS = {
        "ticker": r"(?:[A-Z]{1,4}(?:\.[A-Z]{2})?|\d{6}\.[A-Z]{2})",  # AAPL, 005930.KS, MSFT
        "percentage": r"[-+]?\d+\.?\d*\s*%",  # 15%, -3.5%
        "price": r"(?:\$\d+\.?\d*|\d+(?:,\d{3})*\s*(?:원|달러))",  # $150, 100,000원
        "volume": r"\d+(?:\.\d+)?\s*[MKB]?\s*주",  # 1M주, 500K주
        "date": r"\d{1,4}[-/년]\d{1,2}[-/월]\d{1,2}(?:일)?",  # 2026-05-27, 5월 27일
        "actions": r"(?:상승|하락|급등|급락|발표|인수|합병|상장|상한가|하한가|거래정지)",
    }

    # 한국 주식 시장 주요 회사명
    KOREAN_COMPANIES = {
        "삼성": {"tickers": ["005930.KS"]},
        "SK": {"tickers": ["034730.KS"]},
        "LG": {"tickers": ["066570.KS"]},
        "현대": {"tickers": ["005380.KS"]},
        "기아": {"tickers": ["000270.KS"]},
        "네이버": {"tickers": ["035420.KS"]},
        "카카오": {"tickers": ["035720.KS"]},
        "포스코": {"tickers": ["005490.KS"]},
    }

    @classmethod
    def extract(cls, text: str) -> FinancialEntities:
        """
        텍스트에서 금융 엔티티 추출

        Args:
            text: 추출할 텍스트

        Returns:
            FinancialEntities 객체
        """
        entities = FinancialEntities()

        # 패턴 기반 추출
        for entity_type, pattern in cls.PATTERNS.items():
            matches = re.findall(pattern, text)
            if entity_type == "ticker":
                entities.tickers.update(matches)
            elif entity_type == "percentage":
                entities.percentages.update(matches)
            elif entity_type == "price":
                entities.prices.update(matches)
            elif entity_type == "volume":
                entities.volumes.update(matches)
            elif entity_type == "date":
                entities.dates.update(matches)
            elif entity_type == "actions":
                entities.actions.update(matches)

        # 회사명 추출
        for company, info in cls.KOREAN_COMPANIES.items():
            if company in text:
                entities.companies.add(company)
                entities.tickers.update(info["tickers"])

        return entities


class EntityPreservationMetrics:
    """엔티티 보존 평가 메트릭"""

    @staticmethod
    def _calculate_f1(
        reference_entities: Set[str],
        generated_entities: Set[str],
    ) -> Tuple[float, Set[str], Set[str]]:
        """
        F1 점수 계산

        Args:
            reference_entities: 참조 요약의 엔티티
            generated_entities: 생성 요약의 엔티티

        Returns:
            (F1 점수, 누락된 엔티티, 추가된 엔티티)
        """
        if not reference_entities and not generated_entities:
            return 1.0, set(), set()

        if not reference_entities or not generated_entities:
            return 0.0, reference_entities - generated_entities, generated_entities - reference_entities

        intersection = reference_entities & generated_entities
        precision = len(intersection) / len(generated_entities) if generated_entities else 0
        recall = len(intersection) / len(reference_entities) if reference_entities else 0

        if precision + recall == 0:
            return 0.0, reference_entities - generated_entities, generated_entities - reference_entities

        f1 = 2 * (precision * recall) / (precision + recall)
        missing = reference_entities - generated_entities
        extra = generated_entities - reference_entities

        return f1, missing, extra

    @classmethod
    def calculate(
        cls,
        reference_summary: str,
        generated_summary: str,
    ) -> EntityPreservationScores:
        """
        엔티티 보존 점수 계산

        Args:
            reference_summary: 참조 요약
            generated_summary: 생성된 요약

        Returns:
            EntityPreservationScores 객체
        """
        # 엔티티 추출
        ref_entities = FinancialEntityExtractor.extract(reference_summary)
        gen_entities = FinancialEntityExtractor.extract(generated_summary)

        # 각 엔티티 타입별 F1 계산
        ticker_f1, ticker_missing, ticker_extra = cls._calculate_f1(
            ref_entities.tickers, gen_entities.tickers
        )
        pct_f1, pct_missing, pct_extra = cls._calculate_f1(
            ref_entities.percentages, gen_entities.percentages
        )
        price_f1, price_missing, price_extra = cls._calculate_f1(
            ref_entities.prices, gen_entities.prices
        )
        vol_f1, vol_missing, vol_extra = cls._calculate_f1(
            ref_entities.volumes, gen_entities.volumes
        )
        date_f1, date_missing, date_extra = cls._calculate_f1(
            ref_entities.dates, gen_entities.dates
        )
        action_f1, action_missing, action_extra = cls._calculate_f1(
            ref_entities.actions, gen_entities.actions
        )

        # 전체 F1 평균 계산
        all_f1_scores = [ticker_f1, pct_f1, price_f1, vol_f1, date_f1, action_f1]
        overall_f1 = sum(all_f1_scores) / len(all_f1_scores)

        missing_entities = {
            "tickers": list(ticker_missing),
            "percentages": list(pct_missing),
            "prices": list(price_missing),
            "volumes": list(vol_missing),
            "dates": list(date_missing),
            "actions": list(action_missing),
        }

        extra_entities = {
            "tickers": list(ticker_extra),
            "percentages": list(pct_extra),
            "prices": list(price_extra),
            "volumes": list(vol_extra),
            "dates": list(date_extra),
            "actions": list(action_extra),
        }

        return EntityPreservationScores(
            ticker_f1=ticker_f1,
            percentage_f1=pct_f1,
            price_f1=price_f1,
            volume_f1=vol_f1,
            date_f1=date_f1,
            action_f1=action_f1,
            overall_f1=overall_f1,
            missing_entities=missing_entities,
            extra_entities=extra_entities,
        )


class NumberAccuracyMetrics:
    """수치 정확도 평가 메트릭"""

    @staticmethod
    def _normalize_number(num_str: str) -> str:
        """수치 정규화"""
        # 쉼표 제거, 공백 제거
        return re.sub(r"[\s,]", "", num_str.strip()).lower()

    @classmethod
    def calculate(
        cls,
        reference_summary: str,
        generated_summary: str,
    ) -> NumberAccuracyScores:
        """
        수치 정확도 계산

        Args:
            reference_summary: 참조 요약
            generated_summary: 생성된 요약

        Returns:
            NumberAccuracyScores 객체
        """
        # 엔티티 추출
        ref_entities = FinancialEntityExtractor.extract(reference_summary)
        gen_entities = FinancialEntityExtractor.extract(generated_summary)

        number_errors = []

        # 퍼센트 비교
        ref_pct = {cls._normalize_number(p) for p in ref_entities.percentages}
        gen_pct = {cls._normalize_number(p) for p in gen_entities.percentages}
        pct_errors = ref_pct - gen_pct
        pct_match = len(ref_pct & gen_pct) / len(ref_pct) if ref_pct else 1.0
        if pct_errors:
            number_errors.append(f"누락된 퍼센트: {pct_errors}")

        # 가격 비교
        ref_price = {cls._normalize_number(p) for p in ref_entities.prices}
        gen_price = {cls._normalize_number(p) for p in gen_entities.prices}
        price_errors = ref_price - gen_price
        price_match = len(ref_price & gen_price) / len(ref_price) if ref_price else 1.0
        if price_errors:
            number_errors.append(f"누락된 가격: {price_errors}")

        # 거래량 비교
        ref_vol = {cls._normalize_number(v) for v in ref_entities.volumes}
        gen_vol = {cls._normalize_number(v) for v in gen_entities.volumes}
        vol_errors = ref_vol - gen_vol
        vol_match = len(ref_vol & gen_vol) / len(ref_vol) if ref_vol else 1.0
        if vol_errors:
            number_errors.append(f"누락된 거래량: {vol_errors}")

        # 생성된 요약에만 있는 잘못된 수치
        false_pct = len(gen_pct - ref_pct)
        false_price = len(gen_price - ref_price)
        false_vol = len(gen_vol - ref_vol)
        total_false = false_pct + false_price + false_vol

        # 전체 정확도
        all_matches = [pct_match, price_match, vol_match]
        overall_accuracy = sum(all_matches) / len(all_matches)

        return NumberAccuracyScores(
            percentage_match_ratio=pct_match,
            price_match_ratio=price_match,
            volume_match_ratio=vol_match,
            overall_number_accuracy=overall_accuracy,
            false_numbers=total_false,
            number_errors=number_errors,
        )


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

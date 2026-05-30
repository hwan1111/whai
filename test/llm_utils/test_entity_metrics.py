"""
엔티티/수치 기반 평가 메트릭 단위 테스트
"""

import pytest
from src.llm_utils.evaluation_metrics import (
    FinancialEntityExtractor,
    EntityPreservationMetrics,
    NumberAccuracyMetrics,
    FinancialEntities,
)


class TestFinancialEntityExtractor:
    """금융 엔티티 추출 테스트"""

    def test_extract_ticker(self):
        """티커 추출 테스트"""
        text = "삼성전자(005930.KS) 주가가 상승했다. AAPL도 강세다."
        entities = FinancialEntityExtractor.extract(text)

        assert "005930.KS" in entities.tickers
        assert "AAPL" in entities.tickers

    def test_extract_percentage(self):
        """퍼센트 추출 테스트"""
        text = "지난주 15% 상승했고, -3.5% 하락했다."
        entities = FinancialEntityExtractor.extract(text)

        assert "15%" in entities.percentages
        assert "-3.5%" in entities.percentages

    def test_extract_price(self):
        """가격 추출 테스트"""
        text = "$150으로 상승했고, 100,000원에 거래되었다."
        entities = FinancialEntityExtractor.extract(text)

        assert len(entities.prices) > 0

    def test_extract_volume(self):
        """거래량 추출 테스트"""
        text = "오늘 1M주가 거래되었고, 500K주 규모로 체결됐다."
        entities = FinancialEntityExtractor.extract(text)

        assert len(entities.volumes) > 0

    def test_extract_actions(self):
        """액션 추출 테스트"""
        text = "삼성전자가 신규 공장 건설을 발표했다. SK인수 소식도 있다."
        entities = FinancialEntityExtractor.extract(text)

        assert "발표" in entities.actions

    def test_extract_korean_companies(self):
        """한국 회사명 추출 테스트"""
        text = "삼성전자와 LG화학이 합병한다."
        entities = FinancialEntityExtractor.extract(text)

        assert "삼성" in entities.companies
        assert "LG" in entities.companies

    def test_empty_text(self):
        """빈 텍스트 추출 테스트"""
        entities = FinancialEntityExtractor.extract("")
        assert len(entities.tickers) == 0


class TestEntityPreservationMetrics:
    """엔티티 보존 평가 메트릭 테스트"""

    def test_perfect_preservation(self):
        """완벽한 엔티티 보존"""
        ref = "삼성전자(005930.KS)가 15% 상승했다."
        gen = "삼성전자(005930.KS)가 15% 상승했다."

        scores = EntityPreservationMetrics.calculate(ref, gen)

        assert scores.ticker_f1 == 1.0
        assert scores.percentage_f1 == 1.0
        assert scores.overall_f1 == 1.0

    def test_partial_preservation(self):
        """부분적 엔티티 보존"""
        ref = "삼성전자(005930.KS)가 15% 상승했다."
        gen = "삼성전자가 상승했다."

        scores = EntityPreservationMetrics.calculate(ref, gen)

        assert scores.ticker_f1 < 1.0  # 티커 누락
        assert scores.percentage_f1 < 1.0  # 퍼센트 누락

    def test_missing_entities(self):
        """누락된 엔티티 감지"""
        ref = "AAPL과 005930.KS, 035420.KS가 주도했다."
        gen = "AAPL이 주도했다."

        scores = EntityPreservationMetrics.calculate(ref, gen)

        assert len(scores.missing_entities["tickers"]) == 2
        assert "005930.KS" in scores.missing_entities["tickers"]

    def test_extra_entities(self):
        """추가된 엔티티 감지"""
        ref = "AAPL이 상승했다."
        gen = "AAPL과 MSFT, GOOGL이 상승했다. 25% 상승했다."

        scores = EntityPreservationMetrics.calculate(ref, gen)

        assert len(scores.extra_entities["tickers"]) >= 2
        assert len(scores.extra_entities["percentages"]) >= 1

    def test_no_entities(self):
        """엔티티가 없는 경우"""
        ref = "시장이 강세다."
        gen = "시장이 매우 강세다."

        scores = EntityPreservationMetrics.calculate(ref, gen)

        assert scores.overall_f1 == 1.0


class TestNumberAccuracyMetrics:
    """수치 정확도 평가 메트릭 테스트"""

    def test_perfect_number_accuracy(self):
        """완벽한 수치 정확도"""
        ref = "지난주 15% 상승했고, $150에 거래됐다."
        gen = "지난주 15% 상승했고, $150에 거래됐다."

        scores = NumberAccuracyMetrics.calculate(ref, gen)

        assert scores.percentage_match_ratio == 1.0
        assert scores.price_match_ratio == 1.0
        assert scores.false_numbers == 0

    def test_missing_numbers(self):
        """누락된 수치"""
        ref = "15% 상승했고, 25% 하락했다."
        gen = "상승했다."

        scores = NumberAccuracyMetrics.calculate(ref, gen)

        assert scores.percentage_match_ratio < 1.0
        assert len(scores.number_errors) > 0

    def test_false_numbers(self):
        """잘못된 수치 추가"""
        ref = "15% 상승했다."
        gen = "15% 상승했고, 30% 추가 상승했다."

        scores = NumberAccuracyMetrics.calculate(ref, gen)

        assert scores.false_numbers > 0

    def test_number_normalization(self):
        """수치 정규화 테스트"""
        ref = "100,000원에 거래됐다."
        gen = "100000원에 거래됐다."

        scores = NumberAccuracyMetrics.calculate(ref, gen)

        # 정규화되어 일치해야 함
        assert scores.price_match_ratio == 1.0

    def test_mixed_errors(self):
        """혼합된 오류"""
        ref = "15% 상승, $100, 1M주 거래"
        gen = "25% 상승, $150"  # 모든 수치가 틀림

        scores = NumberAccuracyMetrics.calculate(ref, gen)

        assert scores.overall_number_accuracy < 1.0
        assert scores.false_numbers >= 2


class TestIntegration:
    """통합 테스트"""

    def test_real_world_example(self):
        """실제 뉴스 요약 예시"""
        original = """삼성전자(005930.KS)가 지난주 15% 상승했다.
        분기 실적이 예상보다 좋아서 애널리스트들의 목표가가
        평균 $150에서 $160으로 올라갔다. 거래량도 1M주 규모로 활발했다."""

        good_summary = """삼성전자(005930.KS)가 15% 상승했다.
        분기 실적 호조로 목표가가 $150에서 $160으로 상향조정되었고,
        거래량은 1M주 규모를 기록했다."""

        bad_summary = """삼성전자가 상승했다.
        분기 실적이 좋았다."""

        # 좋은 요약 평가
        good_scores = EntityPreservationMetrics.calculate(original, good_summary)
        bad_scores = EntityPreservationMetrics.calculate(original, bad_summary)

        # 좋은 요약이 더 높은 점수를 받아야 함
        assert good_scores.overall_f1 > bad_scores.overall_f1
        assert good_scores.ticker_f1 >= bad_scores.ticker_f1

        # 좋은 요약의 수치 정확도
        good_num = NumberAccuracyMetrics.calculate(original, good_summary)
        bad_num = NumberAccuracyMetrics.calculate(original, bad_summary)

        assert good_num.overall_number_accuracy > bad_num.overall_number_accuracy


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

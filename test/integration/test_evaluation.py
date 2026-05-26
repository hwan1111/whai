#!/usr/bin/env python3
"""
평가 메트릭 시스템 통합 테스트

ROUGE, BERTScore, 정성적 지표를 테스트합니다.
"""

import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import logging
from src.llm_utils import NewsEvaluator

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    """평가 메트릭 시스템 테스트"""
    logger.info("=" * 60)
    logger.info("평가 메트릭 시스템 테스트")
    logger.info("=" * 60)

    # 테스트 데이터
    test_article = """
    Apple Inc. announced record quarterly earnings of $25.3 billion, beating analyst
    expectations by 15%. The company's iPhone sales surged due to strong demand in Asia,
    while Services revenue continued its steady growth trajectory. CEO Tim Cook attributed
    the success to innovation and customer loyalty programs. The stock rose 8% in
    after-hours trading. Analysts remain bullish on the company's prospects for Q3.
    """

    reference_summary = """
    Apple이 분기 매출 253억 달러로 분석가 예상을 15% 초과 달성했다.
    아이폰 판매가 아시아 수요 증가로 급증했으며, 서비스 부문은 지속적인 성장을 이어갔다.
    CEO Tim Cook은 혁신과 고객 충성도 프로그램이 성공의 원동력이라고 밝혔다.
    """

    generated_summary = """
    Apple은 253억 달러의 기록적 분기 매출을 발표했고 분석가 예상을 초과했다.
    아이폰 판매가 증가했고, 서비스 부문도 성장을 계속했다.
    CEO Cook은 회사의 성공이 혁신에서 비롯되었다고 말했다.
    """

    # 1. NewsEvaluator 초기화 (BERTScore 비활성화로 테스트 속도 향상)
    logger.info("\n[1/3] NewsEvaluator 초기화 중...")
    try:
        evaluator = NewsEvaluator(use_bert_score=False)  # 테스트용 빠른 실행
        logger.info("✓ NewsEvaluator 초기화 완료")
    except Exception as e:
        logger.error(f"❌ 초기화 실패: {str(e)}")
        return False

    # 2. 단일 요약 평가
    logger.info("\n[2/3] 단일 요약 평가 중...")
    try:
        result = evaluator.evaluate_single(
            article=test_article,
            reference_summary=reference_summary,
            generated_summary=generated_summary,
            summary_id="test_summary_001",
        )

        logger.info(f"✓ 평가 완료")
        logger.info(f"\n평가 결과:")
        logger.info(f"  ROUGE-1 F1: {result.rouge_scores['rouge1_f']:.4f}")
        logger.info(f"  ROUGE-2 F1: {result.rouge_scores['rouge2_f']:.4f}")
        logger.info(f"  ROUGE-L F1: {result.rouge_scores['rougeL_f']:.4f}")
        logger.info(f"  종합 점수: {result.overall_score:.4f}")

    except Exception as e:
        logger.error(f"❌ 평가 실패: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

    # 3. 배치 평가
    logger.info("\n[3/3] 배치 평가 중...")
    try:
        batch_summaries = [
            {
                "id": "summary_001",
                "article": test_article,
                "reference_summary": reference_summary,
                "generated_summary": generated_summary,
            },
            {
                "id": "summary_002",
                "article": test_article,
                "reference_summary": reference_summary,
                "generated_summary": "Apple의 분기 성과가 좋았다.",
            },
        ]

        batch_results = evaluator.evaluate_batch(
            batch_summaries,
            log_to_mlflow=False,  # 테스트용 MLflow 비활성화
        )

        summary = evaluator.get_evaluation_summary(batch_results)
        logger.info(f"✓ 배치 평가 완료")
        logger.info(f"\n배치 평가 요약:")
        logger.info(f"  평가 항목: {summary['total_count']}")
        logger.info(f"  평균 ROUGE-1 F1: {summary['rouge1_avg']:.4f}")
        logger.info(f"  최소 ROUGE-1 F1: {summary['rouge1_min']:.4f}")
        logger.info(f"  최대 ROUGE-1 F1: {summary['rouge1_max']:.4f}")

    except Exception as e:
        logger.error(f"❌ 배치 평가 실패: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

    # 최종 결과
    logger.info("\n" + "=" * 60)
    logger.info("✅ 평가 메트릭 시스템 테스트 성공!")
    logger.info("=" * 60)

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

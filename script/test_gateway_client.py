#!/usr/bin/env python3
"""
AI Gateway 클라이언트 테스트

MLflow AI Gateway를 통한 LLM 호출이 정상 작동하는지 확인합니다.
"""

import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging
from src.llm_utils import GatewayClient

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    """AI Gateway 클라이언트 테스트"""
    logger.info("=" * 60)
    logger.info("AI Gateway 클라이언트 테스트")
    logger.info("=" * 60)

    # 1. 클라이언트 초기화
    logger.info("\n[1/3] Gateway 클라이언트 초기화 중...")
    try:
        client = GatewayClient(validate_connection=True)
        logger.info("✓ 클라이언트 초기화 완료")
    except RuntimeError as e:
        logger.error(f"❌ 초기화 실패: {str(e)}")
        return False

    # 2. 요약 테스트 (샘플 뉴스 기사)
    logger.info("\n[2/3] LLM 호출 테스트 중...")
    sample_text = (
        "Apple Inc. announced record quarterly earnings of $25.3 billion, "
        "beating analyst expectations by 15%. The company's iPhone sales surged "
        "due to strong demand in Asia, while Services revenue continued its "
        "steady growth trajectory. CEO Tim Cook attributed the success to innovation "
        "and customer loyalty programs. The stock rose 8% in after-hours trading."
    )

    try:
        logger.info(f"입력 텍스트: {len(sample_text)}자")
        logger.info("(5초 정도 소요될 수 있습니다...)")

        # 요약 호출
        summary = client.summarize(
            text=sample_text,
            temperature=0.7,
            max_tokens=100,
        )

        logger.info("✓ 요약 완료")
        logger.info(f"\n📝 요약 결과:")
        logger.info(f"   {summary}\n")

    except Exception as e:
        logger.error(f"❌ LLM 호출 실패: {str(e)}")
        return False

    # 3. 여러 번 호출 테스트
    logger.info("[3/3] 다중 호출 테스트 중...")
    test_articles = [
        {
            "title": "Tesla Q4 Results",
            "text": "Tesla reported quarterly revenue of $24.3B with net income "
            "of $2.5B. The company delivered 1.8 million vehicles globally. "
            "Elon Musk announced plans for three new factories.",
        },
        {
            "title": "Microsoft Cloud Growth",
            "text": "Microsoft's Azure cloud services grew 28% year-over-year, "
            "driven by enterprise AI adoption. Cloud revenue now represents 35% "
            "of total company revenue. Satya Nadella emphasized AI as core strategy.",
        },
    ]

    try:
        for i, article in enumerate(test_articles, 1):
            logger.info(f"\n   테스트 {i}: {article['title']}")
            summary = client.summarize(
                text=article["text"],
                temperature=0.7,
                max_tokens=80,
            )
            logger.info(f"   → {summary[:100]}...")

        logger.info("\n✓ 다중 호출 테스트 완료")

    except Exception as e:
        logger.error(f"❌ 다중 호출 실패: {str(e)}")
        return False

    # 최종 결과
    logger.info("\n" + "=" * 60)
    logger.info("✅ AI Gateway 클라이언트 테스트 성공!")
    logger.info("=" * 60)
    logger.info("\n다음 단계:")
    logger.info("  1. 프롬프트 저장 시스템 구축 (model/llm/prompts/)")
    logger.info("  2. 평가 메트릭 정의 (model/llm/evaluators/)")
    logger.info("  3. 테스트 데이터셋 준비 (data/llm_eval/)")

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

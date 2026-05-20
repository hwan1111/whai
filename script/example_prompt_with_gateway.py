#!/usr/bin/env python3
"""
프롬프트 관리 시스템과 Gateway 클라이언트 통합 예제

프롬프트를 로드하고 LLM을 호출하는 완전한 워크플로우를 보여줍니다.
"""

import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging
from src.llm_utils import GatewayClient, PromptManager

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    """프롬프트 + Gateway 통합 예제"""
    logger.info("=" * 60)
    logger.info("프롬프트 + Gateway 통합 예제")
    logger.info("=" * 60)

    # 1. PromptManager와 GatewayClient 초기화
    logger.info("\n[1/3] 초기화 중...")
    try:
        pm = PromptManager()
        client = GatewayClient(validate_connection=True)
        logger.info("✓ PromptManager, GatewayClient 초기화 완료")
    except Exception as e:
        logger.error(f"❌ 초기화 실패: {str(e)}")
        return False

    # 2. 샘플 뉴스 기사
    logger.info("\n[2/3] 뉴스 기사 요약 중...")

    articles = [
        {
            "title": "Apple Q1 Results",
            "content": (
                "Apple Inc. announced record quarterly earnings of $25.3 billion, "
                "beating analyst expectations by 15%. The company's iPhone sales surged "
                "due to strong demand in Asia, while Services revenue continued its "
                "steady growth trajectory. CEO Tim Cook attributed the success to innovation "
                "and customer loyalty programs. The stock rose 8% in after-hours trading."
            ),
        },
        {
            "title": "Microsoft Cloud Growth",
            "content": (
                "Microsoft's Azure cloud services grew 28% year-over-year, "
                "driven by enterprise AI adoption. Cloud revenue now represents 35% "
                "of total company revenue. Satya Nadella emphasized AI as core strategy. "
                "The company announced three new AI centers of excellence. "
                "Enterprise customers increased by 22% year-over-year."
            ),
        },
    ]

    # 3. 각 기사 요약
    try:
        for i, article in enumerate(articles, 1):
            logger.info(f"\n   기사 {i}: {article['title']}")

            # 프롬프트 렌더링
            rendered_prompt = pm.render_prompt(
                "news_summarization",
                article=article["content"],
            )

            # 모델 설정 가져오기
            model_config = pm.get_model_config("news_summarization")

            # LLM 호출
            summary = client.call(
                text=rendered_prompt,
                temperature=model_config.get("temperature", 0.5),
                max_tokens=model_config.get("max_tokens", 200),
            )

            logger.info(f"\n   📝 요약:\n   {summary}\n")

        logger.info("✓ 모든 기사 요약 완료")

    except Exception as e:
        logger.error(f"❌ 요약 실패: {str(e)}")
        return False

    # 최종 결과
    logger.info("\n" + "=" * 60)
    logger.info("✅ 프롬프트 + Gateway 통합 성공!")
    logger.info("=" * 60)
    logger.info("\n통합 워크플로우:")
    logger.info("  1. PromptManager: 프롬프트 템플릿 로드")
    logger.info("  2. 파라미터 주입: 기사 내용 삽입")
    logger.info("  3. GatewayClient: MLflow AI Gateway 호출")
    logger.info("  4. 결과: LLM 요약 수신")

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

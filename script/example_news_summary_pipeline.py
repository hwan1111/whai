#!/usr/bin/env python3
"""
뉴스 데이터 로더 + 프롬프트 매니저 통합 예제

실제 로컬 뉴스 데이터를 로드하고 LLM으로 요약하는 파이프라인입니다.
"""

import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging
from src.data.news_loader import NewsDataLoader
from src.llm_utils import PromptManager, GatewayClient

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    """뉴스 로더 + 프롬프트 관리 시스템 예제"""
    logger.info("=" * 60)
    logger.info("뉴스 데이터 로더 + 요약 파이프라인 예제")
    logger.info("=" * 60)

    # 1. 데이터 로더 초기화
    logger.info("\n[1/4] NewsDataLoader 초기화 중...")
    try:
        loader = NewsDataLoader()
        logger.info("✓ NewsDataLoader 초기화 완료")
    except Exception as e:
        logger.error(f"❌ 초기화 실패: {str(e)}")
        return False

    # 2. 사용 가능한 티커 확인
    logger.info("\n[2/4] 사용 가능한 티커 확인 중...")
    try:
        tickers = loader.list_available_tickers()
        if not tickers:
            logger.error("❌ 사용 가능한 티커가 없습니다")
            return False

        logger.info(f"✓ 사용 가능한 티커: {tickers}")

        ticker = "005930"  # 삼성전자
        if ticker not in tickers:
            logger.error(f"❌ {ticker}를 찾을 수 없습니다")
            return False

    except Exception as e:
        logger.error(f"❌ 티커 조회 실패: {str(e)}")
        return False

    # 3. 뉴스 데이터 로드
    logger.info("\n[3/4] 뉴스 데이터 로드 중...")
    try:
        # 최근 5일 뉴스 로드
        news_list = loader.load_news(
            ticker=ticker,
            start_date="2026-05-03",
            end_date="2026-05-07",
        )

        if not news_list:
            logger.warning("⚠️ 로드된 뉴스가 없습니다")
            return False

        logger.info(f"✓ {len(news_list)}개의 뉴스 로드 완료")

    except Exception as e:
        logger.error(f"❌ 뉴스 로드 실패: {str(e)}")
        return False

    # 4. PromptManager와 Gateway 초기화
    logger.info("\n[4/4] 프롬프트 관리 및 LLM 호출 준비 중...")
    try:
        pm = PromptManager()
        client = GatewayClient(validate_connection=True)
        logger.info("✓ PromptManager, GatewayClient 초기화 완료")
    except Exception as e:
        logger.error(f"❌ 초기화 실패: {str(e)}")
        return False

    # 5. 뉴스 요약
    logger.info("\n" + "=" * 60)
    logger.info("뉴스 요약 시작")
    logger.info("=" * 60)

    for i, news in enumerate(news_list[:3], 1):  # 최대 3개만 요약
        try:
            metadata = loader.get_news_metadata(news)
            title, fulltext = loader.get_article_text(news)

            logger.info(f"\n[뉴스 {i}] {metadata['pub_date']}")
            logger.info(f"제목: {title[:60]}...")
            logger.info(f"소스: {metadata['source']}")

            # 프롬프트 렌더링
            rendered_prompt = pm.render_prompt(
                "news_summarization",
                article=fulltext,
            )

            # 모델 설정 가져오기
            model_config = pm.get_model_config("news_summarization")

            # LLM 호출로 요약
            logger.info("요약 중... (5초 정도 소요)")
            summary = client.call(
                text=rendered_prompt,
                temperature=model_config.get("temperature", 0.5),
                max_tokens=model_config.get("max_tokens", 200),
            )

            logger.info(f"\n📝 요약 결과:")
            logger.info(f"{summary}")
            logger.info(f"링크: {metadata['link']}")

        except Exception as e:
            logger.error(f"❌ 뉴스 {i} 요약 실패: {str(e)}")
            continue

    # 최종 결과
    logger.info("\n" + "=" * 60)
    logger.info("✅ 파이프라인 예제 완료!")
    logger.info("=" * 60)

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

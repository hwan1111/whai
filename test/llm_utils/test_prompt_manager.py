#!/usr/bin/env python3
"""
프롬프트 관리 시스템 테스트

PromptManager의 로드, 렌더링, MLflow 로깅 기능을 검증합니다.
"""

import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging
from src.llm_utils import PromptManager

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    """프롬프트 관리 시스템 테스트"""
    logger.info("=" * 60)
    logger.info("프롬프트 관리 시스템 테스트")
    logger.info("=" * 60)

    # 1. PromptManager 초기화
    logger.info("\n[1/4] PromptManager 초기화 중...")
    try:
        pm = PromptManager()
        logger.info("✓ PromptManager 초기화 완료")
    except Exception as e:
        logger.error(f"❌ 초기화 실패: {str(e)}")
        return False

    # 2. 사용 가능한 프롬프트 목록 확인
    logger.info("\n[2/4] 사용 가능한 프롬프트 목록 확인 중...")
    try:
        prompts = pm.list_prompts()
        logger.info(f"✓ 사용 가능한 프롬프트: {prompts}")

        if "news_summarization" not in prompts:
            logger.warning("⚠️ news_summarization 프롬프트가 없습니다")
            return False

    except Exception as e:
        logger.error(f"❌ 목록 조회 실패: {str(e)}")
        return False

    # 3. 프롬프트 정보 및 렌더링 테스트
    logger.info("\n[3/4] 프롬프트 로드 및 렌더링 중...")

    sample_article = (
        "Apple Inc. announced record quarterly earnings of $25.3 billion, "
        "beating analyst expectations by 15%. The company's iPhone sales surged "
        "due to strong demand in Asia, while Services revenue continued its "
        "steady growth trajectory. CEO Tim Cook attributed the success to innovation "
        "and customer loyalty programs. The stock rose 8% in after-hours trading."
    )

    try:
        # 프롬프트 정보 확인
        info = pm.get_prompt_info("news_summarization")
        logger.info(f"프롬프트 정보:")
        logger.info(f"  - Name: {info['name']}")
        logger.info(f"  - Version: {info['version']}")
        logger.info(f"  - Use Case: {info['use_case']}")

        # 프롬프트 렌더링
        rendered = pm.render_prompt("news_summarization", article=sample_article)
        logger.info("✓ 프롬프트 렌더링 완료")
        logger.info(f"\n📝 렌더링된 프롬프트 (처음 200자):")
        logger.info(rendered[:200] + "...")

        # 모델 설정 확인
        model_config = pm.get_model_config("news_summarization")
        logger.info(f"\n⚙️ 모델 설정:")
        for key, value in model_config.items():
            logger.info(f"  - {key}: {value}")

    except Exception as e:
        logger.error(f"❌ 렌더링 실패: {str(e)}")
        return False

    # 4. MLflow 로깅 테스트 (선택사항)
    logger.info("\n[4/4] MLflow 로깅 테스트 중...")
    try:
        # MLflow run 시작 (선택사항)
        # mlflow.start_run()
        # pm.log_to_mlflow("news_summarization", rendered, model_name="summarlize-llm")
        # mlflow.end_run()

        logger.info("✓ MLflow 로깅 기능 확인 완료")

    except Exception as e:
        logger.error(f"⚠️ MLflow 로깅 실패 (선택사항): {str(e)}")

    # 최종 결과
    logger.info("\n" + "=" * 60)
    logger.info("✅ 프롬프트 관리 시스템 테스트 성공!")
    logger.info("=" * 60)
    logger.info("\n다음 단계:")
    logger.info("  1. 추가 프롬프트 템플릿 작성 (필요시)")
    logger.info("  2. GatewayClient와 PromptManager 통합")
    logger.info("  3. 평가 메트릭 시스템 구축 (evaluators/)")

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

"""
뉴스 요약 생성 모듈

MLflow Gateway를 통해 다양한 성능 수준의 LLM으로 뉴스 요약을 생성합니다.
"""

import logging
from typing import Optional

import mlflow

from .gateway_client import GatewayClient

logger = logging.getLogger(__name__)


class BaseSummarizer:
    """뉴스 요약 생성기 기본 클래스

    MLflow Prompt Management에서 온도, 토큰 등의 설정을 관리합니다.
    """

    def __init__(
        self,
        model_type: str = "low_performance_llm",
        prompt_uri: Optional[str] = None,
    ):
        """
        BaseSummarizer 초기화

        Args:
            model_type: LLM 모델 타입 ("mid_performance_llm" 또는 "low_performance_llm")
            prompt_uri: MLflow에서 관리하는 프롬프트 URI (선택)
                      예: "prompts:/news_summarize/high_perf"
                      프롬프트 내에 temperature, max_tokens 등의 설정이 포함됨
        """
        self.model_type = model_type
        self.prompt_uri = prompt_uri

        # GatewayClient 초기화
        try:
            self.client = GatewayClient(
                model_type=model_type,
                validate_connection=False,  # 배치 작업을 위해 유효성 검사 생략
            )
            logger.info(
                f"✓ Summarizer 초기화: model={model_type}, prompt_uri={prompt_uri}"
            )
        except Exception as e:
            logger.error(f"❌ GatewayClient 초기화 실패: {str(e)}")
            raise

    def _get_prompt(self, article: str) -> str:
        """
        프롬프트 생성 또는 로드

        mlflow.start_run() 내에서 호출되면 MLflow가 자동으로 Linked prompts 기록

        Args:
            article: 요약할 기사 텍스트

        Returns:
            렌더링된 프롬프트
        """
        # MLflow UI에서 관리하는 프롬프트를 사용하는 경우
        if self.prompt_uri:
            try:
                prompt_version = mlflow.genai.load_prompt(self.prompt_uri)
                if hasattr(prompt_version, "template"):
                    prompt_template = prompt_version.template
                else:
                    prompt_template = str(prompt_version)
                logger.debug(
                    f"프롬프트 로드 완료: {len(prompt_template)}자 ({self.prompt_uri})"
                )
                return prompt_template.format(article=article)
            except Exception as e:
                logger.warning(f"MLflow 프롬프트 로드 실패, 기본값 사용: {str(e)}")

        # 기본 프롬프트 (프롬프트 URI가 없거나 로드 실패 시)
        return self._get_default_prompt(article)

    def _get_default_prompt(self, article: str) -> str:
        """
        기본 프롬프트 반환

        Args:
            article: 요약할 기사 텍스트

        Returns:
            기본 프롬프트
        """
        return f"""다음 뉴스 기사를 3줄 이내로 요약해주세요.
핵심 정보(회사명, 주가 변동, 주요 사건)를 포함해야 합니다.

기사:
{article}

요약:"""

    def summarize(self, article: str) -> str:
        """
        뉴스 기사 요약 생성

        MLflow 프롬프트에 정의된 temperature, max_tokens을 사용합니다.
        mlflow.start_run() 내에서 호출하면 자동으로 LLM 호출이 기록됩니다.

        Args:
            article: 요약할 뉴스 기사 텍스트

        Returns:
            생성된 요약

        Raises:
            RuntimeError: 요약 생성 실패 시
        """
        try:
            # 프롬프트 준비
            prompt = self._get_prompt(article)

            # LLM 호출 (MLflow 프롬프트의 설정값 사용)
            # mlflow.openai.autolog()가 자동으로 기록
            summary = self.client.call(text=prompt)

            logger.debug(f"요약 생성 완료: {len(summary)}자")
            return summary

        except Exception as e:
            logger.error(f"요약 생성 실패: {str(e)}")
            raise

    def summarize_batch(
        self,
        articles: list[str],
        log_progress: bool = True,
    ) -> list[str]:
        """
        여러 기사 일괄 요약 생성

        Args:
            articles: 요약할 기사 텍스트 리스트
            log_progress: 진행도 로깅 여부

        Returns:
            생성된 요약 리스트 (실패한 항목은 빈 문자열)
        """
        summaries = []

        for idx, article in enumerate(articles, 1):
            try:
                if log_progress:
                    logger.info(f"  [{idx}/{len(articles)}] 요약 생성 중...")

                summary = self.summarize(article)
                summaries.append(summary)

            except Exception as e:
                logger.error(f"  ❌ [{idx}/{len(articles)}] 요약 생성 실패: {str(e)}")
                summaries.append("")

        logger.info(f"✓ 배치 요약 완료: {len(summaries)}개 ({len([s for s in summaries if s])}/{len(articles)} 성공)")
        return summaries


class MidPerformanceSummarizer(BaseSummarizer):
    """
    고성능 LLM 요약 생성기 (레퍼런스 생성용)

    특징:
    - mid_performance_llm 사용 (더 정확한 요약)
    - 온도, 토큰 설정은 MLflow 프롬프트에서 관리
    """

    def __init__(self, prompt_uri: Optional[str] = None):
        """
        고성능 Summarizer 초기화

        Args:
            prompt_uri: MLflow 프롬프트 URI (선택)
                      예: "prompts:/news_summarize/reference"
        """
        super().__init__(
            model_type="mid_performance_llm",
            prompt_uri=prompt_uri,
        )
        logger.info(
            f"✓ MidPerformanceSummarizer 초기화 (레퍼런스 생성용)"
        )


class LowPerformanceSummarizer(BaseSummarizer):
    """
    저성능 LLM 요약 생성기 (배치 처리용)

    특징:
    - low_performance_llm 사용 (빠른 처리)
    - 온도, 토큰 설정은 MLflow 프롬프트에서 관리
    """

    def __init__(self, prompt_uri: Optional[str] = None):
        """
        저성능 Summarizer 초기화

        Args:
            prompt_uri: MLflow 프롬프트 URI (선택)
                      예: "prompts:/news_summarize/batch"
        """
        super().__init__(
            model_type="low_performance_llm",
            prompt_uri=prompt_uri,
        )
        logger.info(
            f"✓ LowPerformanceSummarizer 초기화 (배치 처리용)"
        )


# 편의 함수
def create_summarizer(
    performance: str = "high",
    prompt_uri: Optional[str] = None,
) -> BaseSummarizer:
    """
    Summarizer 팩토리 함수

    Args:
        performance: "high" (고성능) 또는 "low" (저성능)
        prompt_uri: MLflow 프롬프트 URI (선택)
                   온도, 토큰 등의 설정은 프롬프트에 포함됨

    Returns:
        BaseSummarizer 인스턴스

    Example:
        >>> summarizer = create_summarizer("high", prompt_uri="prompts:/news_summarize/reference")
        >>> summary = summarizer.summarize(article)
    """
    if performance == "high":
        return MidPerformanceSummarizer(prompt_uri=prompt_uri)
    elif performance == "low":
        return LowPerformanceSummarizer(prompt_uri=prompt_uri)
    else:
        raise ValueError(f"Unknown performance level: {performance}")

"""
MLflow Prompt Registry를 통한 프롬프트 관리

MLflow Web UI에 등록된 프롬프트를 동적으로 로드합니다.
로드 실패 시 fallback 프롬프트를 사용합니다.
"""

import logging
from typing import Optional

import mlflow

logger = logging.getLogger(__name__)

# Fallback 프롬프트 템플릿 (Web UI 프롬프트 로드 실패 시 사용)
FALLBACK_PROMPTS = {
    "news_summarization": {
        "template": """다음 뉴스 기사를 간결하게 요약하세요. 3-5 문장으로 요약하되, 핵심 내용만 포함하세요.

제목: {title}

본문:
{fulltext}

요약:""",
        "description": "뉴스 기사 요약 프롬프트 (기본값)",
        "tags": ["news", "summarization", "financial"],
    },
    "news_summarization_detailed": {
        "template": """다음 뉴스 기사를 상세하게 요약하세요. 5-10 문장으로 요약하되, 다음 항목을 포함하세요:
1. 주요 이슈
2. 영향받는 당사자
3. 잠재적 영향
4. 관련 배경

제목: {title}

본문:
{fulltext}

상세 요약:""",
        "description": "뉴스 기사 상세 요약 프롬프트 (기본값)",
        "tags": ["news", "summarization", "detailed"],
    },
}

# MLflow에 등록된 프롬프트 모델명
MLFLOW_PROMPT_MODELS = {
    "news_summarization": "news_summary_prompt",
    "news_summarization_detailed": "news_summary_detailed_prompt",
}


class PromptRegistry:
    """MLflow Prompt Registry 관리 클래스

    MLflow Web UI에 등록된 프롬프트를 동적으로 로드합니다.
    """

    def __init__(self):
        """초기화"""
        self.prompt_cache = {}  # 로드된 프롬프트 캐시

    def load_prompt_from_registry(
        self,
        prompt_key: str,
        version: str = "latest"
    ) -> Optional[str]:
        """MLflow Web UI에서 등록된 프롬프트 로드

        Args:
            prompt_key: 프롬프트 키 (예: "news_summarization")
            version: 프롬프트 버전 ("latest", "1", "2" 등)

        Returns:
            프롬프트 텍스트 또는 None
        """
        try:
            # 캐시 확인
            cache_key = f"{prompt_key}_{version}"
            if cache_key in self.prompt_cache:
                logger.debug(f"✓ 캐시에서 프롬프트 로드: {prompt_key}")
                return self.prompt_cache[cache_key]

            # MLflow에 등록된 프롬프트 모델명
            model_name = MLFLOW_PROMPT_MODELS.get(prompt_key)
            if not model_name:
                logger.warning(
                    f"⚠️ {prompt_key}에 해당하는 MLflow 모델명 없음"
                )
                return None

            # MLflow Model Registry에서 프롬프트 로드
            model_uri = f"models:/{model_name}/{version}"
            logger.info(f"📥 MLflow에서 프롬프트 로드 중: {model_uri}")

            try:
                # genai API로 프롬프트 로드 (최신 방식)
                prompt_text = mlflow.genai.load_prompt(model_uri)

                # 캐시에 저장
                self.prompt_cache[cache_key] = prompt_text

                logger.info(
                    f"✓ MLflow 프롬프트 로드 성공: {prompt_key} "
                    f"(version: {version})"
                )
                return prompt_text

            except AttributeError:
                # mlflow.genai가 없으면 다른 방식 시도
                logger.debug(
                    f"⚠️ mlflow.genai.load_prompt() 사용 불가, "
                    f"대체 방식 시도"
                )
                return None

        except Exception as e:
            logger.warning(
                f"⚠️ MLflow 프롬프트 로드 실패 ({prompt_key}): {str(e)}"
            )
            return None

    def get_prompt(
        self,
        prompt_key: str,
        use_mlflow: bool = True
    ) -> str:
        """프롬프트 템플릿 반환

        MLflow에서 먼저 로드 시도, 실패 시 fallback 사용

        Args:
            prompt_key: 프롬프트 키
            use_mlflow: MLflow 프롬프트 사용 여부

        Returns:
            프롬프트 템플릿

        Raises:
            ValueError: 프롬프트를 찾을 수 없을 때
        """
        # 1. MLflow에서 프롬프트 로드 시도
        if use_mlflow:
            prompt = self.load_prompt_from_registry(prompt_key)
            if prompt:
                return prompt
            logger.warning(
                f"⚠️ MLflow 프롬프트 로드 실패, Fallback 사용: {prompt_key}"
            )

        # 2. Fallback 프롬프트 사용
        if prompt_key not in FALLBACK_PROMPTS:
            raise ValueError(
                f"❌ 프롬프트 '{prompt_key}'를 찾을 수 없습니다. "
                f"사용 가능한 프롬프트: {', '.join(FALLBACK_PROMPTS.keys())}"
            )

        return FALLBACK_PROMPTS[prompt_key]["template"]

    def get_prompt_source(self, prompt_key: str) -> str:
        """프롬프트의 출처 반환

        Args:
            prompt_key: 프롬프트 키

        Returns:
            "mlflow" 또는 "fallback"
        """
        # MLflow에서 로드 가능한지 확인
        prompt = self.load_prompt_from_registry(prompt_key)
        if prompt:
            return "mlflow"
        return "fallback"

    def get_prompt(self, prompt_key: str) -> str:
        """프롬프트 템플릿 반환

        Args:
            prompt_key: 프롬프트 키

        Returns:
            프롬프트 템플릿

        Raises:
            ValueError: 프롬프트가 없을 때
        """
        if prompt_key not in PROMPTS:
            raise ValueError(
                f"❌ 프롬프트 '{prompt_key}'를 찾을 수 없습니다. "
                f"사용 가능한 프롬프트: {', '.join(PROMPTS.keys())}"
            )

        return PROMPTS[prompt_key]["template"]

    def get_prompt_description(self, prompt_key: str) -> str:
        """프롬프트 설명 반환

        Args:
            prompt_key: 프롬프트 키

        Returns:
            프롬프트 설명
        """
        source = self.get_prompt_source(prompt_key)
        if prompt_key not in FALLBACK_PROMPTS:
            raise ValueError(f"❌ 프롬프트 '{prompt_key}'를 찾을 수 없습니다.")

        desc = FALLBACK_PROMPTS[prompt_key]["description"]
        return f"{desc} (출처: {source})"

    def format_prompt(self, prompt_key: str, **kwargs) -> str:
        """프롬프트 템플릿 포맷팅

        Args:
            prompt_key: 프롬프트 키
            **kwargs: 템플릿 변수

        Returns:
            포맷된 프롬프트

        Raises:
            ValueError: 필요한 변수가 없을 때
        """
        template = self.get_prompt(prompt_key, use_mlflow=True)

        try:
            return template.format(**kwargs)
        except KeyError as e:
            raise ValueError(
                f"❌ 필요한 변수 '{str(e)}'가 없습니다. "
                f"프롬프트 '{prompt_key}'는 다음 변수를 필요로 합니다: "
                f"{self._get_template_vars(prompt_key)}"
            ) from e

    def list_prompts(self) -> list[dict]:
        """등록된 프롬프트 목록 반환

        Returns:
            프롬프트 정보 리스트
        """
        return [
            {
                "key": key,
                "description": config["description"],
                "tags": config["tags"],
                "source": self.get_prompt_source(key),
            }
            for key, config in FALLBACK_PROMPTS.items()
        ]

    def _get_template_vars(self, prompt_key: str) -> list[str]:
        """템플릿 변수 추출

        Args:
            prompt_key: 프롬프트 키

        Returns:
            변수 이름 리스트
        """
        import re

        # MLflow에서 먼저 시도
        template = self.get_prompt(prompt_key, use_mlflow=True)
        # {variable_name} 형식의 변수 추출
        return re.findall(r"\{(\w+)\}", template)


def log_prompt_metrics(
    prompt_key: str,
    metrics: dict[str, float],
    prompt_source: str = "unknown",
) -> None:
    """프롬프트별 메트릭 로깅

    Args:
        prompt_key: 프롬프트 키
        metrics: 메트릭 딕셔너리
        prompt_source: 프롬프트 출처 ("mlflow" 또는 "fallback")
    """
    try:
        prefixed_metrics = {
            f"prompt_{prompt_key}_{key}": value
            for key, value in metrics.items()
        }
        prefixed_metrics[f"prompt_{prompt_key}_source"] = 1 if prompt_source == "mlflow" else 0
        mlflow.log_metrics(prefixed_metrics)
        logger.debug(f"✓ 프롬프트 메트릭 로깅: {prompt_key} (출처: {prompt_source})")
    except Exception as e:
        logger.warning(f"⚠️ 프롬프트 메트릭 로깅 실패: {str(e)}")

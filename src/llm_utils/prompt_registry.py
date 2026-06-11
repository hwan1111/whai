"""
MLflow Prompt Registry - 완전 동적 프롬프트 관리

모든 프롬프트는 MLflow Web UI Model Registry에서 관리됩니다.
코드에는 하드코딩된 프롬프트가 없습니다. (완전 동적 연동)
"""

import logging
from typing import Optional

import mlflow

logger = logging.getLogger(__name__)

# MLflow Model Registry에 등록된 프롬프트 모델명 매핑
# Web UI의 프롬프트 모델명을 정의합니다
MLFLOW_PROMPT_MODELS = {
    "news_summarization": "news_summary_prompt",
    "news_summarization_detailed": "news_summary_detailed_prompt",
}


class PromptRegistry:
    """MLflow Prompt Registry 관리 클래스 (완전 동적 연동)

    모든 프롬프트는 MLflow Web UI Model Registry에서 관리됩니다.
    코드에는 하드코딩된 프롬프트가 없습니다.
    """

    def __init__(self):
        """초기화"""
        self.prompt_cache = {}  # 로드된 프롬프트 캐시

    def load_prompt(self, prompt_key: str, version: str = "latest") -> str:
        """MLflow Web UI에서 프롬프트 로드 (완전 동적)

        Args:
            prompt_key: 프롬프트 키 (예: "news_summarization")
            version: 프롬프트 버전 ("latest", "1", "2" 등)

        Returns:
            프롬프트 텍스트

        Raises:
            ValueError: 프롬프트를 찾을 수 없을 때
        """
        # 캐시 확인
        cache_key = f"{prompt_key}_{version}"
        if cache_key in self.prompt_cache:
            logger.debug(f"✓ 캐시에서 프롬프트 로드: {prompt_key}")
            return self.prompt_cache[cache_key]

        # MLflow에 등록된 프롬프트 모델명
        model_name = MLFLOW_PROMPT_MODELS.get(prompt_key)
        if not model_name:
            raise ValueError(
                f"❌ 프롬프트 '{prompt_key}'가 정의되지 않았습니다.\n"
                f"MLFLOW_PROMPT_MODELS에 추가하세요:\n"
                f"   MLFLOW_PROMPT_MODELS['{prompt_key}'] = 'mlflow_model_name'"
            )

        # MLflow Model Registry에서 프롬프트 로드
        model_uri = f"models:/{model_name}/{version}"
        logger.info(f"📥 MLflow에서 프롬프트 로드 중: {model_uri}")

        try:
            # genai API로 프롬프트 로드
            prompt_text = mlflow.genai.load_prompt(model_uri)

            # 캐시에 저장
            self.prompt_cache[cache_key] = prompt_text

            logger.info(
                f"✅ MLflow 프롬프트 로드 성공: {prompt_key} "
                f"(version: {version})"
            )
            return prompt_text

        except AttributeError as e:
            raise RuntimeError(
                f"❌ MLflow GenAI API를 사용할 수 없습니다.\n"
                f"필요 패키지: pip install mlflow[genai]\n"
                f"오류: {str(e)}"
            ) from e

        except Exception as e:
            raise ValueError(
                f"❌ MLflow Web UI에서 프롬프트를 찾을 수 없습니다.\n"
                f"모델명: {model_name}\n"
                f"버전: {version}\n"
                f"MLflow UI 링크: http://52.78.237.104:5001\n"
                f"→ Model Registry → {model_name} 에서 프롬프트를 등록하세요\n"
                f"오류: {str(e)}"
            ) from e

    def format_prompt(self, prompt_key: str, **kwargs) -> str:
        """프롬프트 템플릿 포맷팅 (완전 동적)

        Args:
            prompt_key: 프롬프트 키
            **kwargs: 템플릿 변수

        Returns:
            포맷된 프롬프트

        Raises:
            ValueError: 프롬프트를 찾을 수 없거나 변수가 없을 때
        """
        # MLflow에서 프롬프트 로드 (실패하면 에러 발생)
        template = self.load_prompt(prompt_key)

        try:
            formatted = template.format(**kwargs)
            return formatted
        except KeyError as e:
            raise ValueError(
                f"❌ 필요한 변수 '{str(e)}'가 없습니다.\n"
                f"프롬프트 '{prompt_key}'에서 찾은 변수: {self._get_template_vars(template)}"
            ) from e

    def list_available_prompts(self) -> list[str]:
        """등록된 프롬프트 키 목록

        Returns:
            프롬프트 키 리스트
        """
        return list(MLFLOW_PROMPT_MODELS.keys())

    @staticmethod
    def _get_template_vars(template: str) -> list[str]:
        """템플릿 변수 추출

        Args:
            template: 프롬프트 템플릿 텍스트

        Returns:
            변수 이름 리스트
        """
        import re
        # {variable_name} 형식의 변수 추출
        return re.findall(r"\{(\w+)\}", template)


def log_prompt_metrics(
    prompt_key: str,
    metrics: dict[str, float],
) -> None:
    """프롬프트별 메트릭 로깅

    Args:
        prompt_key: 프롬프트 키
        metrics: 메트릭 딕셔너리
    """
    try:
        prefixed_metrics = {
            f"prompt_{prompt_key}_{key}": value
            for key, value in metrics.items()
        }
        mlflow.log_metrics(prefixed_metrics)
        logger.debug(f"✓ 프롬프트 메트릭 로깅: {prompt_key}")
    except Exception as e:
        logger.warning(f"⚠️ 프롬프트 메트릭 로깅 실패: {str(e)}")

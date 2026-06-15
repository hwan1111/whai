"""
MLflow Prompt Registry - 완전 동적 프롬프트 관리

모든 프롬프트는 MLflow Web UI Model Registry에서 관리됩니다.
코드에는 하드코딩된 프롬프트가 없습니다. (완전 동적 연동)
"""

import logging
from typing import Optional

import mlflow

logger = logging.getLogger(__name__)

# ============================================================================
# 🎯 프롬프트 설정 (이 부분만 수정하면 됨!)
# ============================================================================
# 형식: "코드에서_사용할_키": {"name": "MLflow_프롬프트_이름", "version": "버전"}
#
# 예시:
#   "news_summarization": {
#       "name": "news_summary_prompt",      # MLflow에 등록된 프롬프트 이름
#       "version": "latest"                 # 또는 "1", "2" 등 특정 버전
#   }
MLFLOW_PROMPTS_CONFIG = {
    "news_summarization": {
        "name": "regime_news_summarys",
        "version": "2",  # 구체적인 버전 번호 사용
    },
    # TODO(owner): MLflow UI에서 portfolio_analysis 프롬프트를 등록한 뒤
    #   아래 name/version 을 실제 등록값으로 확정할 것 (현재는 placeholder).
    #   등록된 프롬프트 URI: prompts:/portfolio_analysis/1
    "portfolio_analysis": {
        "name": "portfolio_analysis",
        "version": "3",
    },
    # 포트폴리오 분석 결과(출력)를 입력으로 받아 근거 뉴스 링크를 찾는 프롬프트.
    # MLflow UI 에서 portfolio_news_evidence 프롬프트(Chat)를 등록한 뒤 version 을 확정할 것.
    "portfolio_news_evidence": {
        "name": "portfolio_news_evidence",
        "version": "1",
    },
}


class PromptRegistry:
    """MLflow Prompt Registry 관리 클래스 (완전 동적 연동)

    모든 프롬프트는 MLflow Web UI Model Registry에서 관리됩니다.
    코드에는 하드코딩된 프롬프트가 없습니다.
    """

    def __init__(self):
        """초기화"""
        self.prompt_cache = {}  # 로드된 프롬프트 캐시

    def load_prompt(self, prompt_key: str, version: Optional[str] = None) -> str:
        """MLflow Prompts Registry에서 프롬프트 로드

        Args:
            prompt_key: 프롬프트 키 (예: "news_summarization")
            version: 버전 (None이면 설정값 사용, 또는 "latest", "1" 등)

        Returns:
            프롬프트 텍스트

        Raises:
            ValueError: 프롬프트를 찾을 수 없을 때
        """
        # 캐시 확인
        cache_key = f"{prompt_key}_{version or 'default'}"
        if cache_key in self.prompt_cache:
            logger.debug(f"✓ 캐시에서 프롬프트 로드: {prompt_key}")
            return self.prompt_cache[cache_key]

        # 1. 설정에 정의된 프롬프트인지 확인
        if prompt_key not in MLFLOW_PROMPTS_CONFIG:
            available = list(MLFLOW_PROMPTS_CONFIG.keys())
            raise ValueError(
                f"❌ 프롬프트 '{prompt_key}'가 설정에 없습니다.\n\n"
                f"📌 해결 방법:\n"
                f"   파일: src/llm_utils/prompt_registry.py\n"
                f"   MLFLOW_PROMPTS_CONFIG에 추가:\n"
                f"   '{prompt_key}': {{\n"
                f"       'name': 'MLflow_프롬프트_이름',\n"
                f"       'version': 'latest'\n"
                f"   }}\n\n"
                f"현재 정의된 프롬프트: {available}"
            )

        config = MLFLOW_PROMPTS_CONFIG[prompt_key]
        mlflow_name = config.get("name")
        mlflow_version = version or config.get("version", "latest")

        logger.info(f"📥 MLflow에서 프롬프트 로드 중: {mlflow_name} (version: {mlflow_version})")

        try:
            from mlflow.client import MlflowClient
            client = MlflowClient()

            # MLflow Prompts API로 프롬프트 객체 로드
            if mlflow_version.lower() == "latest":
                prompt = client.get_prompt(mlflow_name)
            else:
                prompt = client.get_prompt(mlflow_name, version=int(mlflow_version))

            prompt_text = prompt.text if hasattr(prompt, 'text') else str(prompt)

            # 캐시에 저장
            self.prompt_cache[cache_key] = prompt_text

            logger.info(f"✅ MLflow 프롬프트 로드 성공: {prompt_key}")
            return prompt_text

        except Exception as e:
            raise ValueError(
                f"❌ MLflow에서 프롬프트를 찾을 수 없습니다.\n\n"
                f"설정 정보:\n"
                f"  - 코드 키: '{prompt_key}'\n"
                f"  - MLflow 이름: '{mlflow_name}'\n"
                f"  - 버전: '{mlflow_version}'\n\n"
                f"📌 확인 사항:\n"
                f"1. MLflow UI에서 프롬프트 확인:\n"
                f"   http://52.78.237.104:5001/#/prompts\n\n"
                f"2. 설정 파일 확인:\n"
                f"   src/llm_utils/prompt_registry.py\n"
                f"   MLFLOW_PROMPTS_CONFIG 딕셔너리\n\n"
                f"3. MLflow 서버 연결 상태\n\n"
                f"오류: {str(e)}"
            ) from e

    def format_prompt(self, prompt_key: str, **kwargs) -> tuple[str, str]:
        """프롬프트 템플릿 포맷팅

        MLflow genai API를 사용하여 프롬프트를 로드하고 포맷합니다.

        Args:
            prompt_key: 프롬프트 키
            **kwargs: 템플릿 변수

        Returns:
            (포맷된 프롬프트 텍스트, 프롬프트 URI) 튜플

        Raises:
            ValueError: 프롬프트를 찾을 수 없거나 필수 변수가 없을 때
        """
        try:
            # 설정에서 프롬프트 정보 가져오기
            if prompt_key not in MLFLOW_PROMPTS_CONFIG:
                available = list(MLFLOW_PROMPTS_CONFIG.keys())
                raise ValueError(
                    f"❌ 프롬프트 '{prompt_key}'가 설정에 없습니다.\n"
                    f"정의된 프롬프트: {available}"
                )

            config = MLFLOW_PROMPTS_CONFIG[prompt_key]
            mlflow_name = config.get("name")
            mlflow_version = config.get("version", "latest")

            # MLflow genai API로 프롬프트 로드
            # 형식: prompts:/name/version 또는 prompts:/name@alias
            prompt_uri = f"prompts:/{mlflow_name}/{mlflow_version}"
            logger.info(f"📥 MLflow 프롬프트 로드 중: {prompt_uri}")

            prompt_template = mlflow.genai.load_prompt(prompt_uri)

            # prompt.format(**kwargs)로 변수 대입 → Prompt 객체 반환됨
            formatted = prompt_template.format(**kwargs)

            # Prompt 객체에서 실제 텍스트 추출
            prompt_text = formatted.text if hasattr(formatted, "text") else str(formatted)

            logger.info(f"✅ 프롬프트 포맷팅 완료: {prompt_key} (길이: {len(prompt_text)}자)")
            return prompt_text, prompt_uri

        except Exception as e:
            error_msg = f"❌ 프롬프트 로드/포맷팅 실패: {str(e)}"
            logger.error(error_msg)
            raise ValueError(error_msg) from e

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

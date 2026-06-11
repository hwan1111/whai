"""
MLflow Prompt Registry를 통한 프롬프트 관리

프롬프트 템플릿을 MLflow에 등록하고 버전 관리합니다.
"""

import logging
from typing import Optional

import mlflow
from mlflow.entities.model_registry import ModelVersion

logger = logging.getLogger(__name__)

# 프롬프트 템플릿
PROMPTS = {
    "news_summarization": {
        "template": """다음 뉴스 기사를 간결하게 요약하세요. 3-5 문장으로 요약하되, 핵심 내용만 포함하세요.

제목: {title}

본문:
{fulltext}

요약:""",
        "description": "뉴스 기사 요약 프롬프트",
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
        "description": "뉴스 기사 상세 요약 프롬프트",
        "tags": ["news", "summarization", "detailed"],
    },
}


class PromptRegistry:
    """MLflow Prompt Registry 관리 클래스"""

    def __init__(self):
        """초기화"""
        self.model_name = "news_summarization_prompt"

    def register_prompts(self) -> None:
        """모든 프롬프트를 MLflow에 등록"""
        try:
            logger.info("📝 프롬프트 등록 시작...")

            for prompt_key, prompt_config in PROMPTS.items():
                self._register_single_prompt(
                    prompt_key=prompt_key,
                    template=prompt_config["template"],
                    description=prompt_config["description"],
                    tags=prompt_config["tags"],
                )

            logger.info("✅ 모든 프롬프트 등록 완료")

        except Exception as e:
            logger.error(f"❌ 프롬프트 등록 실패: {str(e)}")
            raise

    def _register_single_prompt(
        self,
        prompt_key: str,
        template: str,
        description: str,
        tags: list[str],
    ) -> None:
        """단일 프롬프트 등록

        Args:
            prompt_key: 프롬프트 키
            template: 프롬프트 템플릿
            description: 프롬프트 설명
            tags: 태그 리스트
        """
        try:
            # 메타데이터 저장
            artifact_path = f"prompts/{prompt_key}"

            # MLflow에 프롬프트 저장
            # (간단한 구현: 프롬프트 정보를 로그)
            with mlflow.start_run(run_name=f"register_prompt_{prompt_key}"):
                # 프롬프트 텍스트 저장
                mlflow.log_text(
                    text=template,
                    artifact_file=f"{artifact_path}/template.txt"
                )

                # 메타데이터 저장
                mlflow.log_dict(
                    {
                        "prompt_key": prompt_key,
                        "description": description,
                        "tags": tags,
                        "template": template,
                    },
                    artifact_file=f"{artifact_path}/metadata.json"
                )

                # 파라미터로도 기록
                mlflow.log_params({
                    "prompt_key": prompt_key,
                    "num_tags": len(tags),
                })

            logger.info(
                f"✓ 프롬프트 등록: {prompt_key} "
                f"(tags: {', '.join(tags)})"
            )

        except Exception as e:
            logger.warning(f"⚠️ 프롬프트 등록 실패 ({prompt_key}): {str(e)}")

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
        if prompt_key not in PROMPTS:
            raise ValueError(f"❌ 프롬프트 '{prompt_key}'를 찾을 수 없습니다.")

        return PROMPTS[prompt_key]["description"]

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
        template = self.get_prompt(prompt_key)

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
            }
            for key, config in PROMPTS.items()
        ]

    @staticmethod
    def _get_template_vars(prompt_key: str) -> list[str]:
        """템플릿 변수 추출

        Args:
            prompt_key: 프롬프트 키

        Returns:
            변수 이름 리스트
        """
        import re

        template = PROMPTS[prompt_key]["template"]
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

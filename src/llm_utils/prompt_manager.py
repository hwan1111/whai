"""
프롬프트 관리 시스템

YAML 기반 프롬프트 템플릿을 로드하고, 파라미터를 주입하며, MLflow에 자동으로 기록합니다.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

import mlflow
import yaml

logger = logging.getLogger(__name__)


class PromptManager:
    """YAML 기반 프롬프트 관리"""

    def __init__(self, prompts_dir: Optional[Path] = None):
        """
        PromptManager 초기화

        Args:
            prompts_dir: 프롬프트 YAML 파일들이 위치한 디렉토리
                        기본값: model/llm/prompts/
        """
        if prompts_dir is None:
            # 프로젝트 루트 기준으로 prompts 디렉토리 설정
            project_root = Path(__file__).parent.parent.parent
            prompts_dir = project_root / "model" / "llm" / "prompts"

        self.prompts_dir = prompts_dir
        self._prompts_cache: Dict[str, Dict[str, Any]] = {}

        if not self.prompts_dir.exists():
            logger.warning(
                f"⚠️ 프롬프트 디렉토리가 없습니다: {self.prompts_dir}"
            )
        else:
            logger.info(f"✓ 프롬프트 디렉토리: {self.prompts_dir}")

    def load_prompt(self, prompt_name: str) -> Dict[str, Any]:
        """
        YAML 파일에서 프롬프트 로드

        Args:
            prompt_name: 프롬프트 이름 (파일명 without .yaml)
                        예: "news_summarization"

        Returns:
            프롬프트 메타데이터 및 템플릿

        Raises:
            FileNotFoundError: 프롬프트 파일을 찾을 수 없을 때
            yaml.YAMLError: YAML 파싱 실패 시
        """
        # 캐시 확인
        if prompt_name in self._prompts_cache:
            logger.debug(f"캐시에서 로드: {prompt_name}")
            return self._prompts_cache[prompt_name]

        # 파일 경로
        prompt_file = self.prompts_dir / f"{prompt_name}.yaml"

        if not prompt_file.exists():
            raise FileNotFoundError(
                f"❌ 프롬프트 파일을 찾을 수 없습니다: {prompt_file}"
            )

        # YAML 파일 로드
        try:
            with open(prompt_file, "r", encoding="utf-8") as f:
                prompt_config = yaml.safe_load(f)

            logger.info(f"✓ 프롬프트 로드: {prompt_name} (v{prompt_config.get('version')})")

            # 캐시에 저장
            self._prompts_cache[prompt_name] = prompt_config

            return prompt_config

        except yaml.YAMLError as e:
            raise yaml.YAMLError(
                f"❌ YAML 파싱 실패 ({prompt_name}): {str(e)}"
            ) from e

    def render_prompt(
        self,
        prompt_name: str,
        **kwargs: Any,
    ) -> str:
        """
        프롬프트 템플릿에 파라미터를 주입하여 최종 프롬프트 생성

        Args:
            prompt_name: 프롬프트 이름
            **kwargs: 템플릿 파라미터
                     예: article="뉴스 기사 내용"

        Returns:
            렌더링된 프롬프트 (최종 LLM 입력)

        Raises:
            KeyError: 필수 파라미터가 없을 때
            ValueError: 파라미터 형식이 잘못되었을 때
        """
        # 프롬프트 로드
        prompt_config = self.load_prompt(prompt_name)

        # 필수 파라미터 검증
        parameters = prompt_config.get("parameters", {})
        for param_name, param_info in parameters.items():
            if param_info.get("required", False) and param_name not in kwargs:
                raise KeyError(
                    f"❌ 필수 파라미터가 누락되었습니다: {param_name}"
                )

        # 템플릿 렌더링
        template = prompt_config.get("template", "")
        try:
            rendered_prompt = template.format(**kwargs)
            logger.debug(f"프롬프트 렌더링 완료: {prompt_name}")
            return rendered_prompt
        except KeyError as e:
            raise KeyError(
                f"❌ 템플릿 파라미터 오류: {str(e)}"
            ) from e

    def get_model_config(self, prompt_name: str) -> Dict[str, Any]:
        """
        프롬프트의 LLM 모델 설정 반환

        Args:
            prompt_name: 프롬프트 이름

        Returns:
            model_config (temperature, max_tokens 등)
        """
        prompt_config = self.load_prompt(prompt_name)
        return prompt_config.get("model_config", {})

    def log_to_mlflow(
        self,
        prompt_name: str,
        rendered_prompt: str,
        model_name: Optional[str] = None,
    ) -> None:
        """
        프롬프트 사용 정보를 MLflow에 로깅

        Args:
            prompt_name: 프롬프트 이름
            rendered_prompt: 렌더링된 최종 프롬프트
            model_name: 사용한 모델 이름 (선택사항)
        """
        try:
            prompt_config = self.load_prompt(prompt_name)

            # MLflow에 프롬프트 정보 로깅
            mlflow.log_param("prompt_name", prompt_name)
            mlflow.log_param("prompt_version", prompt_config.get("version", "unknown"))
            mlflow.log_param("prompt_use_case", prompt_config.get("use_case", "unknown"))

            if model_name:
                mlflow.log_param("llm_model", model_name)

            # 모델 설정 로깅
            model_config = self.get_model_config(prompt_name)
            for key, value in model_config.items():
                mlflow.log_param(f"llm_{key}", value)

            logger.debug(f"MLflow에 프롬프트 로깅: {prompt_name}")

        except Exception as e:
            logger.warning(f"⚠️ MLflow 로깅 실패: {str(e)}")

    def get_prompt_info(self, prompt_name: str) -> Dict[str, Any]:
        """
        프롬프트 메타데이터 반환

        Args:
            prompt_name: 프롬프트 이름

        Returns:
            name, version, description, domain, metadata 등
        """
        prompt_config = self.load_prompt(prompt_name)

        return {
            "name": prompt_config.get("name"),
            "version": prompt_config.get("version"),
            "description": prompt_config.get("description"),
            "domain": prompt_config.get("domain"),
            "use_case": prompt_config.get("use_case"),
            "metadata": prompt_config.get("metadata", {}),
        }

    def list_prompts(self) -> list[str]:
        """
        사용 가능한 모든 프롬프트 목록 반환

        Returns:
            프롬프트 이름 리스트
        """
        if not self.prompts_dir.exists():
            return []

        prompt_files = self.prompts_dir.glob("*.yaml")
        prompts = [f.stem for f in prompt_files]

        logger.info(f"사용 가능한 프롬프트: {', '.join(prompts)}")
        return sorted(prompts)

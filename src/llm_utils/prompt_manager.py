"""
프롬프트 관리 시스템

YAML 기반 프롬프트 템플릿을 로드하고, 파라미터를 주입하며, MLflow에 자동으로 기록합니다.
프롬프트를 MLflow 레지스트리에 등록하여 /prompts에서 관리하고,
run 실행 시 자동으로 Linked prompts에 추적됩니다.
"""

import hashlib
import json
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
        self._mlflow_registry: Dict[str, Dict[str, Any]] = {}  # 등록된 프롬프트 메타데이터

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

    def _compute_file_hash(self, prompt_name: str) -> str:
        """
        프롬프트 YAML 파일의 SHA-256 해시 계산
        (파일 변경 감지용)

        Args:
            prompt_name: 프롬프트 이름

        Returns:
            파일의 SHA-256 해시 (처음 16자)
        """
        prompt_file = self.prompts_dir / f"{prompt_name}.yaml"

        if not prompt_file.exists():
            return ""

        try:
            with open(prompt_file, "rb") as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()[:16]
            return file_hash
        except Exception as e:
            logger.warning(f"⚠️ 파일 해시 계산 실패 ({prompt_name}): {str(e)}")
            return ""

    def _should_update_in_mlflow(self, prompt_name: str) -> bool:
        """
        MLflow에 등록된 프롬프트를 업데이트해야 하는지 판단
        (버전 또는 파일 해시가 다르면 True)

        Args:
            prompt_name: 프롬프트 이름

        Returns:
            업데이트 필요 여부
        """
        try:
            prompt_config = self.load_prompt(prompt_name)
            current_version = prompt_config.get("version", "0.0.0")
            current_hash = self._compute_file_hash(prompt_name)

            # 레지스트리에 저장된 메타데이터 확인
            if prompt_name not in self._mlflow_registry:
                return True

            registry_info = self._mlflow_registry[prompt_name]
            previous_version = registry_info.get("version")
            previous_hash = registry_info.get("file_hash")

            # 버전 또는 해시가 다르면 업데이트 필요
            if current_version != previous_version or current_hash != previous_hash:
                logger.debug(
                    f"프롬프트 업데이트 감지 ({prompt_name}): "
                    f"v{previous_version}→v{current_version}"
                )
                return True

            return False

        except Exception as e:
            logger.warning(
                f"⚠️ 업데이트 여부 판단 실패 ({prompt_name}): {str(e)}"
            )
            return True

    def register_prompt_to_mlflow(self, prompt_name: str) -> str:
        """
        YAML 프롬프트를 MLflow 레지스트리에 등록
        파일이 변경되었을 때만 업데이트 수행

        Args:
            prompt_name: 프롬프트 이름

        Returns:
            등록된 프롬프트의 URI (prompts:/<name>@<version>)

        Raises:
            FileNotFoundError: 프롬프트 파일을 찾을 수 없을 때
        """
        try:
            # 업데이트 필요 여부 확인
            if not self._should_update_in_mlflow(prompt_name):
                registered_info = self._mlflow_registry.get(prompt_name, {})
                uri = registered_info.get("mlflow_uri", f"prompts:/{prompt_name}@latest")
                logger.debug(f"✓ 프롬프트 이미 등록됨 (변경 없음): {uri}")
                return uri

            # 프롬프트 로드
            prompt_config = self.load_prompt(prompt_name)
            version = prompt_config.get("version", "1.0.0")
            template = prompt_config.get("template", "")
            description = prompt_config.get("description", "")
            metadata = prompt_config.get("metadata", {})

            # MLflow에 프롬프트 등록
            # 공식 문서: https://mlflow.org/docs/latest/genai/prompt-registry/use-prompts-in-apps/
            try:
                mlflow.genai.register_prompt(
                    name=prompt_name,
                    template=template,  # 공식 파라미터명
                    commit_message=f"Register {prompt_name} v{version}",
                )
                logger.debug(
                    f"✓ MLflow genai.register_prompt() 성공: {prompt_name}"
                )
            except Exception as e:
                logger.error(
                    f"❌ MLflow 프롬프트 등록 실패: {str(e)}. "
                    f"MLflow 버전 확인 필요 (3.12+ 권장)"
                )
                raise

            # 메타데이터와 함께 레지스트리 업데이트
            file_hash = self._compute_file_hash(prompt_name)
            self._mlflow_registry[prompt_name] = {
                "version": version,
                "file_hash": file_hash,
                "mlflow_uri": f"prompts:/{prompt_name}@{version}",
                "metadata": metadata,
                "registered_at": str(Path(self.prompts_dir / f"{prompt_name}.yaml").stat().st_mtime),
            }

            logger.info(
                f"✓ MLflow에 프롬프트 등록 완료: {prompt_name} (v{version})"
            )

            return f"prompts:/{prompt_name}@{version}"

        except FileNotFoundError as e:
            logger.error(f"❌ 프롬프트 파일을 찾을 수 없습니다: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"❌ MLflow 등록 실패 ({prompt_name}): {str(e)}")
            raise

    def load_prompt_from_mlflow(self, prompt_name: str, version: str = "latest") -> str:
        """
        MLflow 레지스트리에서 프롬프트 로드
        mlflow.start_run() 또는 @mlflow.trace 내에서 호출하면
        자동으로 Linked prompts에 추적됨

        공식 문서:
        https://mlflow.org/docs/latest/genai/prompt-registry/use-prompts-in-apps/

        Args:
            prompt_name: 프롬프트 이름 (예: "news_summarization")
            version: 프롬프트 버전
                    - "latest" (기본값): 최신 버전
                    - "1", "2", ... : 특정 버전 번호
                    - "production", "staging" 등: 별칭

        Returns:
            로드된 프롬프트 템플릿 문자열

        Example:
            ```python
            with mlflow.start_run():
                pm = PromptManager()
                # 이 호출이 자동으로 run에 링크됨 ✨
                prompt = pm.load_prompt_from_mlflow("news_summarization")

                # 프롬프트 포맷팅
                rendered = prompt.format(article="...")

                # LLM 호출 등...
            ```

        Note:
            MLflow 3.12+ 권장
        """
        try:
            # 공식 문서의 URI 형식: prompts:/<prompt_name>@<version>
            prompt_uri = f"prompts:/{prompt_name}@{version}"

            # mlflow.start_run() 또는 @mlflow.trace 내에서 호출 시
            # 자동으로 run/trace에 프롬프트가 링크됨
            loaded_prompt = mlflow.genai.load_prompt(name_or_uri=prompt_uri)

            logger.debug(f"✓ MLflow에서 프롬프트 로드: {prompt_uri}")

            return loaded_prompt

        except Exception as e:
            logger.warning(
                f"⚠️ MLflow에서 프롬프트 로드 실패: {str(e)}. "
                f"로컬 YAML에서 로드합니다."
            )
            # 폴백: 로컬 YAML에서 로드
            prompt_config = self.load_prompt(prompt_name)
            return prompt_config.get("template", "")

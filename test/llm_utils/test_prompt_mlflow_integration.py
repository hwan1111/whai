"""
MLflow 프롬프트 관리 통합 테스트

프롬프트 등록, 로드, 변경 감지, Linked prompts 추적 검증
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import mlflow
import pytest
import yaml

from src.llm_utils import PromptManager


@pytest.fixture
def temp_prompts_dir():
    """임시 프롬프트 디렉토리 생성"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_prompt(temp_prompts_dir):
    """샘플 프롬프트 YAML 파일 생성"""
    prompt_data = {
        "name": "test_prompt",
        "version": "1.0.0",
        "description": "Test prompt",
        "domain": "test",
        "use_case": "testing",
        "template": "This is a test prompt: {input}",
        "parameters": {
            "input": {
                "type": "string",
                "description": "Test input",
                "required": True,
            }
        },
        "model_config": {
            "temperature": 0.5,
            "max_tokens": 100,
        },
        "metadata": {
            "created_date": "2026-05-22",
            "author": "test",
        },
    }

    prompt_file = temp_prompts_dir / "test_prompt.yaml"
    with open(prompt_file, "w") as f:
        yaml.dump(prompt_data, f)

    return prompt_file, prompt_data


class TestPromptManagerMlflowIntegration:
    """MLflow 프롬프트 관리 통합 테스트"""

    def test_compute_file_hash(self, sample_prompt, temp_prompts_dir):
        """파일 해시 계산 테스트"""
        _, _ = sample_prompt
        pm = PromptManager(prompts_dir=temp_prompts_dir)

        # 파일 해시 계산
        hash1 = pm._compute_file_hash("test_prompt")
        assert len(hash1) == 16  # SHA-256의 처음 16자
        assert hash1.isalnum()

        # 동일 파일은 같은 해시 반환
        hash2 = pm._compute_file_hash("test_prompt")
        assert hash1 == hash2

        # 파일이 없으면 빈 문자열 반환
        hash_nonexistent = pm._compute_file_hash("nonexistent")
        assert hash_nonexistent == ""

    def test_should_update_in_mlflow_first_registration(
        self, sample_prompt, temp_prompts_dir
    ):
        """처음 등록 시 업데이트 필요 판단"""
        _, _ = sample_prompt
        pm = PromptManager(prompts_dir=temp_prompts_dir)

        # 등록되지 않은 프롬프트는 업데이트 필요
        assert pm._should_update_in_mlflow("test_prompt") is True

    def test_should_update_in_mlflow_after_registration(
        self, sample_prompt, temp_prompts_dir
    ):
        """등록 후 변경 없으면 업데이트 불필요"""
        _, _ = sample_prompt
        pm = PromptManager(prompts_dir=temp_prompts_dir)

        # 버전과 해시 저장
        file_hash = pm._compute_file_hash("test_prompt")
        pm._mlflow_registry["test_prompt"] = {
            "version": "1.0.0",
            "file_hash": file_hash,
        }

        # 변경이 없으므로 업데이트 불필요
        assert pm._should_update_in_mlflow("test_prompt") is False

    def test_should_update_on_version_change(self, sample_prompt, temp_prompts_dir):
        """버전 변경 시 업데이트 필요"""
        prompt_file, _ = sample_prompt
        pm = PromptManager(prompts_dir=temp_prompts_dir)

        # 이전 버전 저장
        file_hash = pm._compute_file_hash("test_prompt")
        pm._mlflow_registry["test_prompt"] = {
            "version": "0.9.0",  # 다른 버전
            "file_hash": file_hash,
        }

        # 버전이 다르므로 업데이트 필요
        assert pm._should_update_in_mlflow("test_prompt") is True

    def test_should_update_on_file_change(self, sample_prompt, temp_prompts_dir):
        """파일 변경 시 업데이트 필요"""
        prompt_file, _ = sample_prompt
        pm = PromptManager(prompts_dir=temp_prompts_dir)

        # 이전 해시 저장
        pm._mlflow_registry["test_prompt"] = {
            "version": "1.0.0",
            "file_hash": "different_hash_123",
        }

        # 파일이 변경되었으므로 업데이트 필요
        assert pm._should_update_in_mlflow("test_prompt") is True

    @patch("mlflow.genai.register_prompt")
    def test_register_prompt_to_mlflow(
        self, mock_register, sample_prompt, temp_prompts_dir
    ):
        """프롬프트를 MLflow에 등록"""
        _, prompt_data = sample_prompt
        pm = PromptManager(prompts_dir=temp_prompts_dir)

        # 프롬프트 등록
        uri = pm.register_prompt_to_mlflow("test_prompt")

        # MLflow에 등록되었는지 확인
        mock_register.assert_called_once()
        call_args = mock_register.call_args
        assert call_args.kwargs["name"] == "test_prompt"
        assert call_args.kwargs["version"] == "1.0.0"
        assert "Test input" in call_args.kwargs["prompt"]

        # 반환된 URI 확인
        assert "prompts:/test_prompt@" in uri

        # 레지스트리에 저장되었는지 확인
        assert "test_prompt" in pm._mlflow_registry
        assert pm._mlflow_registry["test_prompt"]["version"] == "1.0.0"

    @patch("mlflow.genai.register_prompt")
    def test_register_prompt_idempotent(
        self, mock_register, sample_prompt, temp_prompts_dir
    ):
        """같은 파일은 중복 등록하지 않음 (멱등성)"""
        _, _ = sample_prompt
        pm = PromptManager(prompts_dir=temp_prompts_dir)

        # 첫 번째 등록
        pm.register_prompt_to_mlflow("test_prompt")
        assert mock_register.call_count == 1

        # 두 번째 등록 (파일 변경 없음)
        pm.register_prompt_to_mlflow("test_prompt")
        # 두 번째는 호출되지 않음
        assert mock_register.call_count == 1

    @patch("mlflow.genai.load_prompt")
    def test_load_prompt_from_mlflow(self, mock_load, temp_prompts_dir, sample_prompt):
        """MLflow에서 프롬프트 로드"""
        _, prompt_data = sample_prompt
        pm = PromptManager(prompts_dir=temp_prompts_dir)

        # Mock 응답
        mock_load.return_value = prompt_data["template"]

        # 프롬프트 로드
        loaded_prompt = pm.load_prompt_from_mlflow("test_prompt")

        # MLflow에서 로드되었는지 확인
        mock_load.assert_called_once()
        call_args = mock_load.call_args[0]
        assert "prompts:/test_prompt@" in call_args[0]

        # 로드된 프롬프트 확인
        assert loaded_prompt == prompt_data["template"]

    @patch("mlflow.genai.load_prompt")
    def test_load_prompt_fallback_to_local(
        self, mock_load, temp_prompts_dir, sample_prompt
    ):
        """MLflow 로드 실패 시 로컬 YAML에서 로드"""
        _, prompt_data = sample_prompt
        pm = PromptManager(prompts_dir=temp_prompts_dir)

        # Mock 실패
        mock_load.side_effect = Exception("MLflow unavailable")

        # 프롬프트 로드 (폴백)
        loaded_prompt = pm.load_prompt_from_mlflow("test_prompt")

        # 로컬 YAML에서 로드됨
        assert loaded_prompt == prompt_data["template"]

    def test_list_prompts_integration(self, temp_prompts_dir):
        """여러 프롬프트 목록 확인"""
        # 여러 프롬프트 파일 생성
        for i in range(3):
            prompt_data = {
                "name": f"prompt_{i}",
                "version": "1.0.0",
                "template": f"Prompt {i}",
            }
            prompt_file = temp_prompts_dir / f"prompt_{i}.yaml"
            with open(prompt_file, "w") as f:
                yaml.dump(prompt_data, f)

        pm = PromptManager(prompts_dir=temp_prompts_dir)
        prompts = pm.list_prompts()

        assert len(prompts) == 3
        assert "prompt_0" in prompts
        assert "prompt_1" in prompts
        assert "prompt_2" in prompts


class TestPromptManagerWithMlflowTrace:
    """MLflow trace와의 통합 테스트"""

    @patch("mlflow.genai.load_prompt")
    @patch("mlflow.start_run")
    def test_prompt_tracked_in_run(
        self, mock_start_run, mock_load_prompt, temp_prompts_dir, sample_prompt
    ):
        """run 내에서 프롬프트 로드 시 자동 추적"""
        _, prompt_data = sample_prompt
        pm = PromptManager(prompts_dir=temp_prompts_dir)

        mock_load_prompt.return_value = prompt_data["template"]

        # run 내에서 프롬프트 로드
        with mlflow.start_run():
            loaded = pm.load_prompt_from_mlflow("test_prompt")

        # 프롬프트가 로드됨
        assert loaded == prompt_data["template"]
        mock_load_prompt.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

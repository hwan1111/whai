#!/usr/bin/env python3
"""
MLflow 프롬프트 관리 시스템 통합 테스트

프롬프트 등록, 로드, 변경 감지 기능 검증
"""

import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging
import tempfile
from unittest.mock import patch, MagicMock

import yaml

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def test_prompt_manager_initialization():
    """PromptManager 초기화 테스트"""
    logger.info("\n[Test 1] PromptManager 초기화")
    # GatewayClient 임포트 문제를 피하기 위해 직접 import
    from src.llm_utils.prompt_manager import PromptManager

    pm = PromptManager()
    assert pm.prompts_dir.exists(), "프롬프트 디렉토리가 없습니다"
    logger.info("✓ PromptManager 초기화 성공")

    return pm


def test_load_prompt(pm):
    """프롬프트 로드 테스트"""
    logger.info("\n[Test 2] 프롬프트 로드")

    try:
        prompt_config = pm.load_prompt("news_summarization")
        assert prompt_config.get("name") == "news_summarization", "프롬프트 이름 불일치"
        assert prompt_config.get("version") == "1.0.0", "프롬프트 버전 불일치"
        logger.info(f"✓ 프롬프트 로드 성공 (v{prompt_config.get('version')})")
        return prompt_config
    except FileNotFoundError as e:
        logger.error(f"❌ {str(e)}")
        return None


def test_compute_file_hash(pm):
    """파일 해시 계산 테스트"""
    logger.info("\n[Test 3] 파일 해시 계산")

    hash1 = pm._compute_file_hash("news_summarization")
    assert len(hash1) > 0, "해시 계산 실패"
    assert len(hash1) == 16, f"해시 길이 오류: {len(hash1)} (예상: 16)"

    hash2 = pm._compute_file_hash("news_summarization")
    assert hash1 == hash2, "같은 파일의 해시가 다릅니다"

    logger.info(f"✓ 파일 해시 계산 성공: {hash1}")


def test_should_update_detection(pm):
    """업데이트 필요 여부 판단 테스트"""
    logger.info("\n[Test 4] 업데이트 필요 여부 판단")

    # 처음에는 업데이트 필요
    should_update_first = pm._should_update_in_mlflow("news_summarization")
    assert should_update_first is True, "처음 등록은 업데이트가 필요합니다"
    logger.info("✓ 처음 등록 시 업데이트 필요 감지")

    # 레지스트리에 저장
    file_hash = pm._compute_file_hash("news_summarization")
    pm._mlflow_registry["news_summarization"] = {
        "version": "1.0.0",
        "file_hash": file_hash,
    }

    # 두 번째는 업데이트 불필요
    should_update_second = pm._should_update_in_mlflow("news_summarization")
    assert should_update_second is False, "변경이 없으면 업데이트가 필요 없습니다"
    logger.info("✓ 변경 없을 때 업데이트 불필요 감지")


def test_list_prompts(pm):
    """프롬프트 목록 조회 테스트"""
    logger.info("\n[Test 5] 프롬프트 목록 조회")

    prompts = pm.list_prompts()
    assert len(prompts) > 0, "프롬프트 목록이 비어있습니다"
    assert "news_summarization" in prompts, "news_summarization 프롬프트가 없습니다"

    logger.info(f"✓ 사용 가능한 프롬프트: {', '.join(prompts)}")


def test_render_prompt(pm):
    """프롬프트 렌더링 테스트"""
    logger.info("\n[Test 6] 프롬프트 렌더링")

    test_article = "Apple reported record earnings of $100B"
    rendered = pm.render_prompt("news_summarization", article=test_article)

    assert test_article in rendered, "렌더링된 프롬프트에 입력이 포함되지 않았습니다"
    assert "3줄 요약" in rendered or "3" in rendered, "렌더링 실패"

    logger.info(f"✓ 프롬프트 렌더링 성공 ({len(rendered)}자)")


def test_get_model_config(pm):
    """모델 설정 조회 테스트"""
    logger.info("\n[Test 7] 모델 설정 조회")

    config = pm.get_model_config("news_summarization")
    assert "temperature" in config, "temperature 설정이 없습니다"
    assert "max_tokens" in config, "max_tokens 설정이 없습니다"

    logger.info(
        f"✓ 모델 설정 조회 성공: "
        f"temperature={config['temperature']}, max_tokens={config['max_tokens']}"
    )


def test_get_prompt_info(pm):
    """프롬프트 정보 조회 테스트"""
    logger.info("\n[Test 8] 프롬프트 정보 조회")

    info = pm.get_prompt_info("news_summarization")
    assert info["name"] == "news_summarization", "프롬프트 이름 불일치"
    assert info["version"] == "1.0.0", "프롬프트 버전 불일치"
    assert "description" in info, "설명이 없습니다"

    logger.info(f"✓ 프롬프트 정보 조회 성공: {info['name']} v{info['version']}")


@patch("mlflow.genai.register_prompt")
def test_register_prompt_to_mlflow(mock_register, pm):
    """MLflow 프롬프트 등록 테스트"""
    logger.info("\n[Test 9] MLflow 프롬프트 등록")

    uri = pm.register_prompt_to_mlflow("news_summarization")

    # MLflow에 등록되었는지 확인
    assert mock_register.called, "mlflow.genai.register_prompt가 호출되지 않았습니다"
    logger.info("✓ MLflow genai.register_prompt 호출 확인")

    # 반환된 URI 확인
    assert "prompts:" in uri, f"프롬프트 URI 형식 오류: {uri}"
    assert "news_summarization" in uri, "프롬프트 이름이 URI에 없습니다"
    logger.info(f"✓ 프롬프트 URI 생성 성공: {uri}")

    # 레지스트리에 저장되었는지 확인
    assert "news_summarization" in pm._mlflow_registry, "레지스트리에 저장되지 않았습니다"
    logger.info("✓ 프롬프트 메타데이터 레지스트리 저장 확인")


@patch("mlflow.genai.load_prompt")
def test_load_prompt_from_mlflow(mock_load, pm):
    """MLflow에서 프롬프트 로드 테스트"""
    logger.info("\n[Test 10] MLflow에서 프롬프트 로드")

    # Mock 응답
    prompt_template = "다음 기사를 요약하세요: {article}"
    mock_load.return_value = prompt_template

    loaded = pm.load_prompt_from_mlflow("news_summarization")

    # MLflow에서 로드되었는지 확인
    assert mock_load.called, "mlflow.genai.load_prompt가 호출되지 않았습니다"
    logger.info("✓ MLflow genai.load_prompt 호출 확인")

    # 로드된 프롬프트 확인
    assert loaded == prompt_template, "로드된 프롬프트가 일치하지 않습니다"
    logger.info(f"✓ 프롬프트 로드 성공 ({len(loaded)}자)")


@patch("mlflow.genai.load_prompt")
def test_load_prompt_fallback(mock_load, pm):
    """MLflow 로드 실패 시 폴백 테스트"""
    logger.info("\n[Test 11] MLflow 로드 실패 시 폴백")

    # Mock 실패
    mock_load.side_effect = Exception("MLflow unavailable")

    loaded = pm.load_prompt_from_mlflow("news_summarization")

    # 로컬 YAML에서 로드됨
    prompt_config = pm.load_prompt("news_summarization")
    assert loaded == prompt_config.get("template"), "폴백이 제대로 작동하지 않았습니다"
    logger.info("✓ MLflow 실패 시 로컬 YAML으로 폴백 성공")


def test_temp_prompt_dir():
    """임시 프롬프트 디렉토리 테스트"""
    logger.info("\n[Test 12] 임시 프롬프트 디렉토리 처리")
    from src.llm_utils.prompt_manager import PromptManager

    with tempfile.TemporaryDirectory() as tmpdir:
        temp_dir = Path(tmpdir)

        # YAML 파일 생성
        prompt_data = {
            "name": "temp_prompt",
            "version": "1.0.0",
            "template": "Test: {input}",
            "parameters": {"input": {"required": True}},
            "model_config": {"temperature": 0.5},
        }
        prompt_file = temp_dir / "temp_prompt.yaml"
        with open(prompt_file, "w") as f:
            yaml.dump(prompt_data, f)

        # PromptManager로 로드
        pm = PromptManager(prompts_dir=temp_dir)
        loaded = pm.load_prompt("temp_prompt")

        assert loaded["name"] == "temp_prompt", "임시 디렉토리에서 로드 실패"
        logger.info("✓ 임시 프롬프트 디렉토리 처리 성공")


def main():
    """모든 테스트 실행"""
    logger.info("=" * 60)
    logger.info("MLflow 프롬프트 관리 시스템 통합 테스트")
    logger.info("=" * 60)

    try:
        # PromptManager 초기화
        pm = test_prompt_manager_initialization()

        # 프롬프트 로드
        prompt_config = test_load_prompt(pm)
        if not prompt_config:
            logger.error("❌ 프롬프트 로드 실패로 테스트 중단")
            return False

        # 각 테스트 실행
        test_compute_file_hash(pm)
        test_should_update_detection(pm)
        test_list_prompts(pm)
        test_render_prompt(pm)
        test_get_model_config(pm)
        test_get_prompt_info(pm)
        test_register_prompt_to_mlflow(pm)
        test_load_prompt_from_mlflow(pm)
        test_load_prompt_fallback(pm)
        test_temp_prompt_dir()

        # 성공 로깅
        logger.info("\n" + "=" * 60)
        logger.info("✅ 모든 테스트 성공!")
        logger.info("=" * 60)

        return True

    except Exception as e:
        logger.error(f"❌ 테스트 실패: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

"""
국면 분석 프롬프트 로더

MLflow 우선 로드 → 실패 시 로컬 YAML fallback.
시스템 프롬프트는 항상 로컬 YAML에서 로드한다
(MLflow는 유저 템플릿만 관리).
"""

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_DEFAULT_YAML = _PROMPTS_DIR / "regime_analysis.yaml"

# MLflow prompt URI — UI에서 등록 후 버전 지정
MLFLOW_PROMPT_URI = "prompts:/regime_analysis/latest"


def load_prompt(
    mlflow_uri: str = MLFLOW_PROMPT_URI,
    yaml_path: Path = _DEFAULT_YAML,
) -> tuple[str, str]:
    """
    국면 분석 프롬프트 로드

    MLflow 연결 가능하면 유저 템플릿을 MLflow에서 가져오고,
    실패하면 로컬 YAML을 사용한다.
    시스템 프롬프트는 항상 로컬 YAML 기준.

    Returns:
        (system_prompt, user_template)
    """
    local = _load_yaml(yaml_path)
    system = local["system"].strip()

    # MLflow 시도
    try:
        import mlflow
        prompt_version = mlflow.genai.load_prompt(mlflow_uri)
        template = getattr(prompt_version, "template", str(prompt_version)).strip()
        logger.info(f"프롬프트 로드: MLflow ({mlflow_uri})")
        return system, template
    except Exception as e:
        logger.debug(f"MLflow 프롬프트 로드 실패 → 로컬 YAML 사용 ({e})")

    # 로컬 YAML fallback
    template = local["template"].strip()
    logger.info(f"프롬프트 로드: 로컬 YAML ({yaml_path.name})")
    return system, template


def render(template: str, **kwargs: str) -> str:
    """
    템플릿 변수 치환

    str.replace 방식 사용 — .format() 금지.
    (JSON 스키마 예시의 { } 와 충돌 방지)

    Args:
        template: 유저 프롬프트 템플릿
        **kwargs: 변수명=값 (값은 모두 문자열로 변환됨)

    Returns:
        렌더링된 프롬프트 문자열
    """
    result = template
    for key, value in kwargs.items():
        result = result.replace(f"{{{key}}}", str(value))
    return result


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"프롬프트 YAML 없음: {path}")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)

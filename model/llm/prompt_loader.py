"""
국면 분석 프롬프트 로더

MLflow 우선 로드 → 실패 시 로컬 YAML fallback.
시스템 프롬프트는 항상 로컬 YAML에서 로드한다
(MLflow는 유저 템플릿만 관리).
"""

import logging
import os
import re
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# .env 파일 자동 로드
def _load_env():
    """프로젝트 루트의 .env 또는 .env.local 파일을 로드"""
    try:
        from dotenv import load_dotenv
        env_dir = Path(__file__).parent.parent.parent  # model/ → project root
        env_local = env_dir / ".env.local"
        env_file = env_dir / ".env"

        if env_local.exists():
            load_dotenv(env_local)
        elif env_file.exists():
            load_dotenv(env_file)
    except ImportError:
        pass  # python-dotenv 미설치 시 스킵

_load_env()

# MLflow 서버 설정 (환경 변수 또는 기본값)
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_DEFAULT_YAML = _PROMPTS_DIR / "regime_analysis.yaml"

# MLflow prompt URI — UI에서 등록 후 버전 지정
MLFLOW_PROMPT_URI = "prompts:/regime_news_summarys/3"


def load_prompt(
    mlflow_uri: str = MLFLOW_PROMPT_URI,
    yaml_path: Path = _DEFAULT_YAML,
    tracking_uri: str | None = None,
) -> tuple[str, str]:
    """
    국면 분석 프롬프트 로드

    MLflow 연결 가능하면 유저 템플릿을 MLflow에서 가져오고,
    실패하면 로컬 YAML을 사용한다.
    시스템 프롬프트는 항상 로컬 YAML 기준.

    Args:
        mlflow_uri: MLflow 프롬프트 URI (기본: regime_news_summarys/3)
        yaml_path: 로컬 YAML 경로
        tracking_uri: MLflow 트래킹 서버 URI (생략 시 MLFLOW_TRACKING_URI 환경변수 사용)

    Returns:
        (system_prompt, user_template)
    """
    local = _load_yaml(yaml_path)
    system = local["system"].strip()

    # MLflow 시도
    try:
        import mlflow

        # MLflow 서버 설정
        uri = tracking_uri or MLFLOW_TRACKING_URI
        mlflow.set_tracking_uri(uri)

        # 인증 정보 설정 (환경변수 확인 후 설정)
        username = os.getenv("MLFLOW_TRACKING_USERNAME")
        password = os.getenv("MLFLOW_TRACKING_PASSWORD")
        if username and password:
            # MLflow client가 올바르게 인증하도록 설정
            os.environ["MLFLOW_TRACKING_USERNAME"] = username
            os.environ["MLFLOW_TRACKING_PASSWORD"] = password

        prompt_version = mlflow.genai.load_prompt(mlflow_uri)
        template_raw = getattr(prompt_version, "template", str(prompt_version))

        # 템플릿이 list면 (ChatML 형식) JSON 변환, 문자열이면 그대로 사용
        if isinstance(template_raw, list):
            import json
            template = json.dumps(template_raw, ensure_ascii=False, indent=2)
        else:
            template = str(template_raw).strip()

        logger.info(f"✓ 프롬프트 로드: MLflow ({mlflow_uri})")
        return system, template
    except Exception as e:
        logger.warning(f"✗ MLflow 프롬프트 로드 실패: {type(e).__name__}: {e}")

    # 로컬 YAML fallback
    template = local["template"].strip()
    logger.info(f"→ 로컬 YAML 사용 ({yaml_path.name})")
    return system, template


def render(template: str, **kwargs: str) -> str:
    """
    템플릿 변수 치환

    정규식 기반 치환 — .format() 금지.
    (JSON 스키마 예시의 중괄호와 충돌 방지)

    `{key}`, `{{key}}`, `{{ key }}` 등 중괄호 1~2개 + 선택적 공백을
    모두 동일한 변수 placeholder로 인식하여 치환한다.
    MLflow Prompt Registry의 `{{ var }}` (Jinja 스타일) 템플릿과
    로컬 YAML의 `{{var}}` 템플릿을 모두 지원한다.

    Args:
        template: 유저 프롬프트 템플릿
        **kwargs: 변수명=값 (값은 모두 문자열로 변환됨)

    Returns:
        렌더링된 프롬프트 문자열
    """
    result = template
    for key, value in kwargs.items():
        pattern = r"\{{1,2}\s*" + re.escape(key) + r"\s*\}{1,2}"
        # 치환 문자열에 re.sub의 백슬래시 escape 규칙(\1, \g<name> 등)이
        # 적용되지 않도록 콜러블 형태로 전달한다 (news_context 등 자유 텍스트 안전).
        result = re.sub(pattern, lambda _m, v=str(value): v, result)
    return result


def list_mlflow_prompts(tracking_uri: str | None = None) -> dict | None:
    """
    MLflow Prompt Registry의 등록된 프롬프트 목록 조회

    Args:
        tracking_uri: MLflow 트래킹 서버 URI (생략 시 MLFLOW_TRACKING_URI 환경변수 사용)

    Returns:
        {"name": description} 딕셔너리 또는 None (MLflow 연결 실패)
    """
    try:
        import mlflow

        # MLflow 서버 설정
        uri = tracking_uri or MLFLOW_TRACKING_URI
        mlflow.set_tracking_uri(uri)

        client = mlflow.MlflowClient(tracking_uri=uri)
        prompts = client.search_prompts()

        result = {p.name: p.description for p in prompts}
        logger.info(f"✓ MLflow 프롬프트 목록 조회 완료 ({uri}): {list(result.keys())}")
        return result if result else None
    except Exception as e:
        logger.warning(f"✗ MLflow 프롬프트 조회 실패: {type(e).__name__}: {e}")
        return None


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"프롬프트 YAML 없음: {path}")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)

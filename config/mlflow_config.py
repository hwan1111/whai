"""
MLflow 원격 서버 연결 설정

원격 MLflow 서버에 접속하기 위한 설정을 관리합니다.
- 추적 서버(Tracking Server) URI
- 기본 인증(Basic Auth) 정보
- 로깅 레벨
"""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# .env.local 파일 로드 (프로젝트 루트 기준)
# override=True로 설정하여 기존 환경변수를 덮어씀
_project_root = Path(__file__).parent.parent
_env_file = _project_root / ".env.local"
if _env_file.exists():
    load_dotenv(_env_file, override=True)
else:
    # .env.local이 없으면 .env 시도
    _env_file_fallback = _project_root / ".env"
    if _env_file_fallback.exists():
        load_dotenv(_env_file_fallback, override=True)

# 프록시 설정 처리 (원격 MLflow 서버 접근을 위해 프록시 우회 필요할 수 있음)
# NO_PROXY 환경변수가 설정되면 우선적용, 아니면 기본값
if "NO_PROXY" not in os.environ and "no_proxy" not in os.environ:
    os.environ["NO_PROXY"] = "localhost,127.0.0.1,team4.ap.loclx.io,.local"


class MLflowConfig:
    """MLflow 원격 서버 설정"""

    # 원격 MLflow 서버 정보
    MLFLOW_TRACKING_URI: str = os.getenv(
        "MLFLOW_TRACKING_URI",
        "http://localhost:5001"  # 기본값: 로컬호스트
    )

    # 원격 서버 인증 정보
    MLFLOW_TRACKING_USERNAME: Optional[str] = os.getenv("MLFLOW_TRACKING_USERNAME")
    MLFLOW_TRACKING_PASSWORD: Optional[str] = os.getenv("MLFLOW_TRACKING_PASSWORD")

    # 실험 및 운영 설정
    MLFLOW_EXPERIMENT_PREFIX: str = "llm"  # 실험명 프리픽스
    MLFLOW_LOG_LEVEL: str = os.getenv("MLFLOW_LOG_LEVEL", "info")

    @classmethod
    def get_tracking_uri(cls) -> str:
        """MLflow 추적 서버 URI 반환"""
        return cls.MLFLOW_TRACKING_URI

    @classmethod
    def get_auth_headers(cls) -> dict[str, str]:
        """
        MLflow 기본 인증 헤더 생성

        Returns:
            Authorization 헤더 딕셔너리 (인증 정보가 없으면 빈 딕셔너리)
        """
        if cls.MLFLOW_TRACKING_USERNAME and cls.MLFLOW_TRACKING_PASSWORD:
            import base64

            credentials = f"{cls.MLFLOW_TRACKING_USERNAME}:{cls.MLFLOW_TRACKING_PASSWORD}"
            encoded = base64.b64encode(credentials.encode()).decode()
            return {"Authorization": f"Basic {encoded}"}
        return {}

    @classmethod
    def validate(cls) -> bool:
        """
        설정 유효성 검증

        Returns:
            설정이 유효하면 True, 인증 정보가 없으면 False
        """
        # 인증 정보 검증 (Basic Auth 사용 시)
        if not (cls.MLFLOW_TRACKING_USERNAME and cls.MLFLOW_TRACKING_PASSWORD):
            print(
                "⚠️ Warning: MLflow 인증 정보가 설정되지 않았습니다."
                "\n   .env.local에 다음을 추가하세요:"
                "\n   - MLFLOW_TRACKING_USERNAME"
                "\n   - MLFLOW_TRACKING_PASSWORD"
            )
            return False
        return True

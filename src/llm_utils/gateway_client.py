"""
MLflow Gateway 클라이언트

MLflow Gateway REST API를 사용하여 OpenRouter의 LLM 모델에 접근합니다.

아키텍처:
  로컬 → MLflow Gateway REST API → OpenRouter (summarize-llm API 키)

엔드포인트:
  - mid_performance_llm (레퍼런스 생성용)
  - low_performance_llm (프로덕션 요약용)
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# .env 파일 로드 (프로젝트 루트 기준)
_project_root = Path(__file__).parent.parent.parent
_env_file = _project_root / ".env"
if _env_file.exists():
    load_dotenv(_env_file, override=True)

# 프록시 무시 (환경변수 제거)
os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)
os.environ.pop("http_proxy", None)
os.environ.pop("https_proxy", None)
os.environ.pop("ALL_PROXY", None)
os.environ.pop("all_proxy", None)


class GatewayClient:
    """MLflow Gateway REST API 클라이언트"""

    # LLM 파라미터 기본값
    DEFAULT_TEMPERATURE = 0.7
    DEFAULT_MAX_TOKENS = 512

    def __init__(self, endpoint: str = "mid_performance_llm", validate_connection: bool = True):
        """
        MLflow Gateway 클라이언트 초기화

        Args:
            endpoint: Gateway route 이름 (mid_performance_llm, low_performance_llm)
            validate_connection: 초기화 시 연결 검증 여부

        Raises:
            RuntimeError: Gateway에 연결할 수 없을 때
        """
        # MLflow Gateway 설정
        self.gateway_uri = os.getenv(
            "MLFLOW_GATEWAY_URL",
            "http://52.78.237.104:5001/gateway/mlflow/v1"
        )
        self.username = os.getenv("MLFLOW_TRACKING_USERNAME", "")
        self.password = os.getenv("MLFLOW_TRACKING_PASSWORD", "")
        self.endpoint = endpoint

        # Gateway 요청 URL
        self.request_url = f"{self.gateway_uri}/chat/completions"

        logger.debug(
            f"환경 변수 로드 확인:\n"
            f"  MLFLOW_GATEWAY_URL: {self.gateway_uri}\n"
            f"  Request URL: {self.request_url}\n"
            f"  Username: {self.username}\n"
            f"  Endpoint: {self.endpoint}"
        )

        if validate_connection:
            self._validate_connection()

        logger.info(
            f"✓ MLflow Gateway 클라이언트 초기화 완료\n"
            f"   Gateway URI: {self.gateway_uri}\n"
            f"   Endpoint: {self.endpoint}"
        )

    def _validate_connection(self) -> bool:
        """
        MLflow Gateway 연결 확인

        Returns:
            연결 성공 시 True

        Raises:
            RuntimeError: 연결 실패 시
        """
        try:
            # 간단한 테스트 요청
            test_message = "Say 'Connection successful' in one sentence."

            with httpx.Client(timeout=10.0, auth=(self.username, self.password)) as client:
                response = client.post(
                    self.request_url,
                    json={
                        "model": self.endpoint,
                        "messages": [{"role": "user", "content": test_message}],
                        "temperature": 0.3,
                        "max_tokens": 50,
                    }
                )

                if response.status_code == 200:
                    logger.info("✓ MLflow Gateway 연결 검증 완료")
                    return True
                else:
                    error_msg = (
                        f"❌ MLflow Gateway 연결 실패\n"
                        f"   Gateway URI: {self.gateway_uri}\n"
                        f"   Endpoint: {self.endpoint}\n"
                        f"   Status Code: {response.status_code}\n"
                        f"   Response: {response.text}"
                    )
                    logger.error(error_msg)
                    raise RuntimeError(error_msg)

        except Exception as e:
            error_msg = (
                f"❌ MLflow Gateway 요청 실패\n"
                f"   Gateway URI: {self.gateway_uri}\n"
                f"   Endpoint: {self.endpoint}\n"
                f"   오류: {str(e)}\n\n"
                f"   다음을 확인하세요:\n"
                f"   1. MLFLOW_GATEWAY_URL 설정 확인 (.env)\n"
                f"   2. MLflow 서버 실행 상태 확인\n"
                f"   3. Gateway endpoint 이름 확인\n"
                f"   4. 네트워크 연결 확인"
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def call(
        self,
        text: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        endpoint: Optional[str] = None,
    ) -> str:
        """
        MLflow Gateway를 통해 LLM 호출

        Args:
            text: 입력 텍스트 (렌더링된 프롬프트 등)
            temperature: 샘플링 온도 (0~1, 기본값: 0.7)
            max_tokens: 최대 토큰 수 (기본값: 512)
            endpoint: 사용할 route 이름 (기본값: 클래스 설정값)

        Returns:
            LLM 응답 텍스트

        Raises:
            RuntimeError: 호출 실패 시
        """
        temperature = temperature or self.DEFAULT_TEMPERATURE
        max_tokens = max_tokens or self.DEFAULT_MAX_TOKENS
        endpoint = endpoint or self.endpoint

        try:
            logger.debug(f"MLflow Gateway 호출: {len(text)}자 텍스트 전송 (Route: {endpoint})")

            with httpx.Client(timeout=60.0, auth=(self.username, self.password)) as client:
                response = client.post(
                    self.request_url,
                    json={
                        "model": endpoint,
                        "messages": [{"role": "user", "content": text}],
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    }
                )

                if response.status_code == 200:
                    result = response.json()

                    # 응답 형식 파싱
                    if isinstance(result, dict):
                        # OpenAI 형식 응답
                        if "choices" in result and len(result["choices"]) > 0:
                            message = result["choices"][0].get("message", {})
                            content = message.get("content", "")
                        # 직접 응답
                        elif "content" in result:
                            content = result["content"]
                        # 기타 형식
                        else:
                            content = str(result)
                    else:
                        content = str(result)

                    logger.debug(f"✓ MLflow Gateway 응답 수신 (크기: {len(content)}자)")
                    return content
                else:
                    error_msg = (
                        f"❌ MLflow Gateway 응답 오류\n"
                        f"   Status Code: {response.status_code}\n"
                        f"   Response: {response.text}"
                    )
                    logger.error(error_msg)
                    raise RuntimeError(error_msg)

        except Exception as e:
            error_msg = f"❌ MLflow Gateway 호출 실패: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def summarize(
        self,
        text: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        endpoint: Optional[str] = None,
    ) -> str:
        """
        텍스트 요약 (편의 메서드)

        Args:
            text: 요약할 텍스트
            temperature: 샘플링 온도
            max_tokens: 최대 토큰 수
            endpoint: 사용할 route 이름

        Returns:
            요약 텍스트
        """
        summary_prompt = (
            f"다음 텍스트를 3줄로 요약해주세요:\n\n{text}"
        )
        return self.call(
            text=summary_prompt,
            temperature=temperature or 0.5,
            max_tokens=max_tokens or 200,
            endpoint=endpoint,
        )

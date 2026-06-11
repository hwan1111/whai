"""
MLflow AI Gateway 클라이언트

원격 MLflow 서버의 AI Gateway를 통해 LLM 모델에 접근합니다.
Gateway는 OpenRouter 또는 다른 LLM 제공자를 백엔드로 사용합니다.

아키텍처:
  로컬 → MLflow AI Gateway → LLM (OpenRouter, etc.)

인증:
  MLflow Basic Auth (username/password)
  Gateway 라우트를 통한 모델 접근
"""

import logging
import os
from pathlib import Path
from typing import Any, Optional

import httpx
import mlflow
from dotenv import load_dotenv
from openai import OpenAI

logger = logging.getLogger(__name__)

# MLflow OpenAI SDK 자동 추적 활성화
try:
    mlflow.openai.autolog()
except Exception as e:
    logger.debug(f"MLflow OpenAI autolog 활성화 실패: {str(e)}")

_project_root = Path(__file__).parent.parent.parent
load_dotenv(_project_root / ".env", override=True)

# 프록시 무시 (환경변수 제거)
os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)
os.environ.pop("http_proxy", None)
os.environ.pop("https_proxy", None)
os.environ.pop("ALL_PROXY", None)
os.environ.pop("all_proxy", None)


class GatewayClient:
    """MLflow AI Gateway 클라이언트 (OpenAI 호환)"""

    # LLM 파라미터 기본값
    DEFAULT_TEMPERATURE = 0.7
    DEFAULT_MAX_TOKENS = 512

    def __init__(self, validate_connection: bool = True):
        """
        MLflow AI Gateway 클라이언트 초기화

        Args:
            validate_connection: 초기화 시 연결 검증 여부

        Raises:
            RuntimeError: MLflow Gateway에 연결할 수 없을 때
        """
        # 환경 변수 로드 (인스턴스 생성 시점에 로드)
        self.GATEWAY_BASE_URL = os.getenv(
            "MLFLOW_GATEWAY_URL",
            "http://52.78.237.104:5001/gateway/mlflow/v1",
        )
        self.MLFLOW_TRACKING_USERNAME = os.getenv("MLFLOW_TRACKING_USERNAME", "")
        self.MLFLOW_TRACKING_PASSWORD = os.getenv("MLFLOW_TRACKING_PASSWORD", "")
        self.ROUTE_NAME = os.getenv("MLFLOW_SUMMARIZE_URI", "mid_performance_llm")

        logger.debug(
            f"환경 변수 로드 확인:\n"
            f"  MLFLOW_TRACKING_USERNAME: {self.MLFLOW_TRACKING_USERNAME}\n"
            f"  MLFLOW_TRACKING_PASSWORD: {'*' * len(self.MLFLOW_TRACKING_PASSWORD) if self.MLFLOW_TRACKING_PASSWORD else '(empty)'}\n"
            f"  GATEWAY_BASE_URL: {self.GATEWAY_BASE_URL}\n"
            f"  ROUTE_NAME: {self.ROUTE_NAME}"
        )

        # OpenAI SDK를 사용하여 MLflow AI Gateway 호출
        # MLflow Gateway는 API key 불필요 (server-side 설정)
        self.client = OpenAI(
            base_url=self.GATEWAY_BASE_URL,
            api_key="",  # API key 불필요
        )

        if validate_connection:
            self._validate_connection()

        logger.info(
            f"✓ MLflow AI Gateway 클라이언트 초기화 완료\n"
            f"   Gateway URL: {self.GATEWAY_BASE_URL}\n"
            f"   Route: {self.ROUTE_NAME}"
        )

    def _validate_connection(self) -> bool:
        """
        MLflow AI Gateway 연결 확인

        Returns:
            연결 성공 시 True

        Raises:
            RuntimeError: 연결 실패 시
        """
        try:
            # 간단한 테스트 요청
            test_message = "Say 'Connection successful' in one sentence."

            response = self.client.chat.completions.create(
                model=self.ROUTE_NAME,
                messages=[{"role": "user", "content": test_message}],
                temperature=0.3,
                max_tokens=50,
            )

            if response.choices and len(response.choices) > 0:
                logger.info("✓ MLflow AI Gateway 연결 검증 완료")
                return True
            else:
                error_msg = (
                    f"❌ MLflow AI Gateway 연결 실패\n"
                    f"   Gateway URL: {self.GATEWAY_BASE_URL}\n"
                    f"   Route: {self.ROUTE_NAME}\n"
                    f"   응답이 비어있음"
                )
                logger.error(error_msg)
                raise RuntimeError(error_msg)

        except Exception as e:
            error_msg = (
                f"❌ MLflow AI Gateway 요청 실패\n"
                f"   Gateway URL: {self.GATEWAY_BASE_URL}\n"
                f"   Route: {self.ROUTE_NAME}\n"
                f"   오류: {str(e)}\n\n"
                f"   다음을 확인하세요:\n"
                f"   1. MLFLOW_TRACKING_URI 설정 확인\n"
                f"   2. MLFLOW_TRACKING_USERNAME/PASSWORD 설정 확인\n"
                f"   3. MLflow 서버 실행 상태\n"
                f"   4. Gateway Route 존재 여부"
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def call(
        self,
        text: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
    ) -> str:
        """
        MLflow AI Gateway를 통해 LLM 호출

        mlflow.start_run() 내에서 호출하면 MLflow가 자동으로
        OpenAI 호출을 traced합니다.

        참고:
          - mlflow.genai.load_prompt()를 mlflow.start_run() 내에서
            호출하면 자동으로 Linked prompts에 기록됨
          - 이 메서드는 순수 LLM 호출만 담당

        Args:
            text: 입력 텍스트 (렌더링된 프롬프트 등)
            temperature: 샘플링 온도 (0~1, 기본값: 0.7)
            max_tokens: 최대 토큰 수 (기본값: 512)
            model: 사용할 Gateway Route (기본값: 클래스 설정값)

        Returns:
            LLM 응답 텍스트

        Raises:
            RuntimeError: 호출 실패 시
        """
        temperature = temperature or self.DEFAULT_TEMPERATURE
        max_tokens = max_tokens or self.DEFAULT_MAX_TOKENS
        model = model or self.ROUTE_NAME

        try:
            logger.debug(f"MLflow Gateway 호출: {len(text)}자 텍스트 전송 (Route: {model})")

            response = self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": text}],
                temperature=temperature,
                max_tokens=max_tokens,
            )

            if response.choices and len(response.choices) > 0:
                result = response.choices[0].message.content
                logger.debug(f"✓ MLflow Gateway 응답 수신 (크기: {len(result)}자)")
                return result
            else:
                error_msg = "❌ MLflow Gateway 응답이 비어있음"
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
    ) -> str:
        """
        텍스트 요약 (편의 메서드)

        Args:
            text: 요약할 텍스트
            temperature: 샘플링 온도
            max_tokens: 최대 토큰 수

        Returns:
            요약 텍스트
        """
        # 요약용 시스템 프롬프트 추가
        summary_prompt = (
            f"다음 텍스트를 3줄로 요약해주세요:\n\n{text}"
        )
        return self.call(
            text=summary_prompt,
            temperature=temperature or 0.5,
            max_tokens=max_tokens or 200,
        )

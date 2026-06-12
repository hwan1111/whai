"""
MLflow GenAI Token Usage & Cost Tracking

토큰 사용량 추적 및 비용 계산 모듈
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import mlflow

logger = logging.getLogger(__name__)


@dataclass
class TokenUsage:
    """토큰 사용량 정보"""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = field(init=False)

    def __post_init__(self):
        self.total_tokens = self.input_tokens + self.output_tokens

    def to_dict(self) -> dict:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass
class CostInfo:
    """비용 정보"""
    input_cost: float = 0.0
    output_cost: float = 0.0
    total_cost: float = field(init=False)

    def __post_init__(self):
        self.total_cost = self.input_cost + self.output_cost

    def to_dict(self) -> dict:
        return {
            "input_cost_usd": self.input_cost,
            "output_cost_usd": self.output_cost,
            "total_cost_usd": self.total_cost,
        }


class TokenTracker:
    """토큰 사용량 및 비용 추적"""

    # OpenRouter 모델별 비용 (M tokens 기준)
    # https://openrouter.ai/docs#models
    MODEL_COSTS = {
        "mid_performance_llm": {
            "input_cost_per_mtok": 0.003,  # $/M tokens
            "output_cost_per_mtok": 0.009,  # $/M tokens
        },
        "low_performance_llm": {
            "input_cost_per_mtok": 0.0005,  # $/M tokens
            "output_cost_per_mtok": 0.0015,  # $/M tokens
        },
        "default": {  # 기본값 (미지정 모델)
            "input_cost_per_mtok": 0.005,
            "output_cost_per_mtok": 0.015,
        }
    }

    def __init__(self):
        self.total_usage = TokenUsage()
        self.total_cost = CostInfo()
        self.session_logs = []

    def track_usage(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        endpoint: Optional[str] = None,
    ) -> CostInfo:
        """
        토큰 사용량 추적 및 비용 계산

        Args:
            model: 모델 이름
            input_tokens: 입력 토큰 수
            output_tokens: 출력 토큰 수
            endpoint: 엔드포인트 이름 (선택사항)

        Returns:
            비용 정보
        """
        usage = TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens)
        cost = self._calculate_cost(model, usage, endpoint)

        # 누적
        self.total_usage.input_tokens += input_tokens
        self.total_usage.output_tokens += output_tokens
        self.total_usage.total_tokens = (
            self.total_usage.input_tokens + self.total_usage.output_tokens
        )
        self.total_cost.input_cost += cost.input_cost
        self.total_cost.output_cost += cost.output_cost
        self.total_cost.total_cost = (
            self.total_cost.input_cost + self.total_cost.output_cost
        )

        # 로그에 기록
        self.session_logs.append({
            "model": model,
            "endpoint": endpoint,
            "usage": usage.to_dict(),
            "cost": cost.to_dict(),
        })

        logger.debug(
            f"Token tracked: {model} | "
            f"Input: {input_tokens}, Output: {output_tokens} | "
            f"Cost: ${cost.total_cost:.6f}"
        )

        return cost

    def log_to_mlflow(self, run_id: Optional[str] = None) -> None:
        """
        누적된 토큰 정보를 MLflow에 로깅

        Args:
            run_id: MLflow Run ID (선택사항)
        """
        try:
            with mlflow.start_span(name="token_usage_summary"):
                # 토큰 사용량 로깅
                mlflow.log_token_usage(
                    model="aggregated",
                    input_tokens=self.total_usage.input_tokens,
                    output_tokens=self.total_usage.output_tokens,
                )

                # 메트릭 로깅
                mlflow.log_metrics({
                    "total_input_tokens": self.total_usage.input_tokens,
                    "total_output_tokens": self.total_usage.output_tokens,
                    "total_tokens": self.total_usage.total_tokens,
                    "total_cost_usd": self.total_cost.total_cost,
                    "input_cost_usd": self.total_cost.input_cost,
                    "output_cost_usd": self.total_cost.output_cost,
                })

                logger.info(
                    f"✓ Token usage logged to MLflow:\n"
                    f"   Tokens: {self.total_usage.total_tokens} "
                    f"(input: {self.total_usage.input_tokens}, "
                    f"output: {self.total_usage.output_tokens})\n"
                    f"   Cost: ${self.total_cost.total_cost:.6f} USD"
                )
        except Exception as e:
            logger.warning(f"⚠️ Failed to log token usage to MLflow: {str(e)}")

    def log_span_usage(self, span_name: str, usage: TokenUsage, cost: CostInfo) -> None:
        """
        개별 span에 토큰 정보 로깅

        Args:
            span_name: Span 이름
            usage: 토큰 사용량
            cost: 비용 정보
        """
        try:
            with mlflow.start_span(name=span_name) as span:
                span.set_usage(
                    num_prompt_tokens=usage.input_tokens,
                    num_completion_tokens=usage.output_tokens,
                )
                span.set_attributes({
                    "cost_usd": cost.total_cost,
                    "input_cost_usd": cost.input_cost,
                    "output_cost_usd": cost.output_cost,
                })
        except Exception as e:
            logger.warning(f"⚠️ Failed to log span usage: {str(e)}")

    def _calculate_cost(
        self,
        model: str,
        usage: TokenUsage,
        endpoint: Optional[str] = None,
    ) -> CostInfo:
        """
        비용 계산

        Args:
            model: 모델 이름
            usage: 토큰 사용량
            endpoint: 엔드포인트 이름

        Returns:
            비용 정보
        """
        # 엔드포인트 이름으로 비용 조회
        cost_config = self.MODEL_COSTS.get(
            endpoint or model,
            self.MODEL_COSTS["default"]
        )

        input_cost_per_mtok = cost_config["input_cost_per_mtok"]
        output_cost_per_mtok = cost_config["output_cost_per_mtok"]

        input_cost = (usage.input_tokens / 1_000_000) * input_cost_per_mtok
        output_cost = (usage.output_tokens / 1_000_000) * output_cost_per_mtok

        return CostInfo(input_cost=input_cost, output_cost=output_cost)

    def get_summary(self) -> dict:
        """누적 통계 조회"""
        return {
            "total_usage": self.total_usage.to_dict(),
            "total_cost": self.total_cost.to_dict(),
            "num_calls": len(self.session_logs),
        }

    def reset(self) -> None:
        """초기화"""
        self.total_usage = TokenUsage()
        self.total_cost = CostInfo()
        self.session_logs.clear()
        logger.info("✓ Token tracker reset")

"""
TokenTracker 단위 테스트
"""

import pytest
from src.llm_utils.token_tracker import TokenTracker, TokenUsage, CostInfo


class TestTokenUsage:
    """TokenUsage 클래스 테스트"""

    def test_token_usage_initialization(self):
        usage = TokenUsage(input_tokens=100, output_tokens=50)
        assert usage.input_tokens == 100
        assert usage.output_tokens == 50
        assert usage.total_tokens == 150

    def test_token_usage_to_dict(self):
        usage = TokenUsage(input_tokens=100, output_tokens=50)
        result = usage.to_dict()
        assert result["input_tokens"] == 100
        assert result["output_tokens"] == 50
        assert result["total_tokens"] == 150


class TestCostInfo:
    """CostInfo 클래스 테스트"""

    def test_cost_info_initialization(self):
        cost = CostInfo(input_cost=0.0001, output_cost=0.0002)
        assert cost.input_cost == 0.0001
        assert cost.output_cost == 0.0002
        assert abs(cost.total_cost - 0.0003) < 1e-6

    def test_cost_info_to_dict(self):
        cost = CostInfo(input_cost=0.0001, output_cost=0.0002)
        result = cost.to_dict()
        assert result["input_cost_usd"] == 0.0001
        assert result["output_cost_usd"] == 0.0002
        assert abs(result["total_cost_usd"] - 0.0003) < 1e-6


class TestTokenTracker:
    """TokenTracker 클래스 테스트"""

    def test_token_tracker_initialization(self):
        tracker = TokenTracker()
        assert tracker.total_usage.total_tokens == 0
        assert tracker.total_cost.total_cost == 0.0
        assert len(tracker.session_logs) == 0

    def test_track_usage_mid_performance(self):
        tracker = TokenTracker()
        cost = tracker.track_usage(
            model="mid_performance_llm",
            input_tokens=1000,
            output_tokens=500,
            endpoint="mid_performance_llm",
        )

        assert tracker.total_usage.total_tokens == 1500
        assert tracker.total_usage.input_tokens == 1000
        assert tracker.total_usage.output_tokens == 500

        # 비용 검증 (input: 0.003$/M, output: 0.009$/M)
        expected_cost = (1000 / 1_000_000) * 0.003 + (500 / 1_000_000) * 0.009
        assert abs(cost.total_cost - expected_cost) < 1e-9

    def test_track_usage_low_performance(self):
        tracker = TokenTracker()
        cost = tracker.track_usage(
            model="low_performance_llm",
            input_tokens=1000,
            output_tokens=500,
            endpoint="low_performance_llm",
        )

        # 비용 검증 (input: 0.0005$/M, output: 0.0015$/M)
        expected_cost = (1000 / 1_000_000) * 0.0005 + (500 / 1_000_000) * 0.0015
        assert abs(cost.total_cost - expected_cost) < 1e-9

    def test_track_usage_accumulation(self):
        tracker = TokenTracker()

        # 첫 번째 호출
        tracker.track_usage(
            model="mid_performance_llm",
            input_tokens=1000,
            output_tokens=500,
            endpoint="mid_performance_llm",
        )

        # 두 번째 호출
        tracker.track_usage(
            model="low_performance_llm",
            input_tokens=2000,
            output_tokens=1000,
            endpoint="low_performance_llm",
        )

        assert tracker.total_usage.total_tokens == 4500
        assert tracker.total_usage.input_tokens == 3000
        assert tracker.total_usage.output_tokens == 1500
        assert len(tracker.session_logs) == 2

    def test_get_summary(self):
        tracker = TokenTracker()
        tracker.track_usage(
            model="mid_performance_llm",
            input_tokens=1000,
            output_tokens=500,
            endpoint="mid_performance_llm",
        )

        summary = tracker.get_summary()
        assert summary["total_usage"]["total_tokens"] == 1500
        assert summary["total_usage"]["input_tokens"] == 1000
        assert summary["total_usage"]["output_tokens"] == 500
        assert summary["num_calls"] == 1
        assert "total_cost" in summary

    def test_reset(self):
        tracker = TokenTracker()
        tracker.track_usage(
            model="mid_performance_llm",
            input_tokens=1000,
            output_tokens=500,
            endpoint="mid_performance_llm",
        )

        tracker.reset()

        assert tracker.total_usage.total_tokens == 0
        assert tracker.total_cost.total_cost == 0.0
        assert len(tracker.session_logs) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

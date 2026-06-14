"""script/llm/regime_news_summary_pipeline.py 단위 테스트

DB/S3/MLflow Gateway/MLflow Tracking 등 외부 연결은 모두 mock 처리하며,
실제 네트워크 호출은 발생하지 않는다.
"""

import json
from datetime import date
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from script.llm import regime_news_summary_pipeline as pipeline_module
from script.llm.regime_news_summary_pipeline import (
    DIR_STR,
    FALLBACK_TICKER_MAP,
    REQUIRED_KEYS,
    RegimeNewsSummaryPipeline,
    _date_str,
    _parse_llm_response,
)


@pytest.fixture(autouse=True)
def _isolate_mlflow_tracking(tmp_path, monkeypatch):
    """테스트 중 mlflow.trace/start_span이 리포지토리에 mlruns/를 만들지 않도록 격리"""
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"file://{tmp_path / 'mlruns'}")


@pytest.fixture
def pipeline(monkeypatch):
    mock_regime_loader = MagicMock()
    mock_news_loader = MagicMock()
    mock_news_loader.bucket = "fisa-news-archive"
    mock_gateway_client = MagicMock()
    mock_mlflow_logger = MagicMock()
    mock_s3_client = MagicMock()

    monkeypatch.setattr(pipeline_module, "RegimeDBLoader", MagicMock(return_value=mock_regime_loader))
    monkeypatch.setattr(pipeline_module, "S3NewsDataLoader", MagicMock(return_value=mock_news_loader))
    monkeypatch.setattr(pipeline_module, "GatewayClient", MagicMock(return_value=mock_gateway_client))
    monkeypatch.setattr(pipeline_module, "MLflowLogger", MagicMock(return_value=mock_mlflow_logger))
    monkeypatch.setattr(pipeline_module.boto3, "client", MagicMock(return_value=mock_s3_client))

    p = RegimeNewsSummaryPipeline(validate_connections=False)
    p._mocks = {
        "regime_loader": mock_regime_loader,
        "news_loader": mock_news_loader,
        "gateway_client": mock_gateway_client,
        "mlflow_logger": mock_mlflow_logger,
        "s3_client": mock_s3_client,
    }
    return p


def _sample_regime(**overrides):
    regime = {
        "ticker": "005930",
        "regime_id": 1,
        "start": date(2024, 1, 1),
        "end": date(2024, 1, 10),
        "days": 9,
        "direction": "상승",
        "cum_return": 0.05,
        "vol_trend": "증가",
    }
    regime.update(overrides)
    return regime


# ── 모듈 상수 ─────────────────────────────────────────────────────


def test_dir_str_mapping_covers_known_directions():
    assert DIR_STR["상승"] == "상승 ▲"
    assert DIR_STR["하락"] == "하락 ▼"


def test_required_keys_matches_regime_analysis_schema():
    assert REQUIRED_KEYS == {"cause", "evidence", "vol_insight", "confidence", "reasoning"}


# ── _date_str ────────────────────────────────────────────────────


def test_date_str_with_date_object():
    assert _date_str(date(2024, 1, 5)) == "2024-01-05"


def test_date_str_with_string_passthrough():
    assert _date_str("2024-01-05") == "2024-01-05"


# ── _parse_llm_response ──────────────────────────────────────────


def test_parse_llm_response_plain_json():
    text = (
        '{"cause": "a", "evidence": [], "vol_insight": "b", '
        '"confidence": 0.8, "reasoning": "c"}'
    )
    result = _parse_llm_response(text)
    assert result["cause"] == "a"
    assert result["confidence"] == 0.8


def test_parse_llm_response_markdown_fenced():
    text = (
        "분석 결과:\n```json\n"
        '{"cause": "a", "evidence": [], "vol_insight": "b", '
        '"confidence": 0.8, "reasoning": "c"}'
        "\n```"
    )
    result = _parse_llm_response(text)
    assert result["cause"] == "a"


def test_parse_llm_response_raises_on_empty():
    with pytest.raises(ValueError, match="비어"):
        _parse_llm_response("")


def test_parse_llm_response_raises_when_no_json_object():
    with pytest.raises(ValueError, match="JSON"):
        _parse_llm_response("결과를 생성할 수 없습니다.")


# ── _build_news_context ──────────────────────────────────────────


def test_build_news_context_returns_placeholder_when_empty(pipeline):
    assert pipeline._build_news_context([]) == "(해당 기간 뉴스 없음)"


def test_build_news_context_sorts_by_pub_date_and_truncates_long_articles(pipeline):
    long_text = "가" * 2000
    articles = [
        {"pub_date": "2024-01-02", "title": "두번째", "fulltext": "본문2"},
        {"pub_date": "2024-01-01", "title": "첫번째", "fulltext": long_text},
    ]

    context = pipeline._build_news_context(articles)

    assert context.index("첫번째") < context.index("두번째")
    assert "…" in context


def test_build_news_context_limits_to_max_news_count(pipeline):
    articles = [
        {"pub_date": f"2024-01-{i:02d}", "title": f"뉴스{i}", "fulltext": "내용"}
        for i in range(1, pipeline.MAX_NEWS_COUNT + 5)
    ]

    context = pipeline._build_news_context(articles)

    assert context.count("▶") == pipeline.MAX_NEWS_COUNT


# ── _fetch_regime_news (S3 + 중복 제거) ──────────────────────────


def test_fetch_regime_news_dedups_by_pub_date_and_title(pipeline):
    pipeline._mocks["news_loader"].load_news.return_value = [
        {"pub_date": "2024-01-01", "title": "A", "fulltext": "x"},
        {"pub_date": "2024-01-01", "title": "A", "fulltext": "x"},  # 중복
        {"pub_date": "2024-01-02", "title": "B", "fulltext": "y"},
    ]

    articles = pipeline._fetch_regime_news("005930", "2024-01-01", "2024-01-31")

    assert len(articles) == 2
    pipeline._mocks["news_loader"].load_news.assert_called_once_with(
        ticker="005930", start_date="2024-01-01", end_date="2024-01-31"
    )


# ── _get_ticker_info ──────────────────────────────────────────────


def test_get_ticker_info_uses_asset_table_when_available(pipeline):
    pipeline._mocks["regime_loader"].get_asset_info.return_value = {
        "ticker": "005930", "name": "삼성전자", "sector": "반도체",
    }

    info = pipeline._get_ticker_info("005930")

    assert info == {"name": "삼성전자", "sector": "반도체"}


def test_get_ticker_info_falls_back_to_ticker_map_when_asset_missing(pipeline):
    pipeline._mocks["regime_loader"].get_asset_info.return_value = None

    info = pipeline._get_ticker_info("005930")

    expected_name, expected_sector = FALLBACK_TICKER_MAP["005930"]
    assert info == {"name": expected_name, "sector": expected_sector}


def test_get_ticker_info_falls_back_to_ticker_code_when_unknown(pipeline):
    pipeline._mocks["regime_loader"].get_asset_info.return_value = None

    info = pipeline._get_ticker_info("999999")

    assert info == {"name": "999999", "sector": "기타"}


# ── S3 요약 저장 / 존재 확인 (idempotency) ───────────────────────


def test_summary_exists_returns_true_when_head_object_succeeds(pipeline):
    pipeline._mocks["s3_client"].head_object.return_value = {}

    assert pipeline.summary_exists("005930", "2024-01-01", "2024-01-10") is True


def test_summary_exists_returns_false_on_404(pipeline):
    pipeline._mocks["s3_client"].head_object.side_effect = ClientError(
        {"Error": {"Code": "404"}}, "HeadObject"
    )

    assert pipeline.summary_exists("005930", "2024-01-01", "2024-01-10") is False


def test_save_summary_to_s3_writes_expected_key_and_body(pipeline):
    ok = pipeline.save_summary_to_s3("005930", "2024-01-01", "2024-01-10", {"cause": "x"})

    assert ok is True
    _, kwargs = pipeline._mocks["s3_client"].put_object.call_args
    assert kwargs["Bucket"] == "fisa-news-archive"
    assert kwargs["Key"] == "summary/005930/2024-01-01_2024-01-10.json"
    assert json.loads(kwargs["Body"].decode("utf-8"))["cause"] == "x"


def test_save_summary_to_s3_returns_false_on_error(pipeline):
    pipeline._mocks["s3_client"].put_object.side_effect = RuntimeError("upload failed")

    ok = pipeline.save_summary_to_s3("005930", "2024-01-01", "2024-01-10", {"cause": "x"})

    assert ok is False


# ── process_ticker (idempotency / dry-run) ───────────────────────


def test_process_ticker_skips_existing_summary_when_not_forced(pipeline, monkeypatch):
    pipeline._mocks["regime_loader"].get_asset_info.return_value = {
        "ticker": "005930", "name": "삼성전자", "sector": "반도체",
    }
    monkeypatch.setattr(pipeline, "summary_exists", MagicMock(return_value=True))
    summarize_mock = MagicMock()
    monkeypatch.setattr(pipeline, "summarize_regime", summarize_mock)

    stats = pipeline.process_ticker("005930", [_sample_regime()], force=False, dry_run=False)

    assert stats == {"processed": 0, "skipped": 1, "failed": 0}
    summarize_mock.assert_not_called()


def test_process_ticker_force_reprocesses_existing_summary(pipeline, monkeypatch):
    pipeline._mocks["regime_loader"].get_asset_info.return_value = {
        "ticker": "005930", "name": "삼성전자", "sector": "반도체",
    }
    monkeypatch.setattr(pipeline, "summary_exists", MagicMock(return_value=True))
    monkeypatch.setattr(pipeline, "summarize_regime", MagicMock(return_value={"llm_analysis": {}}))
    save_mock = MagicMock(return_value=True)
    monkeypatch.setattr(pipeline, "save_summary_to_s3", save_mock)

    stats = pipeline.process_ticker("005930", [_sample_regime()], force=True, dry_run=False)

    assert stats == {"processed": 1, "skipped": 0, "failed": 0}
    save_mock.assert_called_once()


def test_process_ticker_dry_run_does_not_call_llm_or_save(pipeline, monkeypatch):
    pipeline._mocks["regime_loader"].get_asset_info.return_value = {
        "ticker": "005930", "name": "삼성전자", "sector": "반도체",
    }
    monkeypatch.setattr(pipeline, "summary_exists", MagicMock(return_value=False))
    summarize_mock = MagicMock()
    save_mock = MagicMock()
    monkeypatch.setattr(pipeline, "summarize_regime", summarize_mock)
    monkeypatch.setattr(pipeline, "save_summary_to_s3", save_mock)

    stats = pipeline.process_ticker("005930", [_sample_regime()], force=False, dry_run=True)

    assert stats == {"processed": 0, "skipped": 0, "failed": 0}
    summarize_mock.assert_not_called()
    save_mock.assert_not_called()


def test_process_ticker_counts_failures_without_raising(pipeline, monkeypatch):
    pipeline._mocks["regime_loader"].get_asset_info.return_value = {
        "ticker": "005930", "name": "삼성전자", "sector": "반도체",
    }
    monkeypatch.setattr(pipeline, "summary_exists", MagicMock(return_value=False))
    monkeypatch.setattr(pipeline, "summarize_regime", MagicMock(side_effect=RuntimeError("llm failed")))
    save_mock = MagicMock()
    monkeypatch.setattr(pipeline, "save_summary_to_s3", save_mock)

    stats = pipeline.process_ticker("005930", [_sample_regime()], force=False, dry_run=False)

    assert stats == {"processed": 0, "skipped": 0, "failed": 1}
    save_mock.assert_not_called()


# ── summarize_regime (prompt 렌더링 + gateway 호출) ──────────────


def test_summarize_regime_renders_prompt_and_parses_response(pipeline, monkeypatch):
    pipeline._mocks["news_loader"].load_news.return_value = []

    fake_response = json.dumps({
        "cause": "실적 호조",
        "evidence": [{"date": "2024-01-02", "quote": "...", "point": "..."}],
        "vol_insight": "변동성 증가",
        "confidence": 0.7,
        "reasoning": "근거 요약",
    })
    pipeline._mocks["gateway_client"].call_with_usage.return_value = (fake_response, 123, 45)

    monkeypatch.setattr(
        pipeline_module,
        "load_prompt",
        MagicMock(return_value=("시스템 프롬프트", "종목: {code} ({name}), 구간 {start}~{end}, news: {news_context}")),
    )

    ticker_info = {"name": "삼성전자", "sector": "반도체"}
    result = pipeline.summarize_regime(_sample_regime(), ticker_info)

    assert result["ticker"] == "005930"
    assert result["input_tokens"] == 123
    assert result["output_tokens"] == 45
    assert result["llm_analysis"]["cause"] == "실적 호조"

    sent_text = pipeline._mocks["gateway_client"].call_with_usage.call_args[1]["text"]
    assert "005930" in sent_text
    assert "삼성전자" in sent_text
    assert "2024-01-01" in sent_text and "2024-01-10" in sent_text


def test_summarize_regime_logs_mlflow_standard_token_usage_and_cost(pipeline, monkeypatch):
    """MLflow Trace UI의 Tokens/Cost 컬럼이 읽는 표준 span attribute
    (mlflow.chat.tokenUsage, mlflow.llm.cost)가 올바르게 설정되어야 한다."""
    pipeline._mocks["news_loader"].load_news.return_value = []

    fake_response = json.dumps({
        "cause": "실적 호조",
        "evidence": [],
        "vol_insight": "변동성 증가",
        "confidence": 0.7,
        "reasoning": "근거 요약",
    })
    pipeline._mocks["gateway_client"].call_with_usage.return_value = (fake_response, 100, 50)

    monkeypatch.setattr(
        pipeline_module,
        "load_prompt",
        MagicMock(return_value=("시스템 프롬프트", "{code} {name} {start} {end} {news_context}")),
    )

    mock_span = MagicMock()
    mock_start_span = MagicMock()
    mock_start_span.return_value.__enter__.return_value = mock_span
    mock_start_span.return_value.__exit__.return_value = False
    monkeypatch.setattr(pipeline_module.mlflow, "start_span", mock_start_span)

    ticker_info = {"name": "삼성전자", "sector": "반도체"}
    pipeline.summarize_regime(_sample_regime(), ticker_info)

    attrs = mock_span.set_attributes.call_args[0][0]
    assert attrs["mlflow.chat.tokenUsage"] == {
        "input_tokens": 100, "output_tokens": 50, "total_tokens": 150,
    }
    assert attrs["mlflow.llm.cost"]["input_cost"] == pytest.approx(100 / 1_000_000 * 0.0005)
    assert attrs["mlflow.llm.cost"]["output_cost"] == pytest.approx(50 / 1_000_000 * 0.0015)


def test_summarize_regime_raises_after_retries_when_response_missing_keys(pipeline, monkeypatch):
    pipeline._mocks["news_loader"].load_news.return_value = []
    pipeline._mocks["gateway_client"].call_with_usage.return_value = (
        json.dumps({"cause": "사유만 있음"}), 10, 5,
    )

    monkeypatch.setattr(
        pipeline_module,
        "load_prompt",
        MagicMock(return_value=("시스템 프롬프트", "{code} {name} {start} {end} {news_context}")),
    )
    monkeypatch.setattr(pipeline_module.time, "sleep", MagicMock())  # 재시도 대기 제거

    ticker_info = {"name": "삼성전자", "sector": "반도체"}
    with pytest.raises(RuntimeError, match="LLM 요약"):
        pipeline.summarize_regime(_sample_regime(), ticker_info)

    assert pipeline._mocks["gateway_client"].call_with_usage.call_count == pipeline.MAX_RETRIES

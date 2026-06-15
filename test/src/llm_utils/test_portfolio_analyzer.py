"""src/llm_utils/portfolio_analyzer.py 단위 테스트

DB / MLflow Gateway / MLflow Tracking / Prompt Registry 등 외부 연결은 모두
mock 처리하며, 실제 네트워크 호출은 발생하지 않는다.
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.llm_utils import portfolio_analyzer as pa
from src.llm_utils.portfolio_analyzer import (
    REQUIRED_KEYS,
    _build_holdings_payload,
    _get_invest_type,
    _parse_llm_response,
    aggregate_holdings,
    analyze_portfolio,
)


@pytest.fixture(autouse=True)
def _isolate_mlflow_tracking(tmp_path, monkeypatch):
    """mlflow.trace/start_span 이 리포지토리에 mlruns/ 를 만들지 않도록 격리"""
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"file://{tmp_path / 'mlruns'}")


def _full_analysis() -> dict:
    return {
        "overall_summary": "전반적으로 균형 잡힌 포트폴리오입니다.",
        "per_holding": [
            {"ticker": "005930", "comment": "최근 반도체 업황 회복으로 평가익 구간입니다."},
        ],
        "risk_alignment": "공격투자형 성향과 부합합니다.",
        "suggestions": "섹터 분산을 권장합니다.",
        "confidence": 0.8,
    }


# ── _parse_llm_response ──────────────────────────────────────────────


def test_parse_llm_response_plain_json():
    result = _parse_llm_response(json.dumps(_full_analysis()))
    assert result["confidence"] == 0.8


def test_parse_llm_response_markdown_fenced():
    text = "결과:\n```json\n" + json.dumps(_full_analysis()) + "\n```"
    assert _parse_llm_response(text)["overall_summary"].startswith("전반적")


def test_parse_llm_response_raises_on_empty():
    with pytest.raises(ValueError, match="비어"):
        _parse_llm_response("")


def test_parse_llm_response_raises_when_no_json_object():
    with pytest.raises(ValueError, match="JSON"):
        _parse_llm_response("분석 불가")


# ── aggregate_holdings (calcTotals/buildAiHtml 포팅) ─────────────────


def test_aggregate_holdings_weights_sectors_and_return():
    holdings = [
        {"id": "005930", "qty": 10, "avgPrice": 100, "snapshotPrice": 150},  # +50%
        {"id": "000660", "qty": 10, "avgPrice": 200, "snapshotPrice": 100},  # -50%
    ]
    asset_info = {
        "005930": {"name": "삼성전자", "sector": "반도체"},
        "000660": {"name": "SK하이닉스", "sector": "반도체"},
    }

    agg = aggregate_holdings(holdings, asset_info)

    assert agg["total_value"] == pytest.approx(2500.0, abs=0.01)
    assert agg["total_cost"] == pytest.approx(3000.0, abs=0.01)
    assert agg["total_return_pct"] == pytest.approx(-16.67, abs=0.01)
    # 평가액 내림차순 정렬 → 005930(1500) 이 top
    assert agg["top_holding"]["ticker"] == "005930"
    assert agg["top_holding"]["weight_pct"] == pytest.approx(60.0, abs=0.1)
    assert agg["sector_breakdown"][0]["sector"] == "반도체"
    assert agg["sector_breakdown"][0]["weight_pct"] == pytest.approx(100.0, abs=0.1)
    assert agg["top_gainers"][0]["ticker"] == "005930"
    assert agg["top_losers"][0]["ticker"] == "000660"
    # 진입가(avgPrice)/현재가(snapshotPrice)가 종목별로 노출되어야 한다
    top = agg["weights"][0]
    assert top["entry_price"] == pytest.approx(100.0, abs=0.01)
    assert top["current_price"] == pytest.approx(150.0, abs=0.01)


def test_aggregate_holdings_uses_avg_price_when_snapshot_price_missing():
    holdings = [{"id": "005930", "qty": 5, "avgPrice": 100}]
    agg = aggregate_holdings(holdings, {})
    # snapshotPrice 없음 → 현재가=평균가 → 손익 0
    assert agg["total_return_pct"] == pytest.approx(0.0, abs=0.01)
    assert agg["weights"][0]["ticker"] == "005930"
    assert agg["weights"][0]["sector"] == "기타"


def test_aggregate_holdings_uppercases_ticker():
    agg = aggregate_holdings([{"id": "aapl", "qty": 1, "avgPrice": 10}], {})
    assert agg["weights"][0]["ticker"] == "AAPL"


# ── 투자 성향 / 종목별 payload ───────────────────────────────────────


def test_get_invest_type_returns_value():
    user = SimpleNamespace(invest_type="공격투자형", birth_year=1990, gender="M")
    assert _get_invest_type(user) == "공격투자형"


def test_get_invest_type_defaults_when_missing():
    assert _get_invest_type(None) == "미상"
    assert _get_invest_type(SimpleNamespace(invest_type=None)) == "미상"


def test_build_holdings_payload_merges_price_and_news():
    weights = [{
        "ticker": "005930", "name": "삼성전자", "sector": "반도체",
        "entry_price": 100.0, "current_price": 150.0,
        "weight_pct": 60.0, "pnl_pct": 50.0, "cur_val": 1500.0, "cost": 1000.0,
    }]
    news_by_ticker = {
        "005930": {
            "name": "삼성전자",
            "news": [{"end_date": "2026-06-01", "direction": "상승",
                      "cause": "실적 호조", "vol_insight": ""}],
        }
    }
    payload = _build_holdings_payload(weights, news_by_ticker)
    assert len(payload) == 1
    item = payload[0]
    # 4종 핵심 입력 중 종목 단위(진입가·현재가·뉴스)가 한 종목으로 묶여야 한다
    assert item["entry_price"] == 100.0
    assert item["current_price"] == 150.0
    assert item["news"][0]["cause"] == "실적 호조"
    # 보조 집계(비중·손익)도 함께 노출
    assert item["weight_pct"] == 60.0
    assert item["pnl_pct"] == 50.0


def test_build_holdings_payload_empty_news_when_missing():
    weights = [{
        "ticker": "AAPL", "name": "Apple", "sector": "기타",
        "entry_price": 10.0, "current_price": 10.0,
        "weight_pct": 100.0, "pnl_pct": 0.0, "cur_val": 10.0, "cost": 10.0,
    }]
    payload = _build_holdings_payload(weights, {})
    assert payload[0]["news"] == []


# ── S3 요약 로드 (summary/{ticker}/{start}_{end}.json) ───────────────


def test_parse_end_date_from_key():
    key = "summary/005930/2026-05-01_2026-06-10.json"
    assert pa._parse_end_date_from_key(key) == pa.date(2026, 6, 10)
    assert pa._parse_end_date_from_key("summary/005930/badkey.json") is None
    assert pa._parse_end_date_from_key("summary/005930/2026-05-01_2026-06-10.txt") is None


def test_fetch_recent_news_returns_empty_when_no_client():
    assert pa._fetch_recent_news(None, "bucket", "005930", pa.date.today()) == []


def _s3_with_summaries(objects: dict[str, dict]):
    """objects: {key: payload} 를 반환하는 가짜 S3 클라이언트"""
    s3 = MagicMock()
    paginator = MagicMock()
    paginator.paginate.return_value = [
        {"Contents": [{"Key": k} for k in objects]}
    ]
    s3.get_paginator.return_value = paginator

    def _get_object(Bucket, Key):  # noqa: N803
        body = MagicMock()
        body.read.return_value = json.dumps(objects[Key]).encode("utf-8")
        return {"Body": body}

    s3.get_object.side_effect = _get_object
    return s3


def test_fetch_recent_news_filters_by_cutoff_and_extracts_llm_analysis():
    objects = {
        # cutoff 이후 (포함)
        "summary/005930/2026-05-20_2026-06-05.json": {
            "end": "2026-06-05", "direction": "상승",
            "llm_analysis": {"cause": "실적 호조", "vol_insight": "거래량 증가"},
        },
        # cutoff 이전 (제외)
        "summary/005930/2025-01-01_2025-01-10.json": {
            "end": "2025-01-10", "direction": "하락",
            "llm_analysis": {"cause": "오래된 뉴스", "vol_insight": ""},
        },
    }
    s3 = _s3_with_summaries(objects)
    cutoff = pa.date(2026, 5, 15)

    news = pa._fetch_recent_news(s3, "fisa-news-archive", "005930", cutoff)

    assert len(news) == 1
    assert news[0]["cause"] == "실적 호조"
    assert news[0]["direction"] == "상승"
    assert news[0]["end_date"] == "2026-06-05"
    s3.get_paginator.return_value.paginate.assert_called_once_with(
        Bucket="fisa-news-archive", Prefix="summary/005930/"
    )


def test_fetch_recent_news_skips_payload_without_cause():
    objects = {
        "summary/005930/2026-05-20_2026-06-05.json": {
            "end": "2026-06-05", "llm_analysis": {"vol_insight": "x"},  # cause 없음
        },
    }
    s3 = _s3_with_summaries(objects)
    news = pa._fetch_recent_news(s3, "b", "005930", pa.date(2026, 1, 1))
    assert news == []


# ── analyze_portfolio (happy path + graceful degradation) ────────────


def _patch_pipeline(monkeypatch, gateway_return):
    monkeypatch.setattr(pa, "_load_asset_info", MagicMock(return_value={
        "005930": {"name": "삼성전자", "sector": "반도체"},
    }))
    monkeypatch.setattr(pa, "_get_s3_client", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(pa, "_fetch_recent_news", MagicMock(return_value=[
        {"end_date": "2026-06-01", "direction": "상승", "cause": "실적 호조", "vol_insight": "거래량 증가"},
    ]))
    monkeypatch.setattr(pa, "_load_prompt", MagicMock(return_value=(
        "시스템", "성향:{invest_type}\n종목:{holdings_json}\n섹터:{sector_breakdown}",
    )))
    mock_gateway = MagicMock()
    mock_gateway.call_with_usage.return_value = gateway_return
    monkeypatch.setattr(pa, "GatewayClient", MagicMock(return_value=mock_gateway))
    return mock_gateway


def _fake_db(user):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = user
    return db


def test_analyze_portfolio_happy_path(monkeypatch):
    mock_gateway = _patch_pipeline(
        monkeypatch, (json.dumps(_full_analysis()), 120, 60)
    )
    db = _fake_db(SimpleNamespace(invest_type="공격투자형", birth_year=1990, gender="M"))

    result = analyze_portfolio(
        "user1", [{"id": "005930", "qty": 10, "avgPrice": 100, "snapshotPrice": 150}], db
    )

    assert result is not None
    assert REQUIRED_KEYS <= result.keys()
    # 렌더링된 프롬프트에 마스킹된 프로필/종목/뉴스가 반영되었는지 확인
    sent_text = mock_gateway.call_with_usage.call_args[1]["text"]
    assert "공격투자형" in sent_text
    assert "삼성전자" in sent_text
    assert "실적 호조" in sent_text


def test_analyze_portfolio_sets_mlflow_standard_token_usage_and_cost(monkeypatch):
    """MLflow Trace UI 의 Tokens/Cost 컬럼이 읽는 표준 span attribute
    (mlflow.chat.tokenUsage, mlflow.llm.cost) 가 올바르게 설정되어야 한다."""
    _patch_pipeline(monkeypatch, (json.dumps(_full_analysis()), 100, 50))
    db = _fake_db(None)

    mock_span = MagicMock()
    mock_start_span = MagicMock()
    mock_start_span.return_value.__enter__.return_value = mock_span
    mock_start_span.return_value.__exit__.return_value = False
    monkeypatch.setattr(pa.mlflow, "start_span", mock_start_span)

    analyze_portfolio("user1", [{"id": "005930", "qty": 1, "avgPrice": 100}], db)

    attrs = mock_span.set_attributes.call_args[0][0]
    assert attrs["mlflow.chat.tokenUsage"] == {
        "input_tokens": 100, "output_tokens": 50, "total_tokens": 150,
    }
    assert attrs["mlflow.llm.cost"]["input_cost"] == pytest.approx(100 / 1_000_000 * 0.003)
    assert attrs["mlflow.llm.cost"]["output_cost"] == pytest.approx(50 / 1_000_000 * 0.009)
    assert attrs["endpoint"] == "mid_performance_llm"
    # 보안: span 입력에 원본 PII 대신 종목 수/뉴스 수/투자 성향만 기록
    inputs = mock_span.set_inputs.call_args[0][0]
    assert inputs["endpoint"] == "mid_performance_llm"
    assert inputs["invest_type"] == "미상"  # db user=None → 미상


def test_analyze_portfolio_returns_none_on_empty_holdings():
    assert analyze_portfolio("user1", [], MagicMock()) is None


def test_analyze_portfolio_returns_none_when_gateway_fails(monkeypatch):
    monkeypatch.setattr(pa, "_load_asset_info", MagicMock(return_value={}))
    monkeypatch.setattr(pa, "_get_s3_client", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(pa, "_fetch_recent_news", MagicMock(return_value=[]))
    monkeypatch.setattr(pa, "_load_prompt", MagicMock(return_value=("", "{holdings_json}")))
    mock_gateway = MagicMock()
    mock_gateway.call_with_usage.side_effect = RuntimeError("gateway down")
    monkeypatch.setattr(pa, "GatewayClient", MagicMock(return_value=mock_gateway))
    db = _fake_db(None)

    result = analyze_portfolio(
        "user1", [{"id": "005930", "qty": 1, "avgPrice": 100}], db
    )

    assert result is None  # graceful degradation → 호출 측은 ai_analysis = NULL 저장


def test_analyze_portfolio_returns_none_when_prompt_missing(monkeypatch):
    monkeypatch.setattr(pa, "_load_asset_info", MagicMock(return_value={}))
    monkeypatch.setattr(pa, "_get_s3_client", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(pa, "_fetch_recent_news", MagicMock(return_value=[]))
    monkeypatch.setattr(pa, "_load_prompt", MagicMock(side_effect=RuntimeError("no prompt")))
    db = _fake_db(None)

    result = analyze_portfolio("user1", [{"id": "005930", "qty": 1, "avgPrice": 100}], db)

    assert result is None


def test_analyze_portfolio_returns_none_when_response_missing_keys(monkeypatch):
    _patch_pipeline(monkeypatch, (json.dumps({"overall_summary": "부분"}), 10, 5))
    db = _fake_db(None)

    result = analyze_portfolio("user1", [{"id": "005930", "qty": 1, "avgPrice": 100}], db)

    assert result is None  # 필수 키 누락 → None

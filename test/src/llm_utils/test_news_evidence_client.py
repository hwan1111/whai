"""src/llm_utils/news_evidence_client.py 단위 테스트

OpenRouter HTTP 호출은 모두 mock 하며 실제 네트워크 호출은 발생하지 않는다.
"""

from unittest.mock import MagicMock

import pytest

from src.llm_utils import news_evidence_client as nec
from src.llm_utils.news_evidence_client import (
    _annotation_urls,
    _from_annotations,
    _parse_sources,
    find_news_evidence,
)


@pytest.fixture(autouse=True)
def _isolate_mlflow_tracking(tmp_path, monkeypatch):
    """mlflow.set_experiment/trace 가 원격 서버를 건드리지 않도록 로컬 파일 백엔드로 격리"""
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"file://{tmp_path / 'mlruns'}")


# ── _parse_sources ───────────────────────────────────────────────────


def test_parse_sources_plain_json_array():
    content = '[{"ticker": "005930", "title": "삼성 호조", "url": "https://a.com/1"}]'
    out = _parse_sources(content)
    assert out == [{"ticker": "005930", "title": "삼성 호조", "url": "https://a.com/1"}]


def test_parse_sources_markdown_fenced_and_uppercases_ticker():
    content = "결과:\n```json\n[{\"ticker\": \"aapl\", \"title\": \"x\", \"url\": \"https://a.com\"}]\n```"
    out = _parse_sources(content)
    assert out[0]["ticker"] == "AAPL"


def test_parse_sources_drops_items_without_http_url_or_title():
    content = (
        '[{"ticker":"A","title":"ok","url":"https://a.com"},'
        '{"ticker":"B","title":"","url":"https://b.com"},'
        '{"ticker":"C","title":"noturl","url":"ftp://c"}]'
    )
    out = _parse_sources(content)
    assert [s["url"] for s in out] == ["https://a.com"]


def test_parse_sources_returns_empty_on_garbage():
    assert _parse_sources("") == []
    assert _parse_sources("설명만 있고 JSON 없음") == []
    assert _parse_sources("[broken json") == []


# ── annotations 헬퍼 ─────────────────────────────────────────────────


def test_annotation_urls_extracts_url_citations():
    annotations = [
        {"type": "url_citation", "url_citation": {"url": "https://a.com", "title": "A"}},
        {"type": "other", "url_citation": {"url": "https://skip.com"}},
    ]
    assert _annotation_urls(annotations) == {"https://a.com"}


def test_from_annotations_builds_sources_without_ticker():
    annotations = [
        {"type": "url_citation", "url_citation": {"url": "https://a.com", "title": "A"}},
    ]
    out = _from_annotations(annotations)
    assert out == [{"ticker": "", "title": "A", "url": "https://a.com"}]


# ── find_news_evidence (HTTP mock) ───────────────────────────────────


def _mock_response(status_code=200, content="", annotations=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = "error" if status_code != 200 else ""
    resp.json.return_value = {
        "choices": [{"message": {"content": content, "annotations": annotations}}]
    }
    return resp


def _patch_httpx(monkeypatch, response):
    client = MagicMock()
    client.__enter__.return_value = client
    client.__exit__.return_value = False
    client.post.return_value = response
    monkeypatch.setattr(nec.httpx, "Client", MagicMock(return_value=client))
    return client


def test_find_news_evidence_no_api_key_returns_empty(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert find_news_evidence([{"ticker": "005930", "name": "삼성전자"}]) == []


def test_find_news_evidence_empty_holdings_returns_empty(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    assert find_news_evidence([]) == []


def test_find_news_evidence_cross_validates_against_annotations(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    # 모델 JSON 의 두 번째 url 은 annotation 에 없음(환각) → 걸러져야 한다
    content = (
        '[{"ticker":"005930","title":"진짜","url":"https://real.com"},'
        '{"ticker":"000660","title":"가짜","url":"https://hallucination.com"}]'
    )
    annotations = [{"type": "url_citation", "url_citation": {"url": "https://real.com", "title": "진짜"}}]
    _patch_httpx(monkeypatch, _mock_response(content=content, annotations=annotations))

    out = find_news_evidence([{"ticker": "005930", "name": "삼성전자"}])
    assert [s["url"] for s in out] == ["https://real.com"]


def test_find_news_evidence_falls_back_to_annotations_when_json_unparseable(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    annotations = [{"type": "url_citation", "url_citation": {"url": "https://real.com", "title": "제목"}}]
    _patch_httpx(monkeypatch, _mock_response(content="JSON 아님", annotations=annotations))

    out = find_news_evidence([{"ticker": "005930", "name": "삼성전자"}])
    assert out == [{"ticker": "", "title": "제목", "url": "https://real.com"}]


def test_find_news_evidence_dedupes_and_limits(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    content = (
        '[{"ticker":"A","title":"t1","url":"https://a.com"},'
        '{"ticker":"A","title":"dup","url":"https://a.com"},'
        '{"ticker":"B","title":"t2","url":"https://b.com"}]'
    )
    # annotations 없음 → 교차검증 생략, 모델 JSON 그대로 사용
    _patch_httpx(monkeypatch, _mock_response(content=content, annotations=None))

    out = find_news_evidence([{"ticker": "A", "name": "A"}], max_sources=1)
    assert len(out) == 1
    assert out[0]["url"] == "https://a.com"


def test_find_news_evidence_renders_analysis_into_prompt(monkeypatch):
    """portfolio_analysis 출력(analysis)이 프롬프트 메시지에 치환되어 전송된다."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    content = '[{"ticker":"005930","title":"t","url":"https://a.com"}]'
    client = _patch_httpx(monkeypatch, _mock_response(content=content, annotations=None))
    analysis = {
        "overall_summary": "반도체 집중 포트폴리오",
        "per_holding": [{"ticker": "005930", "comment": "HBM 수요"}],
    }

    find_news_evidence([{"ticker": "005930", "name": "삼성전자"}], analysis=analysis)

    body = client.post.call_args[1]["json"]
    joined = " ".join(m["content"] for m in body["messages"])
    assert "반도체 집중 포트폴리오" in joined  # overall_summary 치환
    assert "삼성전자(005930)" in joined        # holdings 치환
    assert body["tools"][0]["type"] == "openrouter:web_search"


def test_find_news_evidence_non_200_returns_empty(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    _patch_httpx(monkeypatch, _mock_response(status_code=500))
    assert find_news_evidence([{"ticker": "005930", "name": "삼성전자"}]) == []


def test_find_news_evidence_swallows_exceptions(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    client = MagicMock()
    client.__enter__.return_value = client
    client.__exit__.return_value = False
    client.post.side_effect = RuntimeError("network down")
    monkeypatch.setattr(nec.httpx, "Client", MagicMock(return_value=client))
    assert find_news_evidence([{"ticker": "005930", "name": "삼성전자"}]) == []

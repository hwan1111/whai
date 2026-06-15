"""포트폴리오 분석 근거용 '관련 최신 뉴스' 검색 클라이언트 (OpenRouter 직접 호출)

MLflow Gateway 는 OpenRouter 의 `openrouter:web_search` server tool 을 요청 스키마
단계에서 거부한다(tools[].type 은 function/uc_function 만 허용). 따라서 이 근거 뉴스
검색만 OpenRouter API 를 직접 호출한다.

포트폴리오 종합 분석 본문은 기존대로 MLflow Gateway(`mid_performance_llm`)로 생성하며,
이 모듈은 그 결과에 덧붙일 '관련 최신 뉴스' 링크(sources)만 만든다. 분석 본문의 입력
근거(국면 뉴스 요약)와는 별개이므로, UI 에서도 "근거"가 아닌 "관련 최신 뉴스"로 표기한다.

신뢰성:
  - 응답 `message.annotations[].url_citation.url` 이 OpenRouter 가 실제로 검색·인용한
    검증된 출처 URL 이다. 모델이 JSON 으로 돌려준 url 을 이 annotation 집합과 교차검증해
    환각 링크를 거른다.
  - 키 미설정 / 네트워크 / 파싱 실패 등 어떤 단계든 실패하면 빈 리스트를 반환해
    호출 측(포트폴리오 분석)이 graceful 하게 degrade 하도록 한다.

보안(.claude/rules/security.md): 종목 티커/종목명만 전송하며 보유 수량·평가액 등 원본
PII 는 전송하지 않는다.
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Optional

import httpx
import mlflow
import yaml
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

_ENV_FILE = Path(__file__).parent.parent.parent / ".env"
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE, override=True)

# 프롬프트는 MLflow Prompt Registry(UI 등록) 우선, 로컬 YAML fallback.
# portfolio_analysis 의 _load_prompt 패턴과 동일하며 prompt_registry 설정과 동기화한다.
_PROMPT_KEY = "portfolio_news_evidence"
_LOCAL_PROMPT_YAML = (
    Path(__file__).parent.parent.parent
    / "model" / "llm" / "prompts" / "portfolio_news_evidence.yaml"
)

# OpenRouter 직접 호출 설정 (게이트웨이 우회)
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
# 근거 뉴스 검색 모델 — 게이트웨이 mid 와 동일 계열(haiku) 기본값, env 로 교체 가능.
DEFAULT_MODEL = "anthropic/claude-3-haiku"
TIMEOUT_SECONDS = 90.0
MAX_SOURCES = 6
MAX_TOKENS = 700
TEMPERATURE = 0.2

# 포트폴리오 분석(MLflow Gateway)과 다른 경로(OpenRouter 직접)·모델·과금(web search)을
# 쓰므로 trace 도 별도 experiment 로 분리한다. 포트폴리오 분석 trace 밖에서 호출해야
# 독립 trace 로 기록된다(child span 으로 흡수되지 않도록).
EXPERIMENT_NAME = "portfolio_news_evidence"


def _parse_sources(content: str) -> list[dict[str, str]]:
    """LLM content 에서 [{ticker, title, url}] JSON 배열 추출 (코드펜스 대응)"""
    content = (content or "").strip()
    if not content:
        return []
    m = re.search(r"\[.*\]", content, re.DOTALL)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except (json.JSONDecodeError, ValueError):
        return []
    out: list[dict[str, str]] = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url", "")).strip()
        title = str(item.get("title", "")).strip()
        if url.startswith("http") and title:
            out.append({
                "ticker": str(item.get("ticker", "")).strip().upper(),
                "title": title,
                "url": url,
            })
    return out


def _annotation_urls(annotations: Any) -> set[str]:
    """응답 annotations 에서 실제 인용된 url_citation URL 집합 추출"""
    urls: set[str] = set()
    if not isinstance(annotations, list):
        return urls
    for ann in annotations:
        if isinstance(ann, dict) and ann.get("type") == "url_citation":
            url = str(ann.get("url_citation", {}).get("url", "")).strip()
            if url:
                urls.add(url)
    return urls


def _from_annotations(annotations: Any) -> list[dict[str, str]]:
    """모델 JSON 파싱 실패 시 fallback — annotations 만으로 sources 구성 (ticker 없음)"""
    out: list[dict[str, str]] = []
    if not isinstance(annotations, list):
        return out
    for ann in annotations:
        if isinstance(ann, dict) and ann.get("type") == "url_citation":
            uc = ann.get("url_citation", {})
            url = str(uc.get("url", "")).strip()
            title = str(uc.get("title", "")).strip() or url
            if url.startswith("http"):
                out.append({"ticker": "", "title": title, "url": url})
    return out


def _render(template: str, **kwargs: str) -> str:
    """템플릿 변수 치환 (정규식 기반 — .format() 금지, JSON 예시 중괄호와 충돌 방지)

    `{key}`, `{{key}}`, `{{ key }}` 형식을 모두 동일 placeholder 로 인식한다.
    """
    result = template
    for key, value in kwargs.items():
        pattern = r"\{{1,2}\s*" + re.escape(key) + r"\s*\}{1,2}"
        result = re.sub(pattern, lambda _m, v=str(value): v, result)
    return result


def _load_prompt_messages() -> list[dict[str, str]]:
    """portfolio_news_evidence 프롬프트 로드 → 메시지 템플릿 리스트(변수 미치환).

    MLflow Prompt Registry(Chat) 우선 → 로컬 YAML fallback.
    `portfolio_analysis` 의 _load_prompt 패턴과 동일.

    Returns:
        [{"role", "content"}] — content 는 아직 변수 치환 전 템플릿.

    Raises:
        RuntimeError: MLflow·로컬 YAML 모두에서 찾지 못했을 때(상위에서 graceful 처리).
    """
    from src.llm_utils.prompt_registry import MLFLOW_PROMPTS_CONFIG

    config = MLFLOW_PROMPTS_CONFIG.get(_PROMPT_KEY, {})
    name = config.get("name", _PROMPT_KEY)
    version = config.get("version", "1")
    uri = f"prompts:/{name}/{version}"

    # 1) MLflow Prompt Registry 시도
    try:
        prompt_version = mlflow.genai.load_prompt(uri)
        template_raw = getattr(prompt_version, "template", None)
        if template_raw is None:
            template_raw = getattr(prompt_version, "text", str(prompt_version))

        if isinstance(template_raw, list):  # Chat 타입 → 메시지 리스트
            msgs = [
                {"role": str(m.get("role", "user")), "content": str(m.get("content", ""))}
                for m in template_raw
                if isinstance(m, dict) and m.get("content")
            ]
            if msgs:
                logger.info("✓ portfolio_news_evidence 프롬프트 로드: MLflow (%s)", uri)
                return msgs
        else:  # Text 타입 → 단일 user 메시지
            logger.info("✓ portfolio_news_evidence 프롬프트 로드: MLflow (%s)", uri)
            return [{"role": "user", "content": str(template_raw).strip()}]
    except Exception as e:  # noqa: BLE001
        logger.warning("✗ MLflow 프롬프트 로드 실패 (%s): %s", uri, e)

    # 2) 로컬 YAML fallback
    if _LOCAL_PROMPT_YAML.exists():
        with open(_LOCAL_PROMPT_YAML, encoding="utf-8") as f:
            local = yaml.safe_load(f) or {}
        msgs = []
        system = str(local.get("system", "")).strip()
        if system:
            msgs.append({"role": "system", "content": system})
        template = str(local.get("template", "")).strip()
        if template:
            msgs.append({"role": "user", "content": template})
        if msgs:
            logger.info("→ portfolio_news_evidence 로컬 YAML 사용 (%s)", _LOCAL_PROMPT_YAML.name)
            return msgs

    raise RuntimeError(
        f"portfolio_news_evidence 프롬프트를 찾을 수 없습니다 (MLflow: {uri}, 로컬: {_LOCAL_PROMPT_YAML})"
    )


def _build_template_vars(
    holdings: list[dict[str, str]],
    analysis: Optional[dict[str, Any]],
) -> dict[str, str]:
    """프롬프트 템플릿 변수 구성 — 보유 종목 + portfolio_analysis 출력"""
    analysis = analysis or {}
    return {
        "holdings": ", ".join(f"{h.get('name') or h['ticker']}({h['ticker']})" for h in holdings),
        "overall_summary": str(analysis.get("overall_summary", "")),
        "per_holding": json.dumps(analysis.get("per_holding", []), ensure_ascii=False),
        "risk_alignment": str(analysis.get("risk_alignment", "")),
        "suggestions": str(analysis.get("suggestions", "")),
    }


def find_news_evidence(
    holdings: list[dict[str, str]],
    analysis: Optional[dict[str, Any]] = None,
    max_sources: int = MAX_SOURCES,
) -> list[dict[str, str]]:
    """포트폴리오 분석 결과를 뒷받침하는 관련 뉴스 링크를 OpenRouter web search 로 찾는다.

    프롬프트는 MLflow Prompt Registry(`portfolio_news_evidence`)에서 로드하며, 입력으로
    portfolio_analysis 의 출력(analysis)을 받아 그 분석을 뒷받침하는 뉴스를 검색한다.
    포트폴리오 분석(MLflow Gateway)과 별개 경로/모델/과금이므로 `portfolio_news_evidence`
    experiment 로 trace 를 분리한다(포트폴리오 분석 trace 밖에서 호출).

    Args:
        holdings: [{"ticker": "005930", "name": "삼성전자"}, ...] (현금성 자산 제외)
        analysis: portfolio_analysis 출력 dict (overall_summary/per_holding 등). None 가능.
        max_sources: 반환할 최대 뉴스 수

    Returns:
        [{"ticker", "title", "url"}, ...] — 실패 시 빈 리스트 (graceful degrade).
        url 은 OpenRouter annotations 와 교차검증된 실제 출처 링크.
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key or not holdings:
        if not api_key:
            logger.warning("OPENROUTER_API_KEY 미설정 — 근거 뉴스 검색 생략")
        return []

    try:
        mlflow.set_experiment(EXPERIMENT_NAME)
    except Exception as e:  # noqa: BLE001
        logger.warning("MLflow 실험 설정 실패 (계속 진행): %s", e)

    try:
        return _find_news_evidence_traced(holdings, analysis, max_sources)
    except Exception as e:  # noqa: BLE001
        logger.warning("근거 뉴스 검색 중 예외 (분석은 유지): %s", e)
        return []


@mlflow.trace
def _find_news_evidence_traced(
    holdings: list[dict[str, str]],
    analysis: Optional[dict[str, Any]],
    max_sources: int,
) -> list[dict[str, str]]:
    """실제 OpenRouter web search 호출 (MLflow 트레이스 대상)

    보안: api_key 는 @mlflow.trace 가 인자를 span input 으로 기록하므로 인자로 받지 않고
    함수 내부에서 환경변수로 직접 읽는다(트레이스에 키가 노출되지 않도록).
    """
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    base_url = os.getenv("OPENROUTER_BASE_URL", DEFAULT_BASE_URL)
    model = os.getenv("OPENROUTER_NEWS_MODEL", DEFAULT_MODEL)

    template_vars = _build_template_vars(holdings, analysis)
    messages = [
        {"role": m["role"], "content": _render(m["content"], **template_vars)}
        for m in _load_prompt_messages()
    ]

    body = {
        "model": model,
        "messages": messages,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "tools": [{
            "type": "openrouter:web_search",
            "parameters": {"max_results": max_sources},
        }],
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    with mlflow.start_span(name="news_evidence_search") as span:
        # 보안: 티커만 기록 (보유 수량·평가액 등 PII 미기록)
        span.set_inputs({"tickers": [h["ticker"] for h in holdings], "model": model})

        with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
            response = client.post(f"{base_url}/chat/completions", json=body, headers=headers)
        if response.status_code != 200:
            logger.warning(
                "근거 뉴스 검색 실패 (status=%s): %s",
                response.status_code, response.text[:300],
            )
            span.set_outputs({"sources_count": 0})
            return []

        result = response.json()
        message = (result.get("choices") or [{}])[0].get("message", {})
        annotations = message.get("annotations")

        sources = _parse_sources(message.get("content", ""))
        valid_urls = _annotation_urls(annotations)
        if valid_urls:
            # 모델 JSON 의 url 을 실제 인용 url 과 교차검증 → 환각 링크 제거.
            # 교차검증 결과가 비면 annotations 만으로 fallback (ticker 없음).
            filtered = [s for s in sources if s["url"] in valid_urls]
            sources = filtered or _from_annotations(annotations)

        # url 기준 중복 제거 (순서 유지)
        seen: set[str] = set()
        deduped: list[dict[str, str]] = []
        for s in sources:
            if s["url"] not in seen:
                seen.add(s["url"])
                deduped.append(s)
        deduped = deduped[:max_sources]

        _record_usage(span, result.get("usage") or {}, model, len(deduped))
        return deduped


def _record_usage(span: Any, usage: dict[str, Any], model: str, sources_count: int) -> None:
    """OpenRouter usage 를 MLflow Trace 표준 span attribute 로 기록.

    web search 추가 과금까지 포함된 OpenRouter 의 실제 비용(usage.cost)을 그대로 쓴다.
    """
    input_tokens = int(usage.get("prompt_tokens", 0) or 0)
    output_tokens = int(usage.get("completion_tokens", 0) or 0)
    web_search_requests = (usage.get("server_tool_use") or {}).get("web_search_requests", 0)
    span.set_outputs({"sources_count": sources_count})
    span.set_attributes({
        "mlflow.chat.tokenUsage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
        # OpenRouter 가 web search 비용까지 합산해 돌려주는 실제 비용.
        "mlflow.llm.cost": {"total_cost": float(usage.get("cost", 0.0) or 0.0)},
        "web_search_requests": web_search_requests,
        "model": model,
    })

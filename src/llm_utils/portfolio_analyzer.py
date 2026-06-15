"""
포트폴리오 스냅샷 LLM 종합 분석 모듈

`my-report` 페이지에서 새 스냅샷을 저장할 때, 보유 종목/섹터 구성·뉴스·투자자
프로필을 종합해 LLM 포트폴리오 분석을 생성한다.

흐름:
  1. 보유 종목 집계 (종목별 비중, 섹터 구성, 손익, 수익/손실 상위, 총 수익률)
     — 프론트엔드 `calcTotals`/`buildAiHtml` 로직을 Python으로 포팅
  2. 보유 종목별 최근 30일 국면 뉴스 요약 조회
     (S3 s3://fisa-news-archive/summary/{ticker}/{start}_{end}.json)
  3. 투자자 프로필 조회 (user.invest_type, birth_year, gender) — 개인화용
  4. `portfolio_analysis` 프롬프트 로드 (MLflow Prompt Registry 우선, 로컬 YAML fallback)
  5. MLflow Gateway(`mid_performance_llm`)로 LLM 호출 — `@mlflow.trace` + start_span,
     `mlflow.chat.tokenUsage` / `mlflow.llm.cost` span attribute 기록
  6. JSON 응답 파싱 후 반환

MLflow Gateway / Prompt Registry / 뉴스·프로필 데이터가 없을 경우 graceful 하게
degrade 한다 (예외를 잡고 None 반환 → 호출 측은 ai_analysis = NULL 저장).

보안(.claude/rules/security.md): 보유 종목은 PII 이므로 INFO 이상 레벨로 로깅하지
않으며, MLflow span 속성에도 원본 PII(보유 수량·평가액·생년)는 넣지 않는다.
"""

import json
import logging
import os
import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

import boto3
import mlflow
import yaml
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from sqlalchemy.orm import Session

from backend.models.asset import Asset
from backend.models.user import User
from src.llm_utils.gateway_client import GatewayClient
from src.llm_utils.token_tracker import TokenTracker

logger = logging.getLogger(__name__)

# 모든 자격증명/설정(AWS_S3_BUCKET, MLFLOW_*, AWS 키 등)은 프로젝트 루트의
# `.env` 에서 로드한다. `.env` 은 참조하지 않는다.
_ENV_FILE = Path(__file__).parent.parent.parent / ".env"
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE, override=True)

# ── 상수 ─────────────────────────────────────────────────────────────
GATEWAY_ENDPOINT = "mid_performance_llm"
EXPERIMENT_NAME = "portfolio_analysis"
NEWS_DAYS = 30
MAX_TOKENS = 1200
TEMPERATURE = 0.4
MAX_NEWS_PER_TICKER = 3

# 국면 뉴스 요약은 S3 에 적재되어 있다 (regime_news_summary_pipeline 산출물).
#   arn:aws:s3:::fisa-news-archive/summary/{ticker}/{start}_{end}.json
S3_REGION = "ap-northeast-2"
S3_DEFAULT_BUCKET = "fisa-news-archive"
SUMMARY_PREFIX = "summary"

# 현금성/비주식 자산 — 뉴스 조회에서 제외
CASH_IDS = {"USD", "KRW", "CASH"}

# portfolio_analysis/1 에 등록된 구조화 출력 스키마의 필수 키
REQUIRED_KEYS = {
    "overall_summary",
    "concentration",
    "sector_allocation",
    "performance",
    "news_highlights",
    "risk_alignment",
    "suggestions",
    "confidence",
}

# 프롬프트 설정 — MLFLOW_PROMPTS_CONFIG["portfolio_analysis"] 와 동기화
_PROMPT_KEY = "portfolio_analysis"
# TODO(owner): MLflow UI 에서 portfolio_analysis 프롬프트를 직접 등록할 것.
#   로컬 YAML fallback 경로(placeholder) — 파일이 없으면 자동으로 무시된다.
_LOCAL_PROMPT_YAML = (
    Path(__file__).parent.parent.parent / "model" / "llm" / "prompts" / "portfolio_analysis.yaml"
)


def _parse_llm_response(text: str) -> dict[str, Any]:
    """LLM 응답 텍스트에서 JSON 객체 추출 (마크다운 코드블록 대응)"""
    content = (text or "").strip()
    if not content:
        raise ValueError("LLM 응답이 비어 있습니다")

    if "```" in content:
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        if m:
            content = m.group(1)

    start, end = content.find("{"), content.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"응답에서 JSON을 찾을 수 없습니다: {content[:200]}")

    return json.loads(content[start:end])


def _render(template: str, **kwargs: str) -> str:
    """템플릿 변수 치환 (정규식 기반 — .format() 금지, JSON 예시 중괄호와 충돌 방지)

    `{key}`, `{{key}}`, `{{ key }}` 형식을 모두 동일 placeholder 로 인식한다.
    `model/llm/prompt_loader.render` 와 동일한 동작.
    """
    result = template
    for key, value in kwargs.items():
        pattern = r"\{{1,2}\s*" + re.escape(key) + r"\s*\}{1,2}"
        result = re.sub(pattern, lambda _m, v=str(value): v, result)
    return result


def _load_prompt() -> tuple[str, str]:
    """portfolio_analysis 프롬프트 로드 (MLflow Prompt Registry 우선 → 로컬 YAML fallback)

    `model/llm/prompt_loader.load_prompt` 패턴을 따른다.

    Returns:
        (system_prompt, user_template) — system 은 없을 수 있으며 그 경우 빈 문자열.

    Raises:
        RuntimeError: MLflow 와 로컬 YAML 모두에서 프롬프트를 찾지 못했을 때.
    """
    from src.llm_utils.prompt_registry import MLFLOW_PROMPTS_CONFIG

    config = MLFLOW_PROMPTS_CONFIG.get(_PROMPT_KEY, {})
    mlflow_name = config.get("name", _PROMPT_KEY)
    mlflow_version = config.get("version", "1")
    mlflow_uri = f"prompts:/{mlflow_name}/{mlflow_version}"

    # 1) MLflow Prompt Registry 시도
    try:
        prompt_version = mlflow.genai.load_prompt(mlflow_uri)
        template_raw = getattr(prompt_version, "template", None)
        if template_raw is None:
            template_raw = getattr(prompt_version, "text", str(prompt_version))

        if isinstance(template_raw, list):
            template = json.dumps(template_raw, ensure_ascii=False, indent=2)
        else:
            template = str(template_raw).strip()

        logger.info("✓ portfolio_analysis 프롬프트 로드: MLflow (%s)", mlflow_uri)
        return "", template
    except Exception as e:  # noqa: BLE001
        logger.warning("✗ MLflow 프롬프트 로드 실패 (%s): %s", mlflow_uri, e)

    # 2) 로컬 YAML fallback (placeholder — 미존재 시 graceful 실패)
    if _LOCAL_PROMPT_YAML.exists():
        with open(_LOCAL_PROMPT_YAML, encoding="utf-8") as f:
            local = yaml.safe_load(f) or {}
        system = str(local.get("system", "")).strip()
        template = str(local.get("template", "")).strip()
        if template:
            logger.info("→ portfolio_analysis 로컬 YAML 사용 (%s)", _LOCAL_PROMPT_YAML.name)
            return system, template

    raise RuntimeError(
        f"portfolio_analysis 프롬프트를 찾을 수 없습니다 "
        f"(MLflow: {mlflow_uri}, 로컬: {_LOCAL_PROMPT_YAML})"
    )


# ── 보유 종목 집계 (프론트 calcTotals/buildAiHtml 포팅) ───────────────


def _dec(value: Any) -> Decimal:
    """임의 숫자형을 Decimal 로 안전 변환 (float 직접 변환 시 오차 방지)"""
    return Decimal(str(value if value is not None else 0))


def aggregate_holdings(
    holdings: list[dict[str, Any]],
    asset_info: dict[str, dict[str, str]],
) -> dict[str, Any]:
    """보유 종목을 집계해 구조화된 입력 데이터를 생성한다.

    프론트엔드 `calcTotals` / `buildAiHtml` 의 비중·섹터·수익/손실 상위·총 수익률
    집계 로직을 Python 으로 포팅한 것.

    Args:
        holdings: [{id, qty, avgPrice, snapshotPrice?}, ...]
        asset_info: {ticker: {"name": ..., "sector": ...}}

    Returns:
        집계 결과 dict (가격/금액은 float 로 직렬화)
    """
    rows: list[dict[str, Any]] = []
    total_val = Decimal(0)
    total_cost = Decimal(0)

    for h in holdings:
        ticker = str(h.get("id", "")).upper()
        qty = _dec(h.get("qty"))
        avg_price = _dec(h.get("avgPrice"))
        snap_price = h.get("snapshotPrice")
        cur_price = _dec(snap_price) if snap_price is not None else avg_price

        cur_val = qty * cur_price
        cost = qty * avg_price
        info = asset_info.get(ticker, {})

        rows.append({
            "ticker": ticker,
            "name": info.get("name") or ticker,
            "sector": info.get("sector") or "기타",
            "cur_val": cur_val,
            "cost": cost,
        })
        total_val += cur_val
        total_cost += cost

    rows.sort(key=lambda r: r["cur_val"], reverse=True)

    def _pct(part: Decimal, whole: Decimal) -> float:
        return float(part / whole * 100) if whole > 0 else 0.0

    weights = []
    sectors: dict[str, float] = {}
    for r in rows:
        weight = _pct(r["cur_val"], total_val)
        pnl_pct = _pct(r["cur_val"] - r["cost"], r["cost"])
        weights.append({
            "ticker": r["ticker"],
            "name": r["name"],
            "sector": r["sector"],
            "weight_pct": round(weight, 1),
            "pnl_pct": round(pnl_pct, 1),
            "cur_val": float(r["cur_val"]),
            "cost": float(r["cost"]),
        })
        sectors[r["sector"]] = sectors.get(r["sector"], 0.0) + weight

    sector_list = sorted(sectors.items(), key=lambda kv: kv[1], reverse=True)
    gainers = sorted(
        [w for w in weights if w["pnl_pct"] > 0], key=lambda w: w["pnl_pct"], reverse=True
    )
    losers = sorted([w for w in weights if w["pnl_pct"] < 0], key=lambda w: w["pnl_pct"])
    total_return_pct = _pct(total_val - total_cost, total_cost)

    return {
        "weights": weights,
        "sector_breakdown": [{"sector": s, "weight_pct": round(w, 1)} for s, w in sector_list],
        "top_gainers": gainers[:3],
        "top_losers": losers[:3],
        "top_holding": weights[0] if weights else None,
        "total_value": float(total_val),
        "total_cost": float(total_cost),
        "total_return_pct": round(total_return_pct, 2),
    }


# ── 뉴스 / 자산 / 프로필 조회 ─────────────────────────────────────────


def _load_asset_info(db: Session, tickers: list[str]) -> dict[str, dict[str, str]]:
    """asset 테이블에서 종목명/섹터 조회"""
    if not tickers:
        return {}
    rows = db.query(Asset).filter(Asset.ticker.in_(tickers)).all()
    return {a.ticker.upper(): {"name": a.name, "sector": a.sector or "기타"} for a in rows}


def _get_s3_client() -> Optional[Any]:
    """S3 클라이언트 생성 (자격증명/네트워크 미비 시 None — graceful degrade)"""
    try:
        return boto3.client("s3", region_name=S3_REGION)
    except Exception as e:  # noqa: BLE001
        logger.warning("S3 클라이언트 생성 실패 (뉴스 없이 진행): %s", e)
        return None


def _get_s3_bucket() -> str:
    return os.getenv("AWS_S3_BUCKET", S3_DEFAULT_BUCKET)


def _parse_end_date_from_key(key: str) -> Optional[date]:
    """`summary/{ticker}/{start}_{end}.json` 키에서 종료일(end) 파싱"""
    filename = key.rsplit("/", 1)[-1]
    if not filename.endswith(".json"):
        return None
    parts = filename[: -len(".json")].split("_")
    if len(parts) != 2:
        return None
    try:
        return datetime.strptime(parts[1], "%Y-%m-%d").date()
    except ValueError:
        return None


def _fetch_recent_news(
    s3_client: Any,
    bucket: str,
    ticker: str,
    cutoff: date,
) -> list[dict[str, str]]:
    """S3 `summary/{ticker}/` 에서 종료일이 cutoff 이후인 국면 요약을 로드한다.

    경로: s3://{bucket}/summary/{ticker}/{start}_{end}.json
    (regime_news_summary_pipeline 가 적재한 산출물 — `llm_analysis` 필드 포함)
    """
    if s3_client is None:
        return []

    prefix = f"{SUMMARY_PREFIX}/{ticker}/"
    try:
        candidates: list[tuple[date, str]] = []
        paginator = s3_client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                end = _parse_end_date_from_key(obj["Key"])
                if end and end >= cutoff:
                    candidates.append((end, obj["Key"]))

        candidates.sort(reverse=True)  # 최신 종료일 우선
        news: list[dict[str, str]] = []
        for end, key in candidates[:MAX_NEWS_PER_TICKER]:
            payload = _load_summary_object(s3_client, bucket, key)
            if payload is None:
                continue
            analysis = payload.get("llm_analysis") or {}
            cause = analysis.get("cause")
            if not cause:
                continue
            news.append({
                "end_date": str(payload.get("end") or end.isoformat()),
                "direction": str(payload.get("direction") or ""),
                "cause": str(cause),
                "vol_insight": str(analysis.get("vol_insight") or ""),
            })
        return news
    except ClientError as e:
        logger.warning("S3 요약 목록 조회 실패 (%s): %s", prefix, e)
        return []
    except Exception as e:  # noqa: BLE001
        logger.warning("S3 요약 조회 중 예외 (%s): %s", prefix, e)
        return []


def _load_summary_object(s3_client: Any, bucket: str, key: str) -> Optional[dict[str, Any]]:
    """S3 요약 JSON 객체 1건 로드"""
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        content = response["Body"].read().decode("utf-8")
        return json.loads(content)
    except Exception as e:  # noqa: BLE001
        logger.warning("S3 요약 객체 읽기 실패 (%s): %s", key, e)
        return None


def _build_news_context(news_by_ticker: dict[str, dict[str, Any]]) -> str:
    """종목별 뉴스 요약을 프롬프트용 텍스트 블록으로 변환"""
    if not news_by_ticker:
        return "(최근 30일 관련 뉴스 없음)"

    parts = []
    for ticker, info in news_by_ticker.items():
        items = info["news"]
        if not items:
            continue
        header = f"▶ {info['name']}({ticker})"
        lines = [
            f"  · [{n['end_date']} {n['direction']}] {n['cause']}"
            + (f" / 수급: {n['vol_insight']}" if n["vol_insight"] else "")
            for n in items
        ]
        parts.append(header + "\n" + "\n".join(lines))

    return "\n\n".join(parts) if parts else "(최근 30일 관련 뉴스 없음)"


def _age_band(birth_year: Optional[int]) -> str:
    """생년 → 연령대 문자열 (원본 생년은 노출/로깅하지 않기 위해 밴드로 변환)"""
    if not birth_year:
        return "미상"
    age = date.today().year - int(birth_year)
    if age < 20:
        return "10대"
    if age >= 70:
        return "70대 이상"
    return f"{(age // 10) * 10}대"


def _gender_label(gender: Any) -> str:
    value = getattr(gender, "value", gender)
    return {"M": "남성", "F": "여성"}.get(value, "미상")


def _build_investor_profile(user: Optional[User]) -> dict[str, str]:
    """투자자 프로필을 마스킹된 표현으로 구성 (원본 PII 미노출)"""
    if user is None:
        return {"invest_type": "미상", "age_band": "미상", "gender": "미상"}
    return {
        "invest_type": user.invest_type or "미상",
        "age_band": _age_band(user.birth_year),
        "gender": _gender_label(user.gender),
    }


# ── 메인 분석 진입점 ──────────────────────────────────────────────────


def analyze_portfolio(
    user_id: str,
    holdings: list[dict[str, Any]],
    db: Session,
) -> Optional[dict[str, Any]]:
    """스냅샷 보유 종목에 대한 LLM 종합 포트폴리오 분석을 생성한다.

    Args:
        user_id: 사용자 ID
        holdings: [{id, qty, avgPrice, snapshotPrice?}, ...]
        db: SQLAlchemy 세션

    Returns:
        분석 결과 dict (Output JSON schema 준수) 또는 None
        (Gateway/Prompt Registry/데이터 미가용 등 어떤 단계든 실패 시 None).
    """
    if not holdings:
        return None

    try:
        # MLflow 실험 설정 (실패해도 분석은 계속)
        try:
            mlflow.set_experiment(EXPERIMENT_NAME)
        except Exception as e:  # noqa: BLE001
            logger.warning("MLflow 실험 설정 실패 (계속 진행): %s", e)

        return _analyze_portfolio_traced(user_id, holdings, db)
    except Exception as e:  # noqa: BLE001
        # PII 보호: 보유 종목 상세는 로깅하지 않고 종목 수만 기록
        logger.error("포트폴리오 분석 실패 (holdings=%d개): %s", len(holdings), e)
        return None


@mlflow.trace
def _analyze_portfolio_traced(
    user_id: str,
    holdings: list[dict[str, Any]],
    db: Session,
) -> dict[str, Any]:
    """실제 집계 + LLM 호출 (MLflow 트레이스 대상)"""
    tickers = [str(h.get("id", "")).upper() for h in holdings if h.get("id")]
    equity_tickers = [t for t in tickers if t not in CASH_IDS]

    asset_info = _load_asset_info(db, tickers)
    aggregation = aggregate_holdings(holdings, asset_info)

    # 종목별 최근 30일 뉴스 요약 — S3 summary/ 에서 로드
    s3_client = _get_s3_client()
    bucket = _get_s3_bucket()
    cutoff = date.today() - timedelta(days=NEWS_DAYS)
    news_by_ticker: dict[str, dict[str, Any]] = {}
    total_news = 0
    for ticker in equity_tickers:
        news = _fetch_recent_news(s3_client, bucket, ticker, cutoff)
        if news:
            name = asset_info.get(ticker, {}).get("name") or ticker
            news_by_ticker[ticker] = {"name": name, "news": news}
            total_news += len(news)
    news_context = _build_news_context(news_by_ticker)

    # 투자자 프로필
    user = db.query(User).filter(User.user_id == user_id).first()
    profile = _build_investor_profile(user)

    # 프롬프트 로드 & 렌더링
    system_prompt, user_template = _load_prompt()
    user_prompt = _render(
        user_template,
        invest_type=profile["invest_type"],
        age_band=profile["age_band"],
        gender=profile["gender"],
        total_return_pct=f"{aggregation['total_return_pct']:+.2f}%",
        total_value=f"{aggregation['total_value']:,.0f}",
        total_cost=f"{aggregation['total_cost']:,.0f}",
        holdings_json=json.dumps(aggregation["weights"], ensure_ascii=False),
        sector_breakdown=json.dumps(aggregation["sector_breakdown"], ensure_ascii=False),
        top_gainers=json.dumps(aggregation["top_gainers"], ensure_ascii=False),
        top_losers=json.dumps(aggregation["top_losers"], ensure_ascii=False),
        news_context=news_context,
    )
    full_prompt = f"{system_prompt}\n\n{user_prompt}".strip() if system_prompt else user_prompt

    gateway_client = GatewayClient(endpoint=GATEWAY_ENDPOINT, validate_connection=False)
    token_tracker = TokenTracker()

    with mlflow.start_span(name="portfolio_analysis") as span:
        # 보안: 원본 PII(보유 수량·평가액·생년) 대신 종목 수/뉴스 수/마스킹 프로필만 기록
        span.set_inputs({
            "tickers": tickers,
            "equity_count": len(equity_tickers),
            "news_count": total_news,
            "endpoint": GATEWAY_ENDPOINT,
            "investor_profile": profile,
        })

        content, input_tokens, output_tokens = gateway_client.call_with_usage(
            text=full_prompt,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
        )
        parsed = _parse_llm_response(content)
        missing = REQUIRED_KEYS - parsed.keys()
        if missing:
            raise ValueError(f"필수 키 누락: {missing}")

        cost_info = token_tracker.track_usage(
            model=GATEWAY_ENDPOINT,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            endpoint=GATEWAY_ENDPOINT,
        )

        span.set_outputs({"analysis": parsed})
        # MLflow Trace UI 의 Tokens/Cost 컬럼이 읽는 표준 span attribute 키.
        span.set_attributes({
            "mlflow.chat.tokenUsage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            },
            "mlflow.llm.cost": {
                "input_cost": cost_info.input_cost,
                "output_cost": cost_info.output_cost,
                "total_cost": cost_info.total_cost,
            },
            "endpoint": GATEWAY_ENDPOINT,
        })

    return parsed

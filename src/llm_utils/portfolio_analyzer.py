"""
포트폴리오 스냅샷 LLM 종합 분석 모듈

`my-report` 페이지에서 새 스냅샷을 저장할 때, 투자자 성향·보유 종목별 손익·뉴스를
종합해 LLM 포트폴리오 분석을 생성한다.

LLM 입력(4종 핵심 + 보조 집계):
  1. 투자 성향           — user.invest_type (whai_service.user)
  2. 종목별 최근 한달 뉴스 — S3 s3://fisa-news-archive/summary/{ticker}/{start}_{end}.json
  3. 진입가(평균 매입가)  — holdings[].avgPrice
  4. 현재가(스냅샷 가격)  — holdings[].snapshotPrice
  + 보조 집계: 종목별 비중·손익률, 섹터 구성, 총 수익률 (`calcTotals` 포팅)
  ※ 연령/성별 등 인구통계는 입력에서 제외한다.

흐름:
  1. 보유 종목 집계 (종목별 비중·진입가·현재가·손익, 섹터 구성, 총 수익률)
  2. 보유 종목별 최근 30일 국면 뉴스 요약 조회 (S3 summary/)
  3. 투자 성향(invest_type) 조회 — 개인화용
  4. 종목별 {진입가·현재가·손익·뉴스} 를 묶은 holdings payload 구성
  5. `portfolio_analysis` 프롬프트 로드 (MLflow Prompt Registry 우선, 로컬 YAML fallback)
  6. MLflow Gateway(`mid_performance_llm`)로 LLM 호출 — `@mlflow.trace` + start_span,
     `mlflow.chat.tokenUsage` / `mlflow.llm.cost` span attribute 기록
  7. JSON 응답 파싱 후 반환

MLflow Prompt Registry 계약 (프롬프트는 MLflow UI 에서 직접 등록/관리):
  - 템플릿 변수: {invest_type} {total_return_pct} {total_value} {total_cost}
    {holdings_json} {sector_breakdown}
    · holdings_json: [{ticker, name, sector, entry_price, current_price,
      weight_pct, pnl_pct, news:[{end_date, direction, cause, vol_insight}]}]
  - 출력 JSON 필수 키(REQUIRED_KEYS): overall_summary, per_holding,
    risk_alignment, suggestions, confidence
    · per_holding: 종목별 코멘트 리스트 (예: [{ticker, comment}])

MLflow Gateway / Prompt Registry / 뉴스·프로필 데이터가 없을 경우 graceful 하게
degrade 한다 (예외를 잡고 None 반환 → 호출 측은 ai_analysis = NULL 저장).

보안(.claude/rules/security.md): 보유 종목은 PII 이므로 INFO 이상 레벨로 로깅하지
않으며, MLflow span 속성에도 원본 PII(보유 수량·평가액)는 넣지 않는다.
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
# `.env` 에서 로드한다. `.env.local` 은 참조하지 않는다.
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

# portfolio_analysis 프롬프트(MLflow 등록)의 구조화 출력 스키마 필수 키.
# 입력을 4종 핵심(성향·뉴스·진입가·현재가) 중심으로 단순화하면서 출력도 축소했다.
REQUIRED_KEYS = {
    "overall_summary",
    "per_holding",
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
        # greedy `\{.*\}` 로 최외곽 객체를 잡는다 — per_holding 처럼 중첩 객체가
        # 있을 때 non-greedy 는 첫 내부 `}` 에서 잘려 파싱이 깨진다.
        m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", content, re.DOTALL)
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
            "entry_price": avg_price,
            "current_price": cur_price,
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
            "entry_price": float(r["entry_price"]),
            "current_price": float(r["current_price"]),
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


def _get_invest_type(user: Optional[User]) -> str:
    """투자 성향(invest_type) 조회 — 개인화 입력. 연령/성별 등은 입력에서 제외한다."""
    if user is None or not user.invest_type:
        return "미상"
    return user.invest_type


def _build_holdings_payload(
    weights: list[dict[str, Any]],
    news_by_ticker: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """종목별 {진입가·현재가·비중·손익·뉴스} 를 묶어 LLM 입력용 payload 로 구성.

    4종 핵심 입력(성향·뉴스·진입가·현재가) 중 종목 단위인 뉴스/진입가/현재가를
    한 종목 단위로 묶어, LLM 이 종목별로 일관되게 분석하도록 한다.
    """
    payload: list[dict[str, Any]] = []
    for w in weights:
        ticker = w["ticker"]
        payload.append({
            "ticker": ticker,
            "name": w["name"],
            "sector": w["sector"],
            "entry_price": w["entry_price"],
            "current_price": w["current_price"],
            "weight_pct": w["weight_pct"],
            "pnl_pct": w["pnl_pct"],
            "news": news_by_ticker.get(ticker, {}).get("news", []),
        })
    return payload


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

    # 투자 성향 (개인화 입력 — 연령/성별 등 인구통계는 제외)
    user = db.query(User).filter(User.user_id == user_id).first()
    invest_type = _get_invest_type(user)

    # 종목별 {진입가·현재가·비중·손익·뉴스} payload — 4종 핵심 입력의 종목 단위 묶음
    holdings_payload = _build_holdings_payload(aggregation["weights"], news_by_ticker)

    # 프롬프트 로드 & 렌더링
    system_prompt, user_template = _load_prompt()
    user_prompt = _render(
        user_template,
        invest_type=invest_type,
        total_return_pct=f"{aggregation['total_return_pct']:+.2f}%",
        total_value=f"{aggregation['total_value']:,.0f}",
        total_cost=f"{aggregation['total_cost']:,.0f}",
        holdings_json=json.dumps(holdings_payload, ensure_ascii=False),
        sector_breakdown=json.dumps(aggregation["sector_breakdown"], ensure_ascii=False),
    )
    full_prompt = f"{system_prompt}\n\n{user_prompt}".strip() if system_prompt else user_prompt

    gateway_client = GatewayClient(endpoint=GATEWAY_ENDPOINT, validate_connection=False)
    token_tracker = TokenTracker()

    with mlflow.start_span(name="portfolio_analysis") as span:
        # 보안: 원본 PII(보유 수량·평가액) 대신 종목 수/뉴스 수/투자 성향만 기록
        span.set_inputs({
            "tickers": tickers,
            "equity_count": len(equity_tickers),
            "news_count": total_news,
            "endpoint": GATEWAY_ENDPOINT,
            "invest_type": invest_type,
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

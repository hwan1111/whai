"""
국면(regime) × 뉴스 LLM 요약 파이프라인

흐름:
  1. Aiven MySQL `regime` 테이블에서 종목별 국면(상승/하락 구간) 목록을 조회
  2. 각 국면의 start_date ~ end_date 범위에 해당하는 뉴스를
     S3 `preprocessed_final/{ticker}/{year}/{month}/{date}.json` 에서 로드
  3. `model/llm/prompts/regime_analysis.yaml` 프롬프트(MLflow Prompt Registry 우선,
     실패 시 로컬 YAML)를 렌더링하여 MLflow Gateway(`low_performance_llm`)로 LLM 요약 생성
  4. 결과를 S3 `summary/{ticker}/{start_date}_{end_date}.json` 에 저장

사용법:
    python script/llm/regime_news_summary_pipeline.py --tickers 005930 000660
    python script/llm/regime_news_summary_pipeline.py --tickers 005930 --force
    python script/llm/regime_news_summary_pipeline.py --dry-run
"""

import argparse
import json
import logging
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

import boto3
import mlflow
from botocore.exceptions import ClientError

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from model.llm.prompt_loader import load_prompt, render  # noqa: E402
from src.data.regime_db_loader import RegimeDBLoader  # noqa: E402
from src.data.s3_news_loader import S3NewsDataLoader  # noqa: E402
from src.llm_utils.gateway_client import GatewayClient  # noqa: E402
from src.llm_utils.mlflow_logger import MLflowLogger  # noqa: E402
from src.llm_utils.token_tracker import TokenTracker  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

NEWS_PREFIX = "preprocessed_final"
SUMMARY_PREFIX = "summary"
EXPERIMENT_NAME = "regime_news_summary"

REQUIRED_KEYS = {"cause", "evidence", "vol_insight", "confidence", "reasoning"}

DIR_STR = {"상승": "상승 ▲", "하락": "하락 ▼"}

# asset 테이블에 종목 정보가 없을 때를 위한 최소 fallback
FALLBACK_TICKER_MAP: dict[str, tuple[str, str]] = {
    "005930": ("삼성전자", "반도체"),
    "000660": ("SK하이닉스", "반도체"),
    "005380": ("현대차", "자동차"),
    "000270": ("기아", "자동차"),
    "079550": ("LIG넥스원", "방산"),
    "051910": ("LG화학", "화학"),
    "096770": ("SK이노베이션", "에너지"),
    "055550": ("신한지주", "금융"),
    "105560": ("KB금융", "금융"),
    "012450": ("한화에어로스페이스", "방산"),
    "KOSPI200": ("코스피200", "시장지수"),
    "USD_KRW": ("원달러", "환율"),
}


def _date_str(value: Any) -> str:
    """date/datetime/문자열을 YYYY-MM-DD 문자열로 변환"""
    if isinstance(value, (date, datetime)):
        return value.strftime("%Y-%m-%d")
    return str(value)


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


class RegimeNewsSummaryPipeline:
    """국면 × 뉴스 LLM 요약 파이프라인"""

    MAX_NEWS_CHARS = 1_300
    MAX_NEWS_COUNT = 20
    NEWS_PRE = 0   # 국면 시작일 이전 버퍼일 — start_date ~ end_date만 사용
    NEWS_POST = 0  # 국면 종료일 이후 버퍼일 — start_date ~ end_date만 사용
    MAX_RETRIES = 3

    def __init__(
        self,
        bucket: Optional[str] = None,
        region: str = "ap-northeast-2",
        gateway_endpoint: str = "low_performance_llm",
        max_tokens: int = 800,
        temperature: float = 0.3,
        validate_connections: bool = True,
    ):
        """
        초기화

        Args:
            bucket: S3 버킷 (기본값: 환경변수 AWS_S3_BUCKET)
            region: AWS 리전
            gateway_endpoint: MLflow Gateway 엔드포인트 (기본값: low_performance_llm)
            max_tokens: LLM 응답 최대 토큰 수
            temperature: LLM 샘플링 온도
            validate_connections: Gateway/MLflow 연결 검증 여부
        """
        self.region = region
        self.gateway_endpoint = gateway_endpoint
        self.max_tokens = max_tokens
        self.temperature = temperature

        self.regime_loader = RegimeDBLoader()
        self.news_loader = S3NewsDataLoader(bucket=bucket, region=region, prefix=NEWS_PREFIX)
        self.bucket = self.news_loader.bucket
        self.s3_client = boto3.client("s3", region_name=region)

        self.gateway_client = GatewayClient(
            endpoint=gateway_endpoint, validate_connection=validate_connections
        )
        self.mlflow_logger = MLflowLogger(validate_connection=validate_connections)
        self.token_tracker = TokenTracker()

        logger.info(
            f"✓ 국면-뉴스 요약 파이프라인 초기화 완료 "
            f"(endpoint={gateway_endpoint}, bucket={self.bucket})"
        )

    # ── 뉴스 수집 ────────────────────────────────────────────────────

    def _fetch_regime_news(self, ticker: str, start_str: str, end_str: str) -> list[dict[str, Any]]:
        """국면 구간(start_date ~ end_date)의 뉴스를 S3에서 로드하고 중복 제거"""
        articles = self.news_loader.load_news(
            ticker=ticker, start_date=start_str, end_date=end_str
        )

        seen: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for article in articles:
            uid = f"{article.get('pub_date', '')}|{article.get('title', '')}"
            if uid not in seen:
                seen.add(uid)
                deduped.append(article)

        return deduped

    def _build_news_context(self, articles: list[dict[str, Any]]) -> str:
        """뉴스 목록을 프롬프트용 텍스트 블록으로 변환 (날짜순 정렬, 개수/길이 제한)"""
        if not articles:
            return "(해당 기간 뉴스 없음)"

        sorted_articles = sorted(articles, key=lambda a: a.get("pub_date", ""))[: self.MAX_NEWS_COUNT]

        parts = []
        for article in sorted_articles:
            fulltext = article.get("fulltext") or ""
            body = fulltext[: self.MAX_NEWS_CHARS]
            if len(fulltext) > self.MAX_NEWS_CHARS:
                body += "…"
            parts.append(f"▶ {article.get('pub_date', '')}  {article.get('title', '')}\n{body}")

        return "\n\n".join(parts)

    # ── 종목 메타데이터 ──────────────────────────────────────────────

    def _get_ticker_info(self, ticker: str) -> dict[str, str]:
        """asset 테이블에서 종목명/섹터 조회, 실패 시 fallback 매핑 사용"""
        info = self.regime_loader.get_asset_info(ticker)
        if info:
            return {"name": info["name"], "sector": info["sector"] or "기타"}

        name, sector = FALLBACK_TICKER_MAP.get(ticker, (ticker, "기타"))
        return {"name": name, "sector": sector}

    # ── LLM 요약 ─────────────────────────────────────────────────────

    @mlflow.trace
    def summarize_regime(self, regime: dict[str, Any], ticker_info: dict[str, str]) -> dict[str, Any]:
        """단일 국면에 대해 뉴스 컨텍스트를 구성하고 LLM 요약을 생성"""
        ticker = regime["ticker"]
        start_str = _date_str(regime["start"])
        end_str = _date_str(regime["end"])

        articles = self._fetch_regime_news(ticker, start_str, end_str)
        news_context = self._build_news_context(articles)

        system_prompt, user_template = load_prompt()

        cum_return = regime.get("cum_return") or 0.0
        direction = regime.get("direction", "")

        user_prompt = render(
            user_template,
            start=start_str,
            end=end_str,
            days=regime.get("days", 0),
            name=ticker_info["name"],
            code=ticker,
            dir_str=DIR_STR.get(direction, direction),
            cum_ret=f"{cum_return:+.1%}",
            direction=direction,
            vol_trend=regime.get("vol_trend", ""),
            sector=ticker_info["sector"],
            news_pre=self.NEWS_PRE,
            news_post=self.NEWS_POST,
            max_news_count=self.MAX_NEWS_COUNT,
            news_context=news_context,
        )

        full_prompt = f"{system_prompt}\n\n{user_prompt}"

        with mlflow.start_span(name="regime_summary") as span:
            span.set_inputs({
                "ticker": ticker,
                "start": start_str,
                "end": end_str,
                "news_count": len(articles),
                "endpoint": self.gateway_endpoint,
            })

            parsed: Optional[dict[str, Any]] = None
            input_tokens = output_tokens = 0
            last_error: Optional[Exception] = None

            for attempt in range(1, self.MAX_RETRIES + 1):
                try:
                    content, input_tokens, output_tokens = self.gateway_client.call_with_usage(
                        text=full_prompt,
                        temperature=self.temperature,
                        max_tokens=self.max_tokens,
                    )
                    candidate = _parse_llm_response(content)
                    missing = REQUIRED_KEYS - candidate.keys()
                    if missing:
                        raise ValueError(f"필수 키 누락: {missing}")
                    parsed = candidate
                    break
                except Exception as e:  # noqa: BLE001
                    last_error = e
                    logger.warning(
                        f"  ⚠️ LLM 요약 실패 ({ticker} {start_str}~{end_str}, "
                        f"시도 {attempt}/{self.MAX_RETRIES}): {e}"
                    )
                    if attempt < self.MAX_RETRIES:
                        time.sleep(2 * attempt)

            if parsed is None:
                span.set_outputs({"error": str(last_error)})
                raise RuntimeError(
                    f"LLM 요약 {self.MAX_RETRIES}회 연속 실패 "
                    f"({ticker} {start_str}~{end_str}): {last_error}"
                ) from last_error

            cost_info = self.token_tracker.track_usage(
                model=self.gateway_endpoint,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                endpoint=self.gateway_endpoint,
            )

            span.set_outputs({"summary": parsed})
            span.set_attributes({
                "mlflow.genai.prompt_tokens": input_tokens,
                "mlflow.genai.completion_tokens": output_tokens,
                "mlflow.genai.input_cost": cost_info.input_cost,
                "mlflow.genai.output_cost": cost_info.output_cost,
                "endpoint": self.gateway_endpoint,
            })

        return {
            "regime_id": regime.get("regime_id"),
            "ticker": ticker,
            "start": start_str,
            "end": end_str,
            "days": regime.get("days"),
            "direction": direction,
            "cum_return": cum_return,
            "vol_trend": regime.get("vol_trend"),
            "sector": ticker_info["sector"],
            "news_count": len(articles),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "input_cost_usd": cost_info.input_cost,
            "output_cost_usd": cost_info.output_cost,
            "llm_analysis": parsed,
        }

    # ── S3 저장 ──────────────────────────────────────────────────────

    def _summary_key(self, ticker: str, start_str: str, end_str: str) -> str:
        return f"{SUMMARY_PREFIX}/{ticker}/{start_str}_{end_str}.json"

    def summary_exists(self, ticker: str, start_str: str, end_str: str) -> bool:
        """해당 국면의 요약이 이미 S3에 존재하는지 확인"""
        key = self._summary_key(ticker, start_str, end_str)
        try:
            self.s3_client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code in ("404", "NoSuchKey"):
                return False
            logger.warning(f"⚠️ S3 head_object 실패 ({key}): {e}")
            return False

    def save_summary_to_s3(self, ticker: str, start_str: str, end_str: str, payload: dict[str, Any]) -> bool:
        """국면 요약 결과를 summary/{ticker}/{start}_{end}.json 으로 저장"""
        key = self._summary_key(ticker, start_str, end_str)
        try:
            content = json.dumps(payload, ensure_ascii=False, indent=2)
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=content.encode("utf-8"),
                ContentType="application/json",
            )
            logger.info(f"  ✓ 요약 저장: s3://{self.bucket}/{key}")
            return True
        except Exception as e:
            logger.error(f"  ❌ 요약 저장 실패 ({key}): {e}")
            return False

    # ── 종목/전체 실행 ───────────────────────────────────────────────

    @mlflow.trace
    def process_ticker(
        self,
        ticker: str,
        regimes: list[dict[str, Any]],
        force: bool = False,
        dry_run: bool = False,
    ) -> dict[str, int]:
        """종목의 국면 목록을 순회하며 요약 생성/저장"""
        ticker_info = self._get_ticker_info(ticker)
        processed = skipped = failed = 0

        with mlflow.start_span(name=f"process_ticker_{ticker}") as span:
            span.set_inputs({"ticker": ticker, "regime_count": len(regimes), "force": force})

            for regime in regimes:
                start_str = _date_str(regime["start"])
                end_str = _date_str(regime["end"])
                label = f"{ticker} [{start_str} ~ {end_str}] ({regime.get('days')}일, {regime.get('direction')})"

                if not force and self.summary_exists(ticker, start_str, end_str):
                    logger.info(f"  → 스킵 (이미 존재): {label}")
                    skipped += 1
                    continue

                if dry_run:
                    logger.info(f"  → [dry-run] 처리 대상: {label}")
                    continue

                try:
                    result = self.summarize_regime(regime, ticker_info)
                    if self.save_summary_to_s3(ticker, start_str, end_str, result):
                        processed += 1
                    else:
                        failed += 1
                except Exception as e:
                    logger.error(f"  ❌ 국면 처리 실패: {label} — {e}")
                    failed += 1

            span.set_outputs({"processed": processed, "skipped": skipped, "failed": failed})

        return {"processed": processed, "skipped": skipped, "failed": failed}

    def run(
        self,
        tickers: Optional[list[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        force: bool = False,
        dry_run: bool = False,
    ) -> None:
        """전체 파이프라인 실행"""
        if tickers is None:
            tickers = self.regime_loader.get_distinct_tickers()
            logger.info(f"종목 미지정 — regime 테이블의 전체 {len(tickers)}개 종목 처리")

        if not tickers:
            logger.warning("⚠️ 처리할 종목이 없습니다")
            return

        if not dry_run:
            self.mlflow_logger.start_run(
                experiment_name=EXPERIMENT_NAME,
                run_name=f"regime_news_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                tags={"endpoint": self.gateway_endpoint},
            )
            self.mlflow_logger.log_params({
                "tickers": ",".join(tickers),
                "start_date": start_date or "-",
                "end_date": end_date or "-",
                "endpoint": self.gateway_endpoint,
                "max_tokens": str(self.max_tokens),
                "temperature": str(self.temperature),
                "force": str(force),
            })

        try:
            ticker_metrics: dict[str, float] = {}

            for idx, ticker in enumerate(tickers, 1):
                regimes = self.regime_loader.load_regimes(
                    tickers=[ticker], start_date=start_date, end_date=end_date
                )
                if not regimes:
                    logger.warning(f"[{idx}/{len(tickers)}] ⚠️ {ticker}: 국면 데이터 없음")
                    continue

                logger.info(f"[{idx}/{len(tickers)}] {ticker}: {len(regimes)}개 국면 처리 시작")
                stats = self.process_ticker(ticker, regimes, force=force, dry_run=dry_run)
                logger.info(f"✓ {ticker} 완료: {stats}")

                ticker_metrics[f"{ticker}_processed"] = stats["processed"]
                ticker_metrics[f"{ticker}_skipped"] = stats["skipped"]
                ticker_metrics[f"{ticker}_failed"] = stats["failed"]

            if not dry_run:
                if ticker_metrics:
                    self.mlflow_logger.log_metrics(ticker_metrics)

                token_summary = self.token_tracker.get_summary()
                self.mlflow_logger.log_metrics({
                    "total_input_tokens": token_summary["total_usage"]["input_tokens"],
                    "total_output_tokens": token_summary["total_usage"]["output_tokens"],
                    "total_tokens": token_summary["total_usage"]["total_tokens"],
                    "total_cost_usd": token_summary["total_cost"]["total_cost_usd"],
                    "input_cost_usd": token_summary["total_cost"]["input_cost_usd"],
                    "output_cost_usd": token_summary["total_cost"]["output_cost_usd"],
                })
                self.token_tracker.log_to_mlflow()

                logger.info(
                    f"✅ 전체 완료 — 총 토큰: {token_summary['total_usage']['total_tokens']} "
                    f"(입력: {token_summary['total_usage']['input_tokens']}, "
                    f"출력: {token_summary['total_usage']['output_tokens']}), "
                    f"비용: ${token_summary['total_cost']['total_cost_usd']:.6f} USD"
                )

                self.mlflow_logger.end_run(status="FINISHED")

        except Exception:
            if not dry_run:
                self.mlflow_logger.end_run(status="FAILED")
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description="국면(regime) × 뉴스 LLM 요약 파이프라인")
    parser.add_argument(
        "--tickers", nargs="+", default=None,
        help="처리할 종목코드 목록 (기본값: regime 테이블의 전체 종목)",
    )
    parser.add_argument(
        "--start", default=None,
        help="조회 시작일 (YYYY-MM-DD). 이 날짜 이후까지 이어지는 국면을 포함 (오버랩 기준)",
    )
    parser.add_argument(
        "--end", default=None,
        help="조회 종료일 (YYYY-MM-DD). 이 날짜 이전에 시작하는 국면을 포함 (오버랩 기준)",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="S3에 이미 존재하는 요약도 재생성",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="LLM 호출/S3 저장 없이 처리 대상만 출력",
    )
    parser.add_argument(
        "--endpoint", default="low_performance_llm",
        choices=["low_performance_llm", "mid_performance_llm", "high_performance_llm"],
        help="MLflow Gateway 엔드포인트 (기본값: low_performance_llm)",
    )
    parser.add_argument("--max-tokens", type=int, default=800, help="LLM 응답 최대 토큰 수")
    parser.add_argument("--temperature", type=float, default=0.3, help="LLM 샘플링 온도")
    args = parser.parse_args()

    pipeline = RegimeNewsSummaryPipeline(
        gateway_endpoint=args.endpoint,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        validate_connections=not args.dry_run,
    )

    pipeline.run(
        tickers=args.tickers,
        start_date=args.start,
        end_date=args.end,
        force=args.force,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()

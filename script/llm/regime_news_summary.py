"""
가격 국면별 뉴스 LLM 요약

가격 국면(상승/하락 구간)을 탐지하고 각 구간의 뉴스를 LLM으로 분석하여
주가 이동 원인을 파악합니다.

출력: data/{TICKER_CODE}/regime_news_summary_{TICKER_CODE}.json

실행:
    python script/llm/regime_news_summary.py --ticker 005930
    python script/llm/regime_news_summary.py --ticker 005930 --provider gemini
    python script/llm/regime_news_summary.py --ticker 005930 --start 2020-01-01 --end 2026-05-12
    python script/llm/regime_news_summary.py --ticker 005930 --dry-run
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import timedelta
from pathlib import Path
from typing import Any, Optional

import boto3
import FinanceDataReader as fdr
import numpy as np
import pandas as pd
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from scipy import stats
from tenacity import retry, stop_after_attempt, wait_exponential

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import mlflow
from src.llm_utils.gateway_client import GatewayClient
from src.llm_utils.mlflow_logger import MLflowLogger
from src.llm_utils.prompt_registry import PromptRegistry

load_dotenv(".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

START_DATE = "2020-01-01"
END_DATE = "2026-05-28"

TICKER_MAP: dict[str, tuple[str, str]] = {
    "005930": ("삼성전자", "반도체"),
    "000660": ("SK하이닉스", "반도체"),
    "005380": ("현대차", "자동차"),
    "000270": ("기아", "자동차"),
    "079550": ("LIG디펜스앤에어로스페이스", "방산"),
    "051910": ("LG화학", "화학"),
    "096770": ("SK이노베이션", "에너지"),
    "055550": ("신한지주", "금융"),
    "105560": ("KB금융", "금융"),
    "012450": ("한화에어로스페이스", "방산"),
}

S3_BUCKET = "fisa-news-archive"
S3_PREFIX = "raw"

MAX_NEWS_CHARS = 1_300
MAX_NEWS_COUNT = 20  # 구간 내 최대 기사 수
NEWS_PRE = 1  # 구간 시작 전 뉴스 탐색 일수
NEWS_POST = 1  # 구간 종료 후 뉴스 탐색 일수

DIR_STR = {"상승": "상승 ▲", "하락": "하락 ▼"}

EXPERIMENT_NAME = "regime_news_summary"
DEFAULT_PROMPT_KEY = "regime_news_analysis"


class RegimeNewsSummary:
    """가격 국면별 뉴스 분석 파이프라인"""

    def __init__(
        self,
        ticker_code: str,
        ticker_name: str,
        sector: str,
        bucket: str = S3_BUCKET,
        region: str = "ap-northeast-2",
        prompt_key: str = DEFAULT_PROMPT_KEY,
    ):
        self.ticker_code = ticker_code
        self.ticker_name = ticker_name
        self.sector = sector
        self.bucket = bucket
        self.region = region
        self.prompt_key = prompt_key
        self.output_path = Path(f"data/{ticker_code}/regime_news_summary_{ticker_code}.json")
        self.mlflow_logger = MLflowLogger()
        self.prompt_registry = PromptRegistry()
        self.s3_client = boto3.client("s3", region_name=region)

    def _fetch_price_volume(
        self, start: str, end: str
    ) -> tuple[pd.Series, pd.Series]:
        """주가와 거래량 데이터 수집"""
        df = fdr.DataReader(self.ticker_code, start, end)
        return df["Close"].pct_change().dropna(), df["Volume"]

    def _detect_price_regimes(self, returns: pd.Series) -> list[dict]:
        """주가 국면 탐지 (상승/하락 구간)"""
        s = returns.dropna()
        dirs = s.map(lambda x: "상승" if x > 0 else "하락")
        regimes, cur_dir, cur_start, cur_dates = (
            [],
            dirs.iloc[0],
            dirs.index[0],
            [dirs.index[0]],
        )
        for date, d in dirs.iloc[1:].items():
            if d == cur_dir:
                cur_dates.append(date)
            else:
                regimes.append(
                    {
                        "direction": cur_dir,
                        "start": cur_start,
                        "end": cur_dates[-1],
                        "days": len(cur_dates),
                        "dates": cur_dates,
                    }
                )
                cur_dir, cur_start, cur_dates = d, date, [date]
        regimes.append(
            {
                "direction": cur_dir,
                "start": cur_start,
                "end": cur_dates[-1],
                "days": len(cur_dates),
                "dates": cur_dates,
            }
        )
        return regimes

    def _cum_return(self, returns: pd.Series, dates: list) -> float:
        """누적 수익률 계산"""
        valid = [d for d in dates if d in returns.index]
        return float((1 + returns.loc[valid]).prod() - 1) if valid else 0.0

    def _merge_noise(
        self, regimes: list[dict], returns: pd.Series
    ) -> list[dict]:
        """단기 노이즈 구간 병합"""
        r = returns.dropna()
        iqr = float(r.quantile(0.75)) - float(r.quantile(0.25))
        result = [{**reg, "dates": list(reg["dates"])} for reg in regimes]
        changed = True
        while changed:
            changed = False
            for i, reg in enumerate(result):
                if reg["days"] > 2:
                    continue
                if abs(self._cum_return(returns, reg["dates"])) >= iqr:
                    continue
                n = len(result)
                if n == 1:
                    break
                if i == 0:
                    dates = sorted(result[0]["dates"] + result[1]["dates"])
                    merged = {
                        **result[1],
                        "start": dates[0],
                        "end": dates[-1],
                        "days": len(dates),
                        "dates": dates,
                    }
                    result = [merged] + result[2:]
                elif i == n - 1:
                    dates = sorted(result[-2]["dates"] + result[-1]["dates"])
                    merged = {
                        **result[-2],
                        "start": dates[0],
                        "end": dates[-1],
                        "days": len(dates),
                        "dates": dates,
                    }
                    result = result[:-2] + [merged]
                else:
                    dates = sorted(
                        result[i - 1]["dates"] + reg["dates"] + result[i + 1]["dates"]
                    )
                    merged = {
                        **result[i - 1],
                        "start": dates[0],
                        "end": dates[-1],
                        "days": len(dates),
                        "dates": dates,
                    }
                    result = result[:i-1] + [merged] + result[i + 2 :]
                changed = True
                break
        return result

    def _vol_trend(
        self, volume: pd.Series, dates: list,
        slope_thr: float = 0.005, min_r: float = 0.3
    ) -> str:
        """거래량 추세 분석"""
        valid = [d for d in dates if d in volume.index]
        if len(valid) < 3:
            return "혼조"
        v = volume.loc[valid].values.astype(float)
        slope, _, r_value, _, _ = stats.linregress(np.arange(len(v)), v)
        if abs(r_value) < min_r:
            return "혼조"
        norm = slope / (v.mean() + 1e-9)
        if norm > slope_thr:
            return "증가"
        if norm < -slope_thr:
            return "감소"
        return "혼조"

    def _fetch_regime_news(
        self,
        start: pd.Timestamp,
        end: pd.Timestamp,
        pre_days: int,
        post_days: int,
    ) -> list[dict]:
        """S3에서 구간별 뉴스 수집"""
        articles = []
        cur = start - timedelta(days=pre_days)
        fin = end + timedelta(days=post_days)
        seen: set[str] = set()
        while cur <= fin:
            key = f"{S3_PREFIX}/{self.ticker_code}/{cur.year}/{cur.month:02d}/{cur.strftime('%Y-%m-%d')}.json"
            try:
                obj = self.s3_client.get_object(Bucket=self.bucket, Key=key)
                data = json.loads(obj["Body"].read().decode("utf-8"))
                uid = f"{data.get('pub_date','')}|{data.get('title','')}"
                if uid not in seen:
                    seen.add(uid)
                    articles.append(data)
            except ClientError as e:
                if e.response["Error"]["Code"] not in ("NoSuchKey", "404"):
                    logger.warning(f"S3 오류 {key}: {e}")
            except Exception as e:
                logger.warning(f"S3 fetch 실패 {key}: {e}")
            cur += timedelta(days=1)
        return articles

    def _build_news_context(self, articles: list[dict]) -> str:
        """뉴스 컨텍스트 구성"""
        if not articles:
            return "(해당 기간 뉴스 없음)"
        sorted_articles = sorted(articles, key=lambda x: x.get("pub_date", ""))[
            :MAX_NEWS_COUNT
        ]
        parts = []
        for a in sorted_articles:
            fulltext = a.get("fulltext") or ""
            body = fulltext[:MAX_NEWS_CHARS] + ("…" if len(fulltext) > MAX_NEWS_CHARS else "")
            parts.append(f"▶ {a.get('pub_date','')}  {a.get('title','')}\n{body}")
        return "\n\n".join(parts)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _analyze_regime_with_llm(
        self,
        regime_info: dict[str, Any],
        news_context: str,
        endpoint: str = "mid_performance_llm",
    ) -> tuple[dict[str, Any], int, int]:
        """LLM을 이용한 국면 분석"""
        try:
            # MLflow에서 프롬프트 로드
            prompt_context = {
                "start": regime_info["start_str"],
                "end": regime_info["end_str"],
                "days": regime_info["days"],
                "name": self.ticker_name,
                "code": self.ticker_code,
                "dir_str": regime_info["dir_str"],
                "cum_ret": regime_info["cum_ret"],
                "direction": regime_info["direction"],
                "vol_trend": regime_info["vol_trend"],
                "sector": self.sector,
                "news_pre": NEWS_PRE,
                "news_post": NEWS_POST,
                "max_news_count": MAX_NEWS_COUNT,
                "news_context": news_context,
            }

            with mlflow.start_span(name="regime_analysis_llm") as span:
                prompt, prompt_uri = self.prompt_registry.format_prompt(
                    self.prompt_key,
                    **prompt_context
                )

                span.set_inputs({
                    "regime_key": regime_info.get("regime_key"),
                    "days": regime_info["days"],
                    "direction": regime_info["direction"],
                    "prompt_key": self.prompt_key,
                    "prompt_uri": prompt_uri,
                })
                span.set_attributes({
                    "mlflow.promptUri": prompt_uri,
                    "endpoint": endpoint,
                    "prompt_length": len(prompt),
                })

                logger.info(f"📤 LLM 프롬프트 전송: {len(prompt)}자")

                gateway_client = GatewayClient(endpoint=endpoint, validate_connection=False)
                response, input_token, output_token = gateway_client.call_with_usage(
                    text=prompt,
                    max_tokens=1200,
                )

                span.set_outputs({
                    "response": response.strip(),
                    "input_token": input_token,
                    "output_token": output_token,
                })

                text = response.strip() if response else ""
                if not text:
                    raise ValueError("LLM 응답이 비어 있음")

                import re
                if "```" in text:
                    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
                    if m:
                        text = m.group(1)

                s, e = text.find("{"), text.rfind("}") + 1
                if s == -1 or e == 0:
                    raise ValueError(f"JSON 없음: {text[:120]}")

                answer = json.loads(text[s:e])
                return answer, input_token, output_token

        except Exception as e:
            logger.error(f"LLM 호출 실패: {e}")
            raise

    def load_existing_results(self) -> list[dict]:
        """기존 결과 로드"""
        if not self.output_path.exists():
            return []
        try:
            return json.loads(self.output_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"기존 결과 로드 실패: {e}")
            return []

    def save_results(self, results: list[dict]) -> None:
        """결과 저장"""
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def run(
        self,
        start: str = START_DATE,
        end: str = END_DATE,
        endpoint: str = "mid_performance_llm",
        dry_run: bool = False,
        rerun_ids: set[int] | None = None,
    ) -> None:
        """메인 실행 로직"""
        rerun_ids = rerun_ids or set()
        sleep_sec = 5  # LLM 호출 간 대기 시간

        logger.info(f"🔄 가격 국면 분석 시작: {self.ticker_name}({self.ticker_code})")
        logger.info(f"   기간: {start} ~ {end}")
        logger.info(f"   LLM endpoint: {endpoint}")

        # 가격 데이터 수집
        logger.info(f"📊 가격 데이터 수집")
        returns, volume = self._fetch_price_volume(start, end)
        raw_regimes = self._detect_price_regimes(returns)
        regimes = self._merge_noise(raw_regimes, returns)
        logger.info(f"   국면: {len(raw_regimes)}개 → 병합 후 {len(regimes)}개")

        # 기존 결과 로드
        results: list[dict] = self.load_existing_results()
        logger.info(f"   기존 결과: {len(results)}건 로드")

        REQUIRED_KEYS = {"cause", "evidence", "vol_insight", "confidence", "reasoning"}

        valid_done: set[str] = set()
        for r in results:
            key = r.get("regime_key", "")
            if not key:
                continue
            rid = r.get("regime_id")
            analysis = r.get("llm_analysis", {})
            is_valid = REQUIRED_KEYS.issubset(analysis.keys())
            if is_valid and rid not in rerun_ids:
                valid_done.add(key)
            else:
                reason = "강제 재처리" if rid in rerun_ids else "필수 키 누락"
                logger.info(f"   [{rid}] {reason}")
                results = [x for x in results if x.get("regime_key") != key]

        done_keys: set[str] = valid_done
        total_input_token = 0
        total_output_token = 0

        # MLflow 실행 시작
        if not dry_run:
            self.mlflow_logger.start_run(
                experiment_name=EXPERIMENT_NAME,
                run_name=f"{self.ticker_code}_{start}_{end}",
                tags={"ticker": self.ticker_code},
            )

        try:
            # 국면 순회
            for i, reg in enumerate(regimes, 1):
                regime_key = f"{reg['start'].strftime('%Y-%m-%d')}_{reg['end'].strftime('%Y-%m-%d')}"
                start_str = reg["start"].strftime("%Y-%m-%d")
                end_str = reg["end"].strftime("%Y-%m-%d")
                cum_ret = self._cum_return(returns, reg["dates"])
                vol_trend = self._vol_trend(volume, reg["dates"])
                dir_str = DIR_STR.get(reg["direction"], reg["direction"])

                news_articles = self._fetch_regime_news(
                    reg["start"], reg["end"], NEWS_PRE, NEWS_POST
                )

                logger.info(
                    f"[{i:>2}/{len(regimes)}] {start_str}~{end_str} ({reg['days']:>2}일) "
                    f"{dir_str} {cum_ret:+.1%}  거래량:{vol_trend}  뉴스 {len(news_articles)}건"
                )

                if dry_run:
                    continue

                if regime_key in done_keys:
                    logger.info(f"   → 이미 완료, 스킵")
                    continue

                news_context = self._build_news_context(news_articles)

                regime_info = {
                    "regime_key": regime_key,
                    "start_str": start_str,
                    "end_str": end_str,
                    "days": reg["days"],
                    "direction": reg["direction"],
                    "cum_ret": cum_ret,
                    "vol_trend": vol_trend,
                    "dir_str": dir_str,
                }

                try:
                    answer, input_token, output_token = self._analyze_regime_with_llm(
                        regime_info, news_context, endpoint=endpoint
                    )
                except Exception as e:
                    logger.warning(f"   분석 실패: {e}")
                    continue

                missing = REQUIRED_KEYS - answer.keys()
                if missing:
                    logger.warning(f"   필수 키 누락 {missing} — 건너뜀")
                    continue

                total_input_token += input_token
                total_output_token += output_token
                logger.info(
                    f"   토큰 input_token={input_token}  output_token={output_token}  "
                    f"(누계 input_token={total_input_token} output_token={total_output_token})"
                )

                results.append(
                    {
                        "regime_id": i,
                        "regime_key": regime_key,
                        "ticker": self.ticker_name,
                        "ticker_code": self.ticker_code,
                        "start": start_str,
                        "end": end_str,
                        "days": reg["days"],
                        "direction": reg["direction"],
                        "cum_return": round(cum_ret, 6),
                        "vol_trend": vol_trend,
                        "news_count": len(news_articles),
                        "input_token": input_token,
                        "output_token": output_token,
                        "llm_analysis": answer,
                    }
                )
                done_keys.add(regime_key)

                self.save_results(results)
                time.sleep(sleep_sec)

            logger.info(
                f"✅ 완료: {len(results)}건 분석  "
                f"토큰 합계 input_token={total_input_token:,}  output_token={total_output_token:,}  → {self.output_path}"
            )

            if not dry_run:
                self.mlflow_logger.log_metrics(
                    {
                        "total_regimes": len(results),
                        "total_input_token": total_input_token,
                        "total_output_token": total_output_token,
                    }
                )
                self.mlflow_logger.end_run(status="FINISHED")

        except Exception as e:
            logger.error(f"❌ 실행 중 오류: {e}")
            if not dry_run:
                self.mlflow_logger.end_run(status="FAILED")
            raise


def main():
    parser = argparse.ArgumentParser(description="가격 국면별 뉴스 LLM 분석")
    parser.add_argument(
        "--ticker",
        required=True,
        choices=list(TICKER_MAP),
        help="종목 코드 (예: 005930)",
    )
    parser.add_argument(
        "--endpoint",
        choices=["mid_performance_llm", "low_performance_llm"],
        default="mid_performance_llm",
        help="LLM endpoint",
    )
    parser.add_argument(
        "--prompt-key",
        default=DEFAULT_PROMPT_KEY,
        help=f"MLflow Prompt Registry 키 (기본값: {DEFAULT_PROMPT_KEY})",
    )
    parser.add_argument("--start", default=START_DATE)
    parser.add_argument("--end", default=END_DATE)
    parser.add_argument("--dry-run", action="store_true", help="dry-run 모드")
    parser.add_argument(
        "--rerun-ids",
        nargs="+",
        type=int,
        default=[],
        metavar="ID",
        help="강제 재처리할 regime_id",
    )
    args = parser.parse_args()

    name, sector = TICKER_MAP[args.ticker]
    pipeline = RegimeNewsSummary(
        ticker_code=args.ticker,
        ticker_name=name,
        sector=sector,
        prompt_key=args.prompt_key,
    )
    pipeline.run(
        start=args.start,
        end=args.end,
        endpoint=args.endpoint,
        dry_run=args.dry_run,
        rerun_ids=set(args.rerun_ids),
    )


if __name__ == "__main__":
    main()

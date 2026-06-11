"""
통합 뉴스 요약 파이프라인

샘플링 → 로드 → LLM 요약 → S3 저장 (MLflow trace)

사용법:
  python script/news_summary_pipeline.py \\
    --endpoint mid_performance_llm \\
    --tickers 005930 000660 \\
    --sample-size 10
"""

import argparse
import json
import logging
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import mlflow
from tenacity import retry, stop_after_attempt, wait_exponential

from src.data.s3_news_loader import S3NewsDataLoader
from src.llm_utils.gateway_client import GatewayClient
from src.llm_utils.mlflow_logger import MLflowLogger
from src.llm_utils.prompt_registry import PromptRegistry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

PREPROCESSED_PREFIX = "preprocessed"
SUMMARIZED_PREFIX = "summarized"
EXPERIMENT_NAME = "news_summary_service"


class NewsSummaryPipeline:
    """통합 뉴스 요약 파이프라인"""

    def __init__(
        self,
        bucket: str = "fisa-news-archive",
        region: str = "ap-northeast-2",
        endpoint_name: str = "mid_performance_llm",
        max_tokens: int = 350,
        prompt_key: str = "news_summarization",
    ):
        """
        초기화

        Args:
            bucket: S3 버킷
            region: AWS 리전
            endpoint_name: LLM endpoint 이름 (필수)
            max_tokens: 최대 토큰 수
            prompt_key: MLflow Prompt Registry의 프롬프트 키
        """
        self.bucket = bucket
        self.region = region
        self.endpoint_name = endpoint_name
        self.max_tokens = max_tokens
        self.prompt_key = prompt_key

        self.news_loader = S3NewsDataLoader(
            bucket=bucket,
            region=region,
            prefix=PREPROCESSED_PREFIX
        )
        self.mlflow_logger = MLflowLogger()
        self.gateway_client = GatewayClient(endpoint_name=endpoint_name)
        self.prompt_registry = PromptRegistry()

    def get_available_dates(self, ticker: str) -> list[str]:
        """티커별 사용 가능한 모든 날짜 조회"""
        try:
            import boto3
            s3_client = boto3.client("s3", region_name=self.region)
            dates = set()
            paginator = s3_client.get_paginator("list_objects_v2")

            pages = paginator.paginate(
                Bucket=self.bucket,
                Prefix=f"{PREPROCESSED_PREFIX}/{ticker}/",
                Delimiter="/"
            )

            for page in pages:
                if "CommonPrefixes" not in page:
                    continue

                for prefix_info in page["CommonPrefixes"]:
                    year_prefix = prefix_info["Prefix"]
                    year = year_prefix.rstrip("/").split("/")[-1]

                    month_pages = paginator.paginate(
                        Bucket=self.bucket,
                        Prefix=year_prefix,
                        Delimiter="/"
                    )

                    for month_page in month_pages:
                        if "CommonPrefixes" not in month_page:
                            continue

                        for month_prefix_info in month_page["CommonPrefixes"]:
                            month_prefix = month_prefix_info["Prefix"]
                            month = month_prefix.rstrip("/").split("/")[-1]

                            file_pages = paginator.paginate(
                                Bucket=self.bucket,
                                Prefix=month_prefix
                            )

                            for file_page in file_pages:
                                if "Contents" not in file_page:
                                    continue

                                for obj in file_page["Contents"]:
                                    key = obj["Key"]
                                    filename = key.split("/")[-1]
                                    if filename.endswith(".json"):
                                        date_str = filename[:-5]
                                        try:
                                            from datetime import datetime as dt
                                            dt.strptime(date_str, "%Y-%m-%d")
                                            dates.add(date_str)
                                        except ValueError:
                                            pass

            return sorted(list(dates))

        except Exception as e:
            logger.error(f"❌ 날짜 조회 실패 ({ticker}): {str(e)}")
            return []

    def sample_dates(self, ticker: str, sample_size: int = 10) -> list[str]:
        """티커별로 날짜 샘플링"""
        available_dates = self.get_available_dates(ticker)

        if len(available_dates) == 0:
            logger.warning(f"⚠️ {ticker}: 사용 가능한 날짜 없음")
            return []

        actual_sample_size = min(sample_size, len(available_dates))
        sampled = random.sample(available_dates, actual_sample_size)

        logger.info(
            f"✓ {ticker}: {len(available_dates)}개 중 {actual_sample_size}개 샘플링"
        )
        return sorted(sampled)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    def summarize_news(self, title: str, fulltext: str) -> str:
        """LLM으로 뉴스 요약"""
        prompt = self.prompt_registry.format_prompt(
            self.prompt_key,
            title=title,
            fulltext=fulltext
        )

        with mlflow.start_span(
            name="llm_summary",
            attributes={
                "endpoint": self.endpoint_name,
                "prompt_key": self.prompt_key,
            }
        ):
            summary = self.gateway_client.invoke(
                prompt=prompt,
                max_tokens=self.max_tokens
            )
            return summary.strip()

    def process_ticker(
        self,
        ticker: str,
        sampled_dates: list[str]
    ) -> dict[str, Any]:
        """티커별로 요약 생성"""
        try:
            logger.info(f"📋 {ticker} 요약 처리 시작 ({len(sampled_dates)}개 날짜)")

            summary_results = {}
            processed_count = 0
            error_count = 0

            for date_str in sampled_dates:
                try:
                    # 해당 날짜의 뉴스 로드
                    news_list = self.news_loader.load_news(
                        ticker=ticker,
                        start_date=date_str,
                        end_date=date_str
                    )

                    if not news_list:
                        continue

                    date_summaries = {}

                    for news in news_list:
                        try:
                            news_id = news.get("id") or str(hash(str(news)))
                            title = news.get("title", "")
                            fulltext = news.get("fulltext", "")

                            if not title or not fulltext:
                                continue

                            # LLM으로 요약
                            summary = self.summarize_news(title, fulltext)
                            date_summaries[news_id] = summary

                            processed_count += 1

                            if processed_count % 5 == 0:
                                logger.info(f"  ✓ {processed_count}개 뉴스 처리")

                        except Exception as e:
                            error_count += 1
                            logger.warning(f"  ⚠️ 뉴스 요약 실패: {str(e)}")
                            continue

                    if date_summaries:
                        summary_results[date_str] = date_summaries

                except Exception as e:
                    error_count += 1
                    logger.warning(f"  ⚠️ {date_str} 처리 실패: {str(e)}")

            logger.info(
                f"✓ {ticker} 요약 완료: {processed_count}개 성공, {error_count}개 실패"
            )

            return summary_results

        except Exception as e:
            logger.error(f"❌ {ticker} 처리 실패: {str(e)}")
            raise

    def save_summaries_to_s3(
        self,
        ticker: str,
        summary_results: dict[str, Any]
    ) -> bool:
        """요약 결과를 S3에 저장"""
        try:
            import boto3
            s3_client = boto3.client("s3", region_name=self.region)

            for date_str, date_summaries in summary_results.items():
                parts = date_str.split("-")
                year, month = parts[0], parts[1]
                s3_key = f"{SUMMARIZED_PREFIX}/{ticker}/{year}/{month}/{date_str}.json"

                content = json.dumps(date_summaries, ensure_ascii=False, indent=2)
                s3_client.put_object(
                    Bucket=self.bucket,
                    Key=s3_key,
                    Body=content.encode("utf-8"),
                    ContentType="application/json"
                )

            logger.info(
                f"✓ S3 저장 완료: {ticker} ({len(summary_results)}개 날짜)"
            )
            return True

        except Exception as e:
            logger.error(f"❌ S3 저장 실패 ({ticker}): {str(e)}")
            return False

    def run(
        self,
        tickers: list[str],
        sample_size: int = 10
    ) -> None:
        """통합 파이프라인 실행"""
        try:
            # MLflow run 시작
            run_id = self.mlflow_logger.start_run(
                experiment_name=EXPERIMENT_NAME,
                run_name=f"news_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                tags={
                    "pipeline": "integrated",
                    "endpoint": self.endpoint_name,
                    "sample_size": str(sample_size),
                }
            )

            try:
                logger.info(f"🔄 {len(tickers)}개 티커 처리 시작")

                # 파라미터 로깅
                self.mlflow_logger.log_params({
                    "tickers": ",".join(tickers),
                    "sample_size": str(sample_size),
                    "endpoint_name": self.endpoint_name,
                    "prompt_key": self.prompt_key,
                    "max_tokens": str(self.max_tokens),
                })

                ticker_metrics = {}

                # 각 티커 처리
                for idx, ticker in enumerate(tickers, 1):
                    logger.info(f"\n[{idx}/{len(tickers)}] 📝 {ticker} 처리")

                    # 1. 샘플링
                    sampled_dates = self.sample_dates(ticker, sample_size)
                    if not sampled_dates:
                        logger.warning(f"⚠️ {ticker}: 샘플링 실패")
                        continue

                    # 2. 요약 생성
                    summary_results = self.process_ticker(ticker, sampled_dates)
                    if not summary_results:
                        logger.warning(f"⚠️ {ticker}: 요약 결과 없음")
                        continue

                    # 3. S3 저장
                    self.save_summaries_to_s3(ticker, summary_results)

                    # 4. 메트릭 기록
                    total_summaries = sum(len(v) for v in summary_results.values())
                    ticker_metrics[f"summaries_{ticker}"] = total_summaries
                    ticker_metrics[f"dates_{ticker}"] = len(summary_results)

                    logger.info(f"✓ {ticker} 완료: {total_summaries}개 요약")

                # 메트릭 로깅
                if ticker_metrics:
                    self.mlflow_logger.log_metrics(ticker_metrics)

                logger.info("\n✅ 모든 처리 완료")
                logger.info(f"\n📍 MLflow Web UI: http://52.78.237.104:5001")
                logger.info(f"   → Experiments → {EXPERIMENT_NAME}")

                self.mlflow_logger.end_run(status="FINISHED")

            except Exception as e:
                logger.error(f"❌ 처리 중 오류: {str(e)}")
                self.mlflow_logger.end_run(status="FAILED")
                raise

        except Exception as e:
            logger.error(f"❌ 파이프라인 실패: {str(e)}")
            raise


def main():
    """메인 함수 (argparse 포함)"""
    parser = argparse.ArgumentParser(
        description="통합 뉴스 요약 파이프라인"
    )

    # 필수 파라미터
    parser.add_argument(
        "--endpoint",
        type=str,
        required=True,
        help="LLM endpoint 이름 (필수: mid_performance_llm, 등)"
    )

    # 선택 파라미터
    parser.add_argument(
        "--tickers",
        type=str,
        nargs="+",
        default=None,
        help="처리할 티커 (기본값: 모든 티커)"
    )

    parser.add_argument(
        "--sample-size",
        type=int,
        default=10,
        help="각 티커별 샘플링 크기 (기본값: 10)"
    )

    parser.add_argument(
        "--prompt-key",
        type=str,
        default="news_summarization",
        help="프롬프트 키 (기본값: news_summarization)"
    )

    parser.add_argument(
        "--max-tokens",
        type=int,
        default=350,
        help="최대 토큰 수 (기본값: 350)"
    )

    args = parser.parse_args()

    # 파이프라인 실행
    pipeline = NewsSummaryPipeline(
        endpoint_name=args.endpoint,
        prompt_key=args.prompt_key,
        max_tokens=args.max_tokens,
    )

    # 티커 목록 확인
    if args.tickers is None:
        tickers = pipeline.news_loader.list_available_tickers()
    else:
        tickers = args.tickers

    logger.info(f"처리 대상 티커: {tickers}")
    logger.info(f"샘플 크기: {args.sample_size}")
    logger.info(f"Endpoint: {args.endpoint}")

    # 실행
    pipeline.run(tickers, args.sample_size)


if __name__ == "__main__":
    main()

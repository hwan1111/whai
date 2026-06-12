"""
통합 뉴스 요약 파이프라인

평가 모드:
  - 샘플링 → mid (reference) + low 요약 → 비교 평가 → MLflow evaluation 등록

프로덕션 모드:
  - 전체 데이터 → low 요약 → S3 저장

사용법:
  평가:
    python script/news_summary_pipeline.py \\
      --mode evaluation \\
      --tickers 005930 000660 \\
      --sample-size 10

  프로덕션:
    python script/news_summary_pipeline.py \\
      --mode production \\
      --tickers 005930 000660
"""

import argparse
import json
import logging
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import mlflow
from tenacity import retry, stop_after_attempt, wait_exponential

from src.data.s3_news_loader import S3NewsDataLoader
from src.llm_utils.gateway_client import GatewayClient
from src.llm_utils.mlflow_logger import MLflowLogger
from src.llm_utils.prompt_registry import PromptRegistry
from src.llm_utils.evaluation_engine import NewsEvaluator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

PREPROCESSED_PREFIX = "preprocessed"
REFERENCE_PREFIX = "reference"
SUMMARIZED_PREFIX = "summarized"
EXPERIMENT_NAME = "news_summary_service"


class NewsSummaryPipeline:
    """통합 뉴스 요약 파이프라인"""

    def __init__(
        self,
        bucket: str = "fisa-news-archive",
        region: str = "ap-northeast-2",
        max_tokens: int = 350,
        prompt_key: str = "news_summarization",
    ):
        """
        초기화

        Args:
            bucket: S3 버킷
            region: AWS 리전
            max_tokens: 최대 토큰 수
            prompt_key: MLflow Prompt Registry의 프롬프트 키
        """
        self.bucket = bucket
        self.region = region
        self.max_tokens = max_tokens
        self.prompt_key = prompt_key

        self.news_loader = S3NewsDataLoader(
            bucket=bucket,
            region=region,
            prefix=PREPROCESSED_PREFIX
        )
        self.mlflow_logger = MLflowLogger()
        self.prompt_registry = PromptRegistry()
        self.evaluator = NewsEvaluator(use_bert_score=True)

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
    def summarize_news(
        self,
        title: str,
        fulltext: str,
        endpoint: str = "mid_performance_llm"
    ) -> tuple[str, int, int]:
        """LLM으로 뉴스 요약"""
        try:
            article_content = f"제목: {title}\n\n내용: {fulltext}"

            with mlflow.start_span(name="llm_summary") as span:
                # span 내부에서 프롬프트 로드 → linked prompts 자동 연결
                prompt, prompt_uri = self.prompt_registry.format_prompt(
                    self.prompt_key,
                    article=article_content
                )

                span.set_inputs({
                    "article_title": title,
                    "article_content": fulltext[:1000],
                    "endpoint": endpoint,
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
                summary, input_token, output_token = gateway_client.call_with_usage(
                    text=prompt,
                    max_tokens=self.max_tokens,
                )

                span.set_outputs({
                    "summary": summary.strip(),
                    "input_token": input_token,
                    "output_token": output_token,
                })

                logger.info(
                    f"📥 LLM 응답 수신: {len(summary)}자 "
                    f"(input_token={input_token}, output_token={output_token})"
                )
                return summary.strip(), input_token, output_token
        except Exception as e:
            logger.error(f"❌ 요약 생성 실패: {str(e)}", exc_info=True)
            raise

    def process_ticker(
        self,
        ticker: str,
        sampled_dates: list[str],
        endpoint: str = "mid_performance_llm"
    ) -> dict[str, Any]:
        """티커별로 요약 생성"""
        try:
            logger.info(f"📋 {ticker} 요약 처리 시작 ({len(sampled_dates)}개 날짜, endpoint: {endpoint})")

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
                            summary, input_token, output_token = self.summarize_news(title, fulltext, endpoint=endpoint)
                            date_summaries[news_id] = {
                                "summary": summary,
                                "input_token": input_token,
                                "output_token": output_token,
                            }

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
        summary_results: dict[str, Any],
        prefix: str = SUMMARIZED_PREFIX
    ) -> bool:
        """요약 결과를 S3에 저장"""
        try:
            import boto3
            s3_client = boto3.client("s3", region_name=self.region)

            for date_str, date_summaries in summary_results.items():
                parts = date_str.split("-")
                year, month = parts[0], parts[1]
                s3_key = f"{prefix}/{ticker}/{year}/{month}/{date_str}.json"

                content = json.dumps(date_summaries, ensure_ascii=False, indent=2)
                s3_client.put_object(
                    Bucket=self.bucket,
                    Key=s3_key,
                    Body=content.encode("utf-8"),
                    ContentType="application/json"
                )

            logger.info(
                f"✓ S3 저장 완료: {prefix}/{ticker} ({len(summary_results)}개 날짜)"
            )
            return True

        except Exception as e:
            logger.error(f"❌ S3 저장 실패 ({ticker}): {str(e)}")
            return False

    def run_evaluation(
        self,
        tickers: list[str],
        sample_size: int = 10
    ) -> None:
        """평가 모드: mid vs low 비교 평가"""
        try:
            run_id = self.mlflow_logger.start_run(
                experiment_name=EXPERIMENT_NAME,
                run_name=f"evaluation_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                tags={
                    "mode": "evaluation",
                    "sample_size": str(sample_size),
                }
            )

            try:
                logger.info(f"🔄 평가 모드: {len(tickers)}개 티커 처리 시작")

                self.mlflow_logger.log_params({
                    "tickers": ",".join(tickers),
                    "sample_size": str(sample_size),
                    "prompt_key": self.prompt_key,
                    "max_tokens": str(self.max_tokens),
                    "mode": "evaluation",
                })

                evaluation_results = []
                ticker_metrics = {}

                for idx, ticker in enumerate(tickers, 1):
                    logger.info(f"\n[{idx}/{len(tickers)}] 📊 {ticker} 평가 시작")

                    # 1. 샘플링
                    sampled_dates = self.sample_dates(ticker, sample_size)
                    if not sampled_dates:
                        logger.warning(f"⚠️ {ticker}: 샘플링 실패")
                        continue

                    # 2. mid (reference) 요약
                    logger.info(f"  → mid_performance 요약 생성")
                    mid_summaries = self.process_ticker(ticker, sampled_dates, endpoint="mid_performance_llm")
                    if not mid_summaries:
                        logger.warning(f"⚠️ {ticker}: mid 요약 실패")
                        continue

                    # 3. low 요약
                    logger.info(f"  → low_performance 요약 생성")
                    low_summaries = self.process_ticker(ticker, sampled_dates, endpoint="low_performance_llm")
                    if not low_summaries:
                        logger.warning(f"⚠️ {ticker}: low 요약 실패")
                        continue

                    # 4. 평가용 데이터 준비
                    eval_summaries = []
                    for date_str in sampled_dates:
                        mid_date_summaries = mid_summaries.get(date_str, {})
                        low_date_summaries = low_summaries.get(date_str, {})

                        for news_id in mid_date_summaries:
                            if news_id not in low_date_summaries:
                                continue

                            # 뉴스 본문 로드 (선택사항)
                            news_list = self.news_loader.load_news(
                                ticker=ticker,
                                start_date=date_str,
                                end_date=date_str
                            )
                            article = ""
                            for news in news_list or []:
                                if news.get("id") == news_id:
                                    article = news.get("fulltext", "")
                                    break

                            mid_summary = mid_date_summaries[news_id]
                            low_summary = low_date_summaries[news_id]

                            # summary 필드 추출 (dict 또는 str)
                            ref_text = mid_summary["summary"] if isinstance(mid_summary, dict) else mid_summary
                            gen_text = low_summary["summary"] if isinstance(low_summary, dict) else low_summary

                            eval_summaries.append({
                                "id": f"{ticker}_{date_str}_{news_id}",
                                "article": article,
                                "reference_summary": ref_text,
                                "generated_summary": gen_text,
                            })

                    # 5. 평가 실행
                    if eval_summaries:
                        logger.info(f"  → {len(eval_summaries)}개 요약 평가 중")
                        with mlflow.start_run(nested=True, run_name=f"eval_{ticker}"):
                            results = self.evaluator.evaluate_batch(
                                eval_summaries,
                                log_to_mlflow=True,
                                run_name=f"eval_{ticker}"
                            )
                            evaluation_results.extend(results)

                            # 평가 결과 요약
                            eval_summary = self.evaluator.get_evaluation_summary(results)
                            mlflow.log_params({"ticker": ticker})
                            for key, value in eval_summary.items():
                                if isinstance(value, (int, float)):
                                    mlflow.log_metric(f"{ticker}_{key}", value)

                        logger.info(f"✓ {ticker} 평가 완료: {len(results)}개 항목")

                        # mlflow.genai.evaluate()로 quality 모니터링
                        try:
                            from mlflow.genai.scorers import RelevanceToQuery, Safety

                            genai_eval_data = [
                                {
                                    "inputs": {
                                        "article_title": s["id"],
                                        "article_content": s.get("article", ""),
                                    },
                                    "outputs": s["generated_summary"],
                                    "expectations": {
                                        "expected_response": s["reference_summary"],
                                    },
                                }
                                for s in eval_summaries
                            ]

                            with mlflow.start_run(nested=True, run_name=f"genai_eval_{ticker}"):
                                mlflow.genai.evaluate(
                                    data=genai_eval_data,
                                    scorers=[RelevanceToQuery(), Safety()],
                                )
                            logger.info(f"✓ {ticker} genai quality 평가 완료")
                        except Exception as e:
                            logger.warning(f"⚠️ genai.evaluate 실패 (선택적): {str(e)}")

                    # 6. S3에 저장
                    logger.info(f"  → S3 저장 중")
                    self.save_summaries_to_s3(ticker, mid_summaries, prefix=REFERENCE_PREFIX)
                    self.save_summaries_to_s3(ticker, low_summaries, prefix=SUMMARIZED_PREFIX)
                    logger.info(f"✓ {ticker} 저장 완료")

                logger.info("\n✅ 평가 완료")
                logger.info(f"📍 MLflow Web UI: http://52.78.237.104:5001")
                logger.info(f"   → Experiments → {EXPERIMENT_NAME}")

                self.mlflow_logger.end_run(status="FINISHED")

            except Exception as e:
                logger.error(f"❌ 평가 중 오류: {str(e)}")
                self.mlflow_logger.end_run(status="FAILED")
                raise

        except Exception as e:
            logger.error(f"❌ 평가 파이프라인 실패: {str(e)}")
            raise

    def run_production(
        self,
        tickers: list[str]
    ) -> None:
        """프로덕션 모드: low로 전체 데이터 요약 후 S3 저장"""
        try:
            run_id = self.mlflow_logger.start_run(
                experiment_name=EXPERIMENT_NAME,
                run_name=f"production_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                tags={
                    "mode": "production",
                }
            )

            try:
                logger.info(f"🔄 프로덕션 모드: {len(tickers)}개 티커 처리 시작")

                self.mlflow_logger.log_params({
                    "tickers": ",".join(tickers),
                    "prompt_key": self.prompt_key,
                    "max_tokens": str(self.max_tokens),
                    "mode": "production",
                    "endpoint": "low_performance_llm",
                })

                ticker_metrics = {}

                for idx, ticker in enumerate(tickers, 1):
                    logger.info(f"\n[{idx}/{len(tickers)}] 📝 {ticker} 처리")

                    # 모든 날짜 가져오기
                    available_dates = self.get_available_dates(ticker)
                    if not available_dates:
                        logger.warning(f"⚠️ {ticker}: 사용 가능한 날짜 없음")
                        continue

                    logger.info(f"  → {len(available_dates)}개 날짜 처리")

                    # low_performance로 전체 요약
                    summary_results = self.process_ticker(
                        ticker,
                        available_dates,
                        endpoint="low_performance_llm"
                    )
                    if not summary_results:
                        logger.warning(f"⚠️ {ticker}: 요약 결과 없음")
                        continue

                    # S3 저장 (summary 버킷)
                    self.save_summaries_to_s3(ticker, summary_results)

                    # 메트릭 기록
                    total_summaries = sum(len(v) for v in summary_results.values())
                    ticker_metrics[f"summaries_{ticker}"] = total_summaries
                    ticker_metrics[f"dates_{ticker}"] = len(summary_results)

                    logger.info(f"✓ {ticker} 완료: {total_summaries}개 요약 저장")

                if ticker_metrics:
                    self.mlflow_logger.log_metrics(ticker_metrics)

                logger.info("\n✅ 모든 처리 완료")
                logger.info(f"📍 MLflow Web UI: http://52.78.237.104:5001")
                logger.info(f"   → Experiments → {EXPERIMENT_NAME}")

                self.mlflow_logger.end_run(status="FINISHED")

            except Exception as e:
                logger.error(f"❌ 처리 중 오류: {str(e)}")
                self.mlflow_logger.end_run(status="FAILED")
                raise

        except Exception as e:
            logger.error(f"❌ 프로덕션 파이프라인 실패: {str(e)}")
            raise


def main():
    """메인 함수 (argparse 포함)"""
    parser = argparse.ArgumentParser(
        description="뉴스 요약 파이프라인 (평가 / 프로덕션)"
    )

    # 필수 파라미터
    parser.add_argument(
        "--mode",
        type=str,
        choices=["evaluation", "production"],
        required=True,
        help="실행 모드 (평가 또는 프로덕션)"
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
        help="평가 모드에서 샘플링 크기 (기본값: 10)"
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

    # 파이프라인 초기화
    pipeline = NewsSummaryPipeline(
        prompt_key=args.prompt_key,
        max_tokens=args.max_tokens,
    )

    # 티커 목록 확인
    if args.tickers is None:
        tickers = pipeline.news_loader.list_available_tickers()
    else:
        tickers = args.tickers

    logger.info(f"모드: {args.mode}")
    logger.info(f"처리 대상 티커: {tickers}")
    if args.mode == "evaluation":
        logger.info(f"샘플 크기: {args.sample_size}")

    # 모드에 따라 실행
    if args.mode == "evaluation":
        pipeline.run_evaluation(tickers, args.sample_size)
    else:  # production
        pipeline.run_production(tickers)


if __name__ == "__main__":
    main()

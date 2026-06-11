"""
MLflow를 사용하여 뉴스 요약 생성 및 추적

- MLflow 실험 생성 및 run 시작
- reference에서 뉴스 로드
- LLM endpoint를 통해 뉴스 요약 생성
- 요약 결과를 summarized 폴더에 저장
- MLflow에 trace 기록
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import mlflow
from tenacity import retry, stop_after_attempt, wait_exponential

from src.data.s3_news_loader import S3NewsDataLoader
from src.llm_utils.gateway_client import GatewayClient
from src.llm_utils.mlflow_logger import MLflowLogger
from src.llm_utils.prompt_registry import PromptRegistry, log_prompt_metrics

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

REFERENCE_PREFIX = "reference"
SUMMARIZED_PREFIX = "summarized"
ENDPOINT_NAME = "mid_performance_llm"
EXPERIMENT_NAME = "news_summary_service"


class NewsLLMSummarizer:
    """뉴스 LLM 요약 클래스"""

    def __init__(
        self,
        bucket: str = "fisa-news-archive",
        region: str = "ap-northeast-2",
        endpoint_name: str = ENDPOINT_NAME,
        max_tokens: int = 200,
        prompt_key: str = "news_summarization",
    ):
        """
        초기화

        Args:
            bucket: S3 버킷
            region: AWS 리전
            endpoint_name: MLflow endpoint 이름
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
            prefix=REFERENCE_PREFIX
        )
        self.mlflow_logger = MLflowLogger()
        self.gateway_client = GatewayClient(endpoint_name=endpoint_name)
        self.prompt_registry = PromptRegistry()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    def summarize_news(self, title: str, fulltext: str) -> str:
        """
        뉴스 요약 생성 (MLflow Prompt Registry 사용)

        Args:
            title: 뉴스 제목
            fulltext: 뉴스 본문

        Returns:
            요약 텍스트
        """
        try:
            # Prompt Registry에서 템플릿 로드 및 포맷팅
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
                    "model": "news_summarization"
                }
            ):
                summary = self.gateway_client.invoke(
                    prompt=prompt,
                    max_tokens=self.max_tokens
                )
                return summary.strip()

        except Exception as e:
            logger.error(f"❌ 요약 생성 실패: {str(e)}")
            raise

    def process_ticker(
        self,
        ticker: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        티커별로 모든 reference 뉴스 요약

        Args:
            ticker: 종목코드
            start_date: 시작 날짜 (선택)
            end_date: 종료 날짜 (선택)

        Returns:
            {date: {news_id: summary}} 형태의 요약 결과
        """
        try:
            # 날짜 범위 설정 (기본: 전체 범위)
            if not start_date:
                start_date = "2000-01-01"
            if not end_date:
                end_date = datetime.now().strftime("%Y-%m-%d")

            logger.info(
                f"📋 {ticker} 요약 처리 시작 ({start_date} ~ {end_date})"
            )

            # reference에서 레퍼런스 데이터 로드
            reference_summaries = self.news_loader.load_references(
                ticker=ticker,
                start_date=start_date,
                end_date=end_date,
                reference_prefix=REFERENCE_PREFIX
            )

            if not reference_summaries:
                logger.warning(f"⚠️ {ticker}: 레퍼런스 데이터 없음")
                return {}

            # 요약 결과 저장소
            summary_results = {}
            processed_count = 0
            error_count = 0

            # 각 날짜별로 처리
            for reference_key, reference_summary in reference_summaries.items():
                date_str = reference_key

                try:
                    # reference 데이터에서 뉴스 정보 추출
                    if isinstance(reference_summary, dict) and "news" in reference_summary:
                        news_list = reference_summary["news"]
                    elif isinstance(reference_summary, str):
                        # 이미 요약된 형태
                        news_list = [{"id": reference_key, "summary": reference_summary}]
                    else:
                        news_list = []

                    date_summaries = {}

                    for news in news_list:
                        try:
                            # 뉴스 ID 생성
                            news_id = news.get("id") or news.get("article_id") or str(hash(str(news)))

                            # 이미 요약된 데이터는 스킵
                            if "summary" in news and not ("title" in news and "fulltext" in news):
                                date_summaries[news_id] = news.get("summary")
                                continue

                            # 제목과 본문 추출
                            title = news.get("title", "")
                            fulltext = news.get("fulltext", "")

                            if not title or not fulltext:
                                logger.debug(f"  ⚠️ {news_id}: 제목 또는 본문 없음, 스킵")
                                continue

                            # LLM으로 요약 생성
                            summary = self.summarize_news(title, fulltext)
                            date_summaries[news_id] = summary

                            processed_count += 1

                            if processed_count % 5 == 0:
                                logger.info(f"  ✓ {processed_count}개 뉴스 처리 완료")

                        except Exception as e:
                            error_count += 1
                            logger.warning(f"  ⚠️ 뉴스 요약 실패 ({news_id}): {str(e)}")
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
        """
        요약 결과를 S3 summarized 폴더에 저장

        Args:
            ticker: 종목코드
            summary_results: 요약 결과

        Returns:
            성공 여부
        """
        try:
            import boto3

            s3_client = boto3.client("s3", region_name=self.region)

            # 날짜별로 파일 저장
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

                logger.debug(f"  ✓ {s3_key} 저장")

            logger.info(
                f"✓ S3 summarized에 {ticker} 저장 완료 "
                f"({len(summary_results)}개 날짜 파일)"
            )
            return True

        except Exception as e:
            logger.error(f"❌ S3 저장 실패 ({ticker}): {str(e)}")
            return False

    def save_summaries_to_local(
        self,
        ticker: str,
        summary_results: dict[str, Any],
        output_dir: str = "summaries"
    ) -> str:
        """
        요약 결과를 로컬에 저장

        Args:
            ticker: 종목코드
            summary_results: 요약 결과
            output_dir: 출력 디렉토리

        Returns:
            저장된 파일 경로
        """
        try:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)

            file_path = output_path / f"{ticker}_summaries.json"

            content = json.dumps(summary_results, ensure_ascii=False, indent=2)
            file_path.write_text(content, encoding="utf-8")

            logger.info(f"✓ 로컬 요약 저장: {file_path}")
            return str(file_path)

        except Exception as e:
            logger.error(f"❌ 로컬 저장 실패 ({ticker}): {str(e)}")
            raise

    def run_summarization(
        self,
        tickers: list[str] | None = None,
        use_registered_dataset: bool = True
    ) -> None:
        """
        MLflow run으로 요약 프로세스 실행

        Args:
            tickers: 티커 목록 (None이면 S3에서 자동 조회)
            use_registered_dataset: 등록된 evaluation dataset 사용 여부
        """
        try:
            import mlflow

            # MLflow run 시작
            run_id = self.mlflow_logger.start_run(
                experiment_name=EXPERIMENT_NAME,
                run_name=f"news_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                tags={
                    "endpoint": self.endpoint_name,
                    "max_tokens": str(self.max_tokens),
                    "date": datetime.now().isoformat(),
                    "uses_registered_dataset": str(use_registered_dataset)
                }
            )

            try:
                # 티커 목록 조회
                if tickers is None:
                    tickers = self.news_loader.list_available_tickers()

                if not tickers:
                    logger.warning("⚠️ 처리할 티커가 없습니다")
                    self.mlflow_logger.end_run(status="FAILED")
                    return

                logger.info(f"🔄 {len(tickers)}개 티커의 요약 생성 시작")

                summary_dir = Path("summaries")
                summary_dir.mkdir(parents=True, exist_ok=True)

                # MLflow Web UI의 프롬프트 로드 시도
                prompt_source = self.prompt_registry.get_prompt_source(self.prompt_key)
                logger.info(f"📝 프롬프트 출처: {prompt_source}")

                # MLflow 파라미터 로깅
                prompt_description = self.prompt_registry.get_prompt_description(self.prompt_key)
                self.mlflow_logger.log_params({
                    "tickers": ",".join(tickers),
                    "endpoint_name": self.endpoint_name,
                    "max_tokens": self.max_tokens,
                    "reference_prefix": REFERENCE_PREFIX,
                    "summary_prefix": SUMMARIZED_PREFIX,
                    "use_registered_dataset": str(use_registered_dataset),
                    "prompt_key": self.prompt_key,
                    "prompt_description": prompt_description,
                    "prompt_source": prompt_source,
                })

                # 각 티커별로 요약 처리
                for idx, ticker in enumerate(tickers, 1):
                    logger.info(f"\n[{idx}/{len(tickers)}] 📝 {ticker} 처리 중...")

                    try:
                        # 등록된 evaluation dataset 로드 (선택사항)
                        if use_registered_dataset:
                            try:
                                dataset = mlflow.data.load_dataset(
                                    name=f"news_reference_{ticker}",
                                    namespace=EXPERIMENT_NAME
                                )
                                mlflow.log_input(dataset, context=f"reference/{ticker}")
                                logger.info(
                                    f"✓ 등록된 evaluation dataset 로드: "
                                    f"news_reference_{ticker}"
                                )
                            except Exception as e:
                                logger.warning(
                                    f"⚠️ evaluation dataset 로드 실패 ({ticker}), "
                                    f"S3 직접 접근으로 진행: {str(e)}"
                                )

                        # 요약 생성
                        summary_results = self.process_ticker(ticker)

                        if not summary_results:
                            logger.warning(f"⚠️ {ticker}: 요약 결과 없음, 스킵")
                            continue

                        # 로컬 저장
                        local_path = self.save_summaries_to_local(ticker, summary_results)

                        # S3 저장
                        self.save_summaries_to_s3(ticker, summary_results)

                        # 메트릭 로깅
                        total_summaries = sum(len(v) for v in summary_results.values())
                        self.mlflow_logger.log_metrics(
                            {
                                f"summaries_{ticker}": total_summaries,
                                f"dates_{ticker}": len(summary_results)
                            }
                        )

                        logger.info(f"✓ {ticker} 요약 완료: {total_summaries}개 요약, {len(summary_results)}개 날짜")

                    except Exception as e:
                        logger.error(f"❌ {ticker} 처리 중 오류: {str(e)}")
                        continue

                logger.info("\n✅ 모든 요약 생성 완료")
                logger.info(f"\n📍 MLflow Web UI에서 확인:")
                logger.info(f"   http://52.78.237.104:5001")
                logger.info(f"   → Experiments → {EXPERIMENT_NAME} → 해당 Run")
                logger.info(f"   → Input 탭에서 등록된 evaluation datasets 확인")

                self.mlflow_logger.end_run(status="FINISHED")

            except Exception as e:
                logger.error(f"❌ 요약 프로세스 중 오류: {str(e)}")
                self.mlflow_logger.end_run(status="FAILED")
                raise

        except Exception as e:
            logger.error(f"❌ MLflow run 실패: {str(e)}")
            raise


def main():
    """메인 함수"""
    # 사용할 프롬프트 선택: "news_summarization" 또는 "news_summarization_detailed"
    summarizer = NewsLLMSummarizer(prompt_key="news_summarization")
    summarizer.run_summarization()


if __name__ == "__main__":
    main()

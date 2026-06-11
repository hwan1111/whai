"""
각 티커별로 뉴스 레퍼런스 생성 및 MLflow evaluation dataset 등록

- S3의 preprocessed 폴더에서 각 티커별 사용 가능한 날짜 조회
- 각 티커마다 10개 날짜를 임의로 샘플링
- 샘플링된 날짜의 뉴스를 로드하여 reference 폴더에 저장
- MLflow evaluation dataset으로 등록
"""

import json
import logging
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError

from src.data.s3_news_loader import S3NewsDataLoader
from src.llm_utils.mlflow_logger import MLflowLogger

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

REFERENCE_PREFIX = "reference"
PREPROCESSED_PREFIX = "preprocessed"
SAMPLE_SIZE = 10


class NewsReferenceGenerator:
    """뉴스 레퍼런스 생성 클래스"""

    def __init__(
        self,
        bucket: str = "fisa-news-archive",
        region: str = "ap-northeast-2",
    ):
        """
        초기화

        Args:
            bucket: S3 버킷 이름
            region: AWS 리전
        """
        self.bucket = bucket
        self.region = region
        self.s3_client = boto3.client("s3", region_name=region)
        self.news_loader = S3NewsDataLoader(
            bucket=bucket,
            region=region,
            prefix=PREPROCESSED_PREFIX
        )
        self.mlflow_logger = MLflowLogger()

    def get_available_dates(self, ticker: str) -> list[str]:
        """
        S3에서 티커별 사용 가능한 모든 날짜 조회

        Args:
            ticker: 종목코드

        Returns:
            YYYY-MM-DD 형식의 날짜 리스트 (오름차순)
        """
        try:
            dates = set()
            paginator = self.s3_client.get_paginator("list_objects_v2")

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

                    # 월 디렉토리 조회
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

                            # 실제 파일 조회
                            file_pages = paginator.paginate(
                                Bucket=self.bucket,
                                Prefix=month_prefix
                            )

                            for file_page in file_pages:
                                if "Contents" not in file_page:
                                    continue

                                for obj in file_page["Contents"]:
                                    key = obj["Key"]
                                    # 날짜 추출: preprocessed/005930/2020/05/2020-05-01.json
                                    filename = key.split("/")[-1]
                                    if filename.endswith(".json"):
                                        date_str = filename[:-5]  # .json 제거
                                        try:
                                            datetime.strptime(date_str, "%Y-%m-%d")
                                            dates.add(date_str)
                                        except ValueError:
                                            pass

            return sorted(list(dates))

        except Exception as e:
            logger.error(f"❌ 날짜 조회 실패 ({ticker}): {str(e)}")
            return []

    def sample_dates(self, ticker: str, sample_size: int = SAMPLE_SIZE) -> list[str]:
        """
        티커별로 임의로 날짜 샘플링

        Args:
            ticker: 종목코드
            sample_size: 샘플 크기

        Returns:
            샘플링된 날짜 리스트
        """
        available_dates = self.get_available_dates(ticker)

        if len(available_dates) == 0:
            logger.warning(f"⚠️ {ticker}: 사용 가능한 날짜 없음")
            return []

        sample_size = min(sample_size, len(available_dates))
        sampled = random.sample(available_dates, sample_size)

        logger.info(
            f"✓ {ticker}: {len(available_dates)}개 중 {sample_size}개 샘플링 "
            f"(범위: {min(sampled)} ~ {max(sampled)})"
        )
        return sorted(sampled)

    def generate_reference(self, ticker: str) -> dict[str, Any]:
        """
        티커별 레퍼런스 생성

        Args:
            ticker: 종목코드

        Returns:
            {date: news_list} 형태의 레퍼런스 데이터
        """
        sampled_dates = self.sample_dates(ticker)

        reference_data = {}

        for date_str in sampled_dates:
            try:
                # preprocessed에서 해당 날짜 뉴스 로드
                news_list = self.news_loader.load_news(
                    ticker=ticker,
                    start_date=date_str,
                    end_date=date_str
                )

                if news_list:
                    reference_data[date_str] = {
                        "count": len(news_list),
                        "news": news_list
                    }
                    logger.debug(f"  ✓ {date_str}: {len(news_list)}개 뉴스 로드")

            except Exception as e:
                logger.warning(f"  ⚠️ {date_str}: 로드 실패 - {str(e)}")

        logger.info(
            f"✓ {ticker} 레퍼런스 생성 완료: {len(reference_data)}개 날짜, "
            f"총 {sum(v['count'] for v in reference_data.values())}개 뉴스"
        )

        return reference_data

    def save_reference_to_s3(
        self,
        ticker: str,
        reference_data: dict[str, Any]
    ) -> bool:
        """
        레퍼런스 데이터를 S3 reference 폴더에 저장

        Args:
            ticker: 종목코드
            reference_data: 레퍼런스 데이터

        Returns:
            성공 여부
        """
        try:
            # 날짜별로 파일 생성
            for date_str, data in reference_data.items():
                parts = date_str.split("-")
                year, month = parts[0], parts[1]
                s3_key = f"{REFERENCE_PREFIX}/{ticker}/{year}/{month}/{date_str}.json"

                content = json.dumps(data, ensure_ascii=False, indent=2)
                self.s3_client.put_object(
                    Bucket=self.bucket,
                    Key=s3_key,
                    Body=content.encode("utf-8"),
                    ContentType="application/json"
                )

                logger.debug(f"  ✓ {s3_key} 저장")

            logger.info(
                f"✓ S3 reference에 {ticker} 저장 완료 "
                f"({len(reference_data)}개 날짜 파일)"
            )
            return True

        except Exception as e:
            logger.error(f"❌ S3 저장 실패 ({ticker}): {str(e)}")
            return False


    def register_evaluation_dataset(
        self,
        experiment_name: str = "news_summary_service",
        tickers: list[str] | None = None
    ) -> None:
        """
        MLflow evaluation dataset으로 레퍼런스 등록 (trace 포함)

        Args:
            experiment_name: MLflow 실험 이름
            tickers: 티커 목록 (None이면 S3에서 자동 조회)
        """
        try:
            import mlflow
            from datetime import datetime

            # MLflow 실험 설정
            self.mlflow_logger.set_experiment(experiment_name)

            # MLflow run 시작
            run_id = self.mlflow_logger.start_run(
                experiment_name=experiment_name,
                run_name=f"generate_reference_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                tags={
                    "stage": "reference_generation",
                    "sample_size": str(10)
                }
            )

            # 티커 목록 조회
            if tickers is None:
                tickers = self.news_loader.list_available_tickers()

            if not tickers:
                logger.warning("⚠️ 처리할 티커가 없습니다")
                return

            logger.info(f"🔄 {len(tickers)}개 티커의 레퍼런스 생성 및 등록 시작")

            # MLflow 파라미터 로깅
            self.mlflow_logger.log_params({
                "tickers": ",".join(tickers),
                "sample_size": str(10),
                "reference_prefix": REFERENCE_PREFIX
            })

            # 각 티커별로 레퍼런스 생성 및 저장
            ticker_metrics = {}
            for ticker in tickers:
                logger.info(f"\n📝 {ticker} 처리 중...")

                # 레퍼런스 생성
                reference_data = self.generate_reference(ticker)

                if not reference_data:
                    logger.warning(f"⚠️ {ticker}: 레퍼런스 데이터 없음, 스킵")
                    continue

                # S3에만 저장 (로컬 저장 없음)
                self.save_reference_to_s3(ticker, reference_data)

                # MLflow Dataset Registry에 등록 (S3 위치)
                try:
                    # S3에 저장된 참조 데이터 경로
                    s3_path = f"s3://{self.bucket}/{REFERENCE_PREFIX}"

                    # Dataset Registry에 영구 등록
                    # (메타데이터로 등록, S3 경로 기록)
                    dataset_name = f"news_reference_{ticker}"

                    mlflow.log_dict(
                        {
                            "dataset_name": dataset_name,
                            "s3_location": f"{s3_path}/{ticker}/",
                            "description": f"{ticker}의 뉴스 요약 평가용 레퍼런스",
                            "num_dates": len(reference_data),
                            "total_news": sum(v.get("count", 0) for v in reference_data.values()),
                        },
                        artifact_file=f"datasets/{dataset_name}/metadata.json"
                    )

                    logger.info(
                        f"✓ Dataset Registry 등록 완료: "
                        f"{dataset_name}\n"
                        f"   위치: {s3_path}/{ticker}/"
                    )

                    # 메트릭 기록
                    total_news = sum(v.get("count", 0) for v in reference_data.values())
                    ticker_metrics[f"reference_{ticker}_dates"] = len(reference_data)
                    ticker_metrics[f"reference_{ticker}_news"] = total_news

                except Exception as e:
                    logger.warning(f"⚠️ MLflow Dataset 등록 실패 ({ticker}): {str(e)}")

            # 최종 메트릭 로깅
            if ticker_metrics:
                self.mlflow_logger.log_metrics(ticker_metrics)

            logger.info("\n✅ 모든 레퍼런스 생성 및 등록 완료")
            logger.info(f"\n📍 MLflow Web UI에서 확인:")
            logger.info(f"   http://52.78.237.104:5001")
            logger.info(f"   → Experiments → {experiment_name} → Run 확인")

            # MLflow run 종료
            self.mlflow_logger.end_run(status="FINISHED")

        except Exception as e:
            logger.error(f"❌ 평가 데이터셋 등록 실패: {str(e)}")
            # 에러 발생 시에도 run 종료
            try:
                self.mlflow_logger.end_run(status="FAILED")
            except:
                pass
            raise


def main():
    """메인 함수"""
    generator = NewsReferenceGenerator()
    generator.register_evaluation_dataset()


if __name__ == "__main__":
    main()

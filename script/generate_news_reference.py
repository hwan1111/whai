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

    def save_reference_to_local(
        self,
        ticker: str,
        reference_data: dict[str, Any],
        output_dir: str = "reference"
    ) -> str:
        """
        레퍼런스 데이터를 로컬에 저장 (evaluation dataset용)

        Args:
            ticker: 종목코드
            reference_data: 레퍼런스 데이터
            output_dir: 출력 디렉토리

        Returns:
            저장된 파일 경로
        """
        try:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)

            file_path = output_path / f"{ticker}_reference.json"

            content = json.dumps(reference_data, ensure_ascii=False, indent=2)
            file_path.write_text(content, encoding="utf-8")

            logger.info(f"✓ 로컬 레퍼런스 저장: {file_path}")
            return str(file_path)

        except Exception as e:
            logger.error(f"❌ 로컬 저장 실패 ({ticker}): {str(e)}")
            raise

    def register_evaluation_dataset(
        self,
        experiment_name: str = "news_summary_service",
        tickers: list[str] | None = None
    ) -> None:
        """
        MLflow evaluation dataset으로 레퍼런스 등록

        Args:
            experiment_name: MLflow 실험 이름
            tickers: 티커 목록 (None이면 S3에서 자동 조회)
        """
        try:
            import mlflow

            # MLflow 실험 설정
            self.mlflow_logger.set_experiment(experiment_name)

            # 티커 목록 조회
            if tickers is None:
                tickers = self.news_loader.list_available_tickers()

            if not tickers:
                logger.warning("⚠️ 처리할 티커가 없습니다")
                return

            logger.info(f"🔄 {len(tickers)}개 티커의 레퍼런스 생성 및 등록 시작")

            reference_dir = Path("reference")
            reference_dir.mkdir(parents=True, exist_ok=True)

            # 각 티커별로 레퍼런스 생성 및 저장
            for ticker in tickers:
                logger.info(f"\n📝 {ticker} 처리 중...")

                # 레퍼런스 생성
                reference_data = self.generate_reference(ticker)

                if not reference_data:
                    logger.warning(f"⚠️ {ticker}: 레퍼런스 데이터 없음, 스킵")
                    continue

                # 로컬 저장
                local_path = self.save_reference_to_local(ticker, reference_data)

                # S3 저장
                self.save_reference_to_s3(ticker, reference_data)

                # MLflow Dataset Registry에 등록
                try:
                    # 1. JSON 파일에서 Dataset 객체 생성
                    dataset = mlflow.data.from_json(local_path)

                    # 2. Dataset Registry에 영구 등록
                    dataset.log_dataset(
                        name=f"news_reference_{ticker}",
                        namespace=experiment_name,
                        description=f"{ticker}의 뉴스 요약 평가용 레퍼런스 ({len(reference_data)}개 날짜)"
                    )
                    logger.info(
                        f"✓ Dataset Registry 등록 완료: "
                        f"news_reference_{ticker} (namespace: {experiment_name})"
                    )

                    # 3. 현재 run이 있으면 Input으로도 로깅 (선택사항)
                    if mlflow.active_run():
                        mlflow.log_input(dataset, context=f"reference/{ticker}")
                        logger.debug(f"  ✓ Run Input으로도 로깅됨")

                except Exception as e:
                    logger.warning(f"⚠️ MLflow Dataset 등록 실패 ({ticker}): {str(e)}")

            logger.info("\n✅ 모든 레퍼런스 생성 및 등록 완료")
            logger.info(f"\n📍 MLflow Web UI에서 확인:")
            logger.info(f"   http://52.78.237.104:5001")
            logger.info(f"   → Datasets 탭에서 'news_reference_*' 검색")

        except Exception as e:
            logger.error(f"❌ 평가 데이터셋 등록 실패: {str(e)}")
            raise


def main():
    """메인 함수"""
    generator = NewsReferenceGenerator()
    generator.register_evaluation_dataset()


if __name__ == "__main__":
    main()

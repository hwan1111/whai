"""
AWS S3 기반 뉴스 데이터 로더

S3에서 뉴스 데이터를 로드합니다.
S3 경로 구조: s3://{bucket}/news/{ticker}/YYYY-MM-DD.json
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class S3NewsDataLoader:
    """AWS S3 기반 뉴스 데이터 로더

    S3 경로 구조: s3://{bucket}/{prefix}/{ticker}/{year}/{month}/{date}.json
    예: s3://fisa-news-archive/raw/000660/2020/05/2020-05-01.json
    """

    def __init__(
        self,
        bucket: Optional[str] = None,
        region: str = "ap-northeast-2",
        prefix: str = "raw",
    ):
        """
        S3NewsDataLoader 초기화

        Args:
            bucket: S3 버킷 이름 (기본값: 환경변수 AWS_S3_BUCKET)
            region: AWS 리전 (기본값: ap-northeast-2)
            prefix: S3 내의 뉴스 데이터 경로 접두어 (기본값: raw)

        Raises:
            ValueError: 버킷이 지정되지 않았을 때
        """
        if bucket is None:
            bucket = os.getenv("AWS_S3_BUCKET")

        if not bucket:
            raise ValueError(
                "❌ S3 버킷이 지정되지 않았습니다. "
                "AWS_S3_BUCKET 환경변수를 설정하거나 bucket 인자를 전달하세요."
            )

        self.bucket = bucket
        self.region = region
        self.prefix = prefix.rstrip("/")

        # S3 클라이언트 초기화
        self.s3_client = boto3.client("s3", region_name=region)

        # 버킷 접근 가능성 확인
        self._verify_bucket_access()

        logger.info(f"✓ S3 뉴스 로더 초기화 완료: s3://{self.bucket}/{self.prefix}/")

    def _verify_bucket_access(self) -> None:
        """
        S3 버킷에 접근 가능한지 확인

        Raises:
            ValueError: 버킷에 접근할 수 없을 때
        """
        try:
            self.s3_client.head_bucket(Bucket=self.bucket)
            logger.debug(f"✓ S3 버킷 접근 확인: {self.bucket}")
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "403":
                raise ValueError(
                    f"❌ S3 버킷에 접근 권한이 없습니다: {self.bucket} "
                    "(AWS 자격증명과 IAM 권한을 확인하세요)"
                )
            elif error_code == "404":
                raise ValueError(
                    f"❌ S3 버킷이 존재하지 않습니다: {self.bucket}"
                )
            else:
                raise ValueError(
                    f"❌ S3 버킷 접근 실패: {self.bucket} ({error_code})"
                )

    def _get_s3_key(self, ticker: str, date_str: str) -> str:
        """
        티커와 날짜로 S3 키 생성

        Args:
            ticker: 종목코드 (예: 000660)
            date_str: 날짜 문자열 (YYYY-MM-DD)

        Returns:
            S3 키 (예: raw/000660/2020/05/2020-05-01.json)
        """
        # 날짜에서 년도와 월 추출
        parts = date_str.split("-")
        if len(parts) != 3:
            raise ValueError(f"날짜 형식이 올바르지 않습니다: {date_str} (형식: YYYY-MM-DD)")

        year = parts[0]
        month = parts[1]

        return f"{self.prefix}/{ticker}/{year}/{month}/{date_str}.json"

    def _parse_date(self, date_str: str) -> datetime:
        """
        문자열을 datetime 객체로 변환

        Args:
            date_str: 날짜 문자열 (YYYY-MM-DD)

        Returns:
            datetime 객체

        Raises:
            ValueError: 날짜 형식이 잘못되었을 때
        """
        try:
            return datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError as e:
            raise ValueError(
                f"❌ 날짜 형식이 잘못되었습니다: {date_str} (형식: YYYY-MM-DD)"
            ) from e

    def load_news(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        """
        날짜 범위와 티커로 S3에서 뉴스 데이터 로드

        Args:
            ticker: 종목코드 (예: 005930)
            start_date: 시작 날짜 (YYYY-MM-DD)
            end_date: 종료 날짜 (YYYY-MM-DD)

        Returns:
            뉴스 데이터 리스트 (날짜 오름차순)

        Raises:
            ValueError: 날짜 형식이 잘못되었을 때
        """
        # 날짜 파싱
        start = self._parse_date(start_date)
        end = self._parse_date(end_date)

        if start > end:
            raise ValueError(
                f"❌ start_date가 end_date보다 클 수 없습니다: {start_date} > {end_date}"
            )

        # S3에서 날짜 범위의 파일 조회
        logger.info(
            f"📂 S3에서 뉴스 조회 중: s3://{self.bucket}/"
            f"{self.prefix}/{ticker}/{{year}}/{{month}}/{{date}}.json"
            f" ({start_date} ~ {end_date})"
        )

        news_list = []
        current = start

        # 시작일부터 종료일까지 하루씩 순회
        from datetime import timedelta
        while current <= end:
            date_str = current.strftime("%Y-%m-%d")
            s3_key = self._get_s3_key(ticker, date_str)

            try:
                # S3에서 객체 읽기
                response = self.s3_client.get_object(Bucket=self.bucket, Key=s3_key)

                # JSON 파싱
                content = response["Body"].read().decode("utf-8")
                news_data = json.loads(content)

                # 리스트 또는 단일 객체 처리
                if isinstance(news_data, list):
                    news_list.extend(news_data)
                    logger.debug(f"  ✓ {date_str}: {len(news_data)}개 뉴스 로드")
                else:
                    news_list.append(news_data)
                    logger.debug(f"  ✓ {date_str}: 1개 뉴스 로드")

            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "Unknown")
                if error_code == "NoSuchKey":
                    # 파일이 없으면 로그하고 계속 진행
                    logger.debug(f"  - {date_str}: 뉴스 파일 없음")
                else:
                    logger.warning(
                        f"  ⚠️ {date_str}: S3 읽기 실패 ({error_code})"
                    )
            except json.JSONDecodeError as e:
                logger.warning(f"  ⚠️ {date_str}: JSON 파싱 실패 - {str(e)}")
            except Exception as e:
                logger.warning(f"  ⚠️ {date_str}: 예기치 않은 오류 - {str(e)}")

            current += timedelta(days=1)

        logger.info(
            f"✓ 뉴스 로드 완료: {ticker} "
            f"({start_date} ~ {end_date}): {len(news_list)}개"
        )

        return news_list

    def get_article_text(self, news_data: dict[str, Any]) -> tuple[str, str]:
        """
        뉴스 데이터에서 제목과 본문 추출

        Args:
            news_data: 뉴스 데이터 딕셔너리

        Returns:
            (제목, 본문) 튜플
        """
        title = news_data.get("title", "")
        fulltext = news_data.get("fulltext", "")
        return title, fulltext

    def get_news_metadata(self, news_data: dict[str, Any]) -> dict[str, Any]:
        """
        뉴스 메타데이터 추출

        Args:
            news_data: 뉴스 데이터 딕셔너리

        Returns:
            메타데이터 (날짜, 회사명, 링크 등)
        """
        return {
            "pub_date": news_data.get("pub_date"),
            "ticker": news_data.get("ticker"),
            "company_name": news_data.get("company_name"),
            "link": news_data.get("link"),
            "source": news_data.get("source"),
        }

    def list_available_tickers(self) -> list[str]:
        """
        S3에서 사용 가능한 모든 티커 목록 반환

        Returns:
            티커 리스트
        """
        try:
            tickers = set()

            # S3의 prefix/ 아래에 있는 모든 "폴더" 조회
            paginator = self.s3_client.get_paginator("list_objects_v2")
            pages = paginator.paginate(
                Bucket=self.bucket,
                Prefix=f"{self.prefix}/",
                Delimiter="/"
            )

            for page in pages:
                if "CommonPrefixes" in page:
                    for prefix_info in page["CommonPrefixes"]:
                        # prefix 형태: "news/005930/"
                        prefix = prefix_info["Prefix"]
                        ticker = prefix.rstrip("/").split("/")[-1]
                        tickers.add(ticker)

            tickers = sorted(list(tickers))
            logger.info(f"사용 가능한 티커 (S3): {', '.join(tickers)}")
            return tickers

        except Exception as e:
            logger.error(f"❌ S3 티커 목록 조회 실패: {str(e)}")
            return []

    def upload_news(
        self,
        ticker: str,
        date_str: str,
        news_data: dict[str, Any],
    ) -> bool:
        """
        뉴스 데이터를 S3에 저장

        Args:
            ticker: 종목코드
            date_str: 날짜 (YYYY-MM-DD)
            news_data: 뉴스 데이터 딕셔너리 또는 리스트

        Returns:
            성공 여부
        """
        try:
            s3_key = self._get_s3_key(ticker, date_str)

            # JSON으로 직렬화
            json_content = json.dumps(news_data, ensure_ascii=False, indent=2)

            # S3에 업로드
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=s3_key,
                Body=json_content.encode("utf-8"),
                ContentType="application/json",
            )

            logger.info(f"✓ 뉴스 저장 완료: s3://{self.bucket}/{s3_key}")
            return True

        except Exception as e:
            logger.error(f"❌ 뉴스 저장 실패: {str(e)}")
            return False

    def load_references(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        reference_prefix: str = "reference",
    ) -> dict[str, str]:
        """
        S3에서 레퍼런스 요약 로드

        경로 구조: s3://{bucket}/{reference_prefix}/{ticker}/{year}/{month}/{date}.json
        예: s3://fisa-news-archive/reference/000660/2020/05/2020-05-01.json

        Args:
            ticker: 종목코드 (예: 000660)
            start_date: 시작 날짜 (YYYY-MM-DD)
            end_date: 종료 날짜 (YYYY-MM-DD)
            reference_prefix: S3 내 레퍼런스 경로 접두어 (기본값: reference)

        Returns:
            {news_id: reference_summary} 딕셔너리

        Raises:
            ValueError: 날짜 형식이 잘못되었을 때
        """
        # 날짜 파싱
        start = self._parse_date(start_date)
        end = self._parse_date(end_date)

        if start > end:
            raise ValueError(
                f"❌ start_date가 end_date보다 클 수 없습니다: {start_date} > {end_date}"
            )

        logger.info(
            f"📚 S3에서 레퍼런스 로드 중: "
            f"s3://{self.bucket}/{reference_prefix}/{ticker}/{{year}}/{{month}}/{{date}}.json "
            f"({start_date} ~ {end_date})"
        )

        reference_summaries = {}
        current = start

        # 시작일부터 종료일까지 하루씩 순회
        from datetime import timedelta
        while current <= end:
            date_str = current.strftime("%Y-%m-%d")

            # 레퍼런스 S3 키 생성
            parts = date_str.split("-")
            year, month = parts[0], parts[1]
            s3_key = f"{reference_prefix}/{ticker}/{year}/{month}/{date_str}.json"

            try:
                # S3에서 객체 읽기
                response = self.s3_client.get_object(Bucket=self.bucket, Key=s3_key)
                content = response["Body"].read().decode("utf-8")
                ref_data = json.loads(content)

                # 데이터 형식 처리
                if isinstance(ref_data, dict):
                    # 딕셔너리 형식: {news_id: summary}
                    reference_summaries.update(ref_data)
                    logger.debug(f"  ✓ {date_str}: {len(ref_data)}개 레퍼런스 로드")

                elif isinstance(ref_data, list):
                    # 리스트 형식: [{id: ..., summary: ...}]
                    for item in ref_data:
                        if isinstance(item, dict):
                            item_id = (
                                item.get("id") or
                                item.get("article_id") or
                                item.get("news_id")
                            )
                            summary = item.get("summary") or item.get("reference_summary")

                            if item_id and summary:
                                reference_summaries[item_id] = summary
                                logger.debug(f"  ✓ {date_str}: {item_id} 로드")

            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "Unknown")
                if error_code == "NoSuchKey":
                    logger.debug(f"  - {date_str}: 레퍼런스 파일 없음")
                else:
                    logger.warning(f"  ⚠️ {date_str}: S3 읽기 실패 ({error_code})")
            except json.JSONDecodeError as e:
                logger.warning(f"  ⚠️ {date_str}: JSON 파싱 실패 - {str(e)}")
            except Exception as e:
                logger.warning(f"  ⚠️ {date_str}: 예기치 않은 오류 - {str(e)}")

            current += timedelta(days=1)

        logger.info(
            f"✓ 레퍼런스 로드 완료: {ticker} "
            f"({start_date} ~ {end_date}): {len(reference_summaries)}개"
        )

        return reference_summaries

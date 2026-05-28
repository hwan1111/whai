"""
뉴스 데이터 로더

S3 또는 로컬 JSON 파일에서 뉴스 데이터를 로드하고 필터링합니다.

S3 구조  : s3://{bucket}/raw/{ticker}/{yyyy}/{mm}/{yyyy-mm-dd}.json
로컬 구조 : data/News_{company_name}_{ticker}/YYYY-MM-DD.json
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

S3_BUCKET_DEFAULT = "fisa-news-archive"
S3_PREFIX_DEFAULT = "raw"


class NewsDataLoader:
    """뉴스 데이터 로더 (S3 우선, 로컬 fallback)"""

    def __init__(
        self,
        data_root: Optional[Path] = None,
        s3_bucket: str = S3_BUCKET_DEFAULT,
        s3_prefix: str = S3_PREFIX_DEFAULT,
        use_s3: bool = True,
    ):
        """
        Args:
            data_root: 로컬 뉴스 루트 디렉토리 (use_s3=False 또는 fallback 시 사용)
            s3_bucket: S3 버킷명
            s3_prefix: S3 키 접두어
            use_s3: True면 S3에서 로드, False면 로컬에서 로드
        """
        if data_root is None:
            project_root = Path(__file__).parent.parent.parent
            data_root = project_root / "data"

        self.data_root = data_root
        self.s3_bucket = s3_bucket
        self.s3_prefix = s3_prefix
        self.use_s3 = use_s3
        self._s3_client = None

        if use_s3:
            logger.info(f"✓ S3 모드: s3://{s3_bucket}/{s3_prefix}/{{ticker}}/")
        else:
            logger.info(f"✓ 로컬 모드: {self.data_root}")

    def _get_s3_client(self):
        if self._s3_client is None:
            import boto3
            self._s3_client = boto3.client("s3")
        return self._s3_client

    def _load_from_s3(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        """S3에서 날짜 범위의 뉴스 로드."""
        from botocore.exceptions import ClientError

        s3 = self._get_s3_client()
        start = self._parse_date(start_date)
        end   = self._parse_date(end_date)
        cur   = start
        news_list: list[dict] = []
        seen: set[str] = set()

        while cur <= end:
            key = (
                f"{self.s3_prefix}/{ticker}/{cur.year}/{cur.month:02d}"
                f"/{cur.strftime('%Y-%m-%d')}.json"
            )
            try:
                obj  = s3.get_object(Bucket=self.s3_bucket, Key=key)
                data = json.loads(obj["Body"].read().decode("utf-8"))
                uid  = f"{data.get('pub_date','')}|{data.get('title','')}"
                if uid not in seen:
                    seen.add(uid)
                    news_list.append(data)
            except ClientError as e:
                if e.response["Error"]["Code"] not in ("NoSuchKey", "404"):
                    logger.warning(f"S3 오류 {key}: {e}")
            except Exception as e:
                logger.warning(f"S3 fetch 실패 {key}: {e}")
            cur += timedelta(days=1)

        return sorted(news_list, key=lambda x: x.get("pub_date", ""))

    def _get_news_dir(self, ticker: str) -> Optional[Path]:
        """
        티커에 해당하는 뉴스 디렉토리 찾기

        Args:
            ticker: 종목코드 (예: "005930")

        Returns:
            뉴스 디렉토리 경로 또는 None
        """
        if not self.data_root.exists():
            logger.warning(f"⚠️ 데이터 루트가 없습니다: {self.data_root}")
            return None

        # data/ 디렉토리 내에서 ticker를 포함하는 디렉토리 찾기
        # 패턴: News_{company_name}_{ticker}/
        for item in self.data_root.iterdir():
            if item.is_dir() and item.name.startswith("News_") and item.name.endswith(f"_{ticker}"):
                return item

        logger.warning(f"⚠️ 뉴스 디렉토리를 찾을 수 없습니다: {ticker}")
        return None

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
        날짜 범위와 티커로 뉴스 데이터 로드

        Args:
            ticker: 종목코드 (예: "005930")
            start_date: 시작 날짜 (YYYY-MM-DD)
            end_date: 종료 날짜 (YYYY-MM-DD)

        Returns:
            뉴스 데이터 리스트 (날짜 오름차순)

        Raises:
            FileNotFoundError: 뉴스 디렉토리를 찾을 수 없을 때
            ValueError: 날짜 형식이 잘못되었을 때
        """
        start = self._parse_date(start_date)
        end   = self._parse_date(end_date)
        if start > end:
            raise ValueError(
                f"❌ start_date가 end_date보다 클 수 없습니다: {start_date} > {end_date}"
            )

        if self.use_s3:
            news_list = self._load_from_s3(ticker, start_date, end_date)
            logger.info(f"✓ S3 뉴스 로드: {ticker} ({start_date}~{end_date}) {len(news_list)}개")
            return news_list

        # 로컬 모드
        news_dir = self._get_news_dir(ticker)
        if news_dir is None:
            raise FileNotFoundError(
                f"❌ 티커 {ticker}의 뉴스 디렉토리를 찾을 수 없습니다"
            )

        news_list = []
        for json_file in sorted(news_dir.glob("*.json")):
            try:
                file_date = self._parse_date(json_file.stem)
                if start <= file_date <= end:
                    with open(json_file, "r", encoding="utf-8") as f:
                        news_list.append(json.load(f))
            except (ValueError, json.JSONDecodeError) as e:
                logger.warning(f"⚠️ 파일 로드 실패: {json_file} - {str(e)}")

        logger.info(f"✓ 로컬 뉴스 로드: {ticker} ({start_date}~{end_date}) {len(news_list)}개")
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
        사용 가능한 모든 티커 목록 반환

        Returns:
            티커 리스트
        """
        if not self.data_root.exists():
            return []

        tickers = []
        for item in self.data_root.iterdir():
            if item.is_dir() and item.name.startswith("News_"):
                # 패턴: News_{company_name}_{ticker}
                parts = item.name.split("_")
                if len(parts) >= 2:
                    ticker = parts[-1]  # 마지막 부분이 티커
                    tickers.append(ticker)

        logger.info(f"사용 가능한 티커: {', '.join(sorted(tickers))}")
        return sorted(tickers)

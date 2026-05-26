"""
뉴스 데이터 로더

로컬 JSON 파일에서 뉴스 데이터를 로드하고 필터링합니다.
파일 구조: data/News_{company_name}_{ticker}/YYYY-MM-DD.json
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class NewsDataLoader:
    """뉴스 데이터 로더"""

    def __init__(self, data_root: Optional[Path] = None):
        """
        NewsDataLoader 초기화

        Args:
            data_root: 뉴스 데이터 루트 디렉토리
                      기본값: project_root/data/
        """
        if data_root is None:
            project_root = Path(__file__).parent.parent.parent
            data_root = project_root / "data"

        self.data_root = data_root
        logger.info(f"✓ 뉴스 데이터 루트: {self.data_root}")

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
        # 뉴스 디렉토리 찾기
        news_dir = self._get_news_dir(ticker)
        if news_dir is None:
            raise FileNotFoundError(
                f"❌ 티커 {ticker}의 뉴스 디렉토리를 찾을 수 없습니다"
            )

        # 날짜 파싱
        start = self._parse_date(start_date)
        end = self._parse_date(end_date)

        if start > end:
            raise ValueError(
                f"❌ start_date가 end_date보다 클 수 없습니다: {start_date} > {end_date}"
            )

        # 뉴스 파일 로드
        news_list = []
        json_files = sorted(news_dir.glob("*.json"))

        for json_file in json_files:
            try:
                # 파일명에서 날짜 추출 (YYYY-MM-DD.json)
                file_date_str = json_file.stem
                file_date = self._parse_date(file_date_str)

                # 날짜 범위 확인
                if start <= file_date <= end:
                    with open(json_file, "r", encoding="utf-8") as f:
                        news_data = json.load(f)
                        news_list.append(news_data)

            except (ValueError, json.JSONDecodeError) as e:
                logger.warning(f"⚠️ 파일 로드 실패: {json_file} - {str(e)}")
                continue

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

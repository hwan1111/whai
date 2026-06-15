"""
MySQL에서 국면 데이터 로드

Aiven MySQL의 whai_service.regime / asset 테이블에서
국면 정보와 종목 메타데이터를 조회합니다.
"""

import logging
import os
from typing import Any, Optional

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(".env")

logger = logging.getLogger(__name__)

DEFAULT_CERTS_PATH = "config/backend/certs/ca.pem"


class RegimeDBLoader:
    """MySQL에서 국면 데이터 로드"""

    def __init__(
        self,
        database_url: Optional[str] = None,
        certs_path: Optional[str] = None,
    ):
        """
        초기화

        Args:
            database_url: 데이터베이스 URL (기본값: .env의 SERVICE_DATABASE_URL)
            certs_path: SSL 인증서 경로 (기본값: .env의 BACKEND_CERTS_PATH)
        """
        if database_url is None:
            database_url = os.getenv("SERVICE_DATABASE_URL")

        if not database_url:
            raise ValueError(
                "DATABASE_URL이 지정되지 않았습니다. "
                ".env에 SERVICE_DATABASE_URL을 설정하세요."
            )

        certs_path = certs_path or os.getenv("BACKEND_CERTS_PATH", DEFAULT_CERTS_PATH)

        # Aiven MySQL은 ssl_ca 쿼리 파라미터를 pymysql 커넥션 kwarg로 직접 넘기지 못하므로
        # 쿼리스트링을 분리하고 connect_args로 SSL 설정을 전달한다.
        if "ssl_ca=" in database_url:
            base_url = database_url.split("?")[0]
            url = f"{base_url}?charset=utf8mb4"
            connect_args: dict[str, Any] = {"ssl": {"ca": certs_path}}
        else:
            url = database_url
            connect_args = {}

        self.database_url = url
        self.engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)

        self._verify_connection()

        logger.info("✓ 국면 DB 로더 초기화 완료")

    def _verify_connection(self) -> None:
        """DB 연결 확인"""
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.debug("✓ DB 연결 확인 완료")
        except Exception as e:
            raise ValueError(f"❌ DB 연결 실패: {e}") from e

    def load_regimes(
        self,
        tickers: Optional[list[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """
        국면 데이터 조회

        start_date/end_date는 국면이 해당 기간과 겹치는지(overlap) 기준으로 필터링한다.
        국면의 [start_date, end_date] 구간이 조회 범위와 조금이라도 겹치면 포함되며,
        국면 전체가 범위 안에 포함될 필요는 없다.

        Args:
            tickers: 조회할 종목코드 목록 (선택사항, 기본값: 전체)
            start_date: 조회 시작일 (YYYY-MM-DD, 선택사항)
                — regime.end_date >= start_date (국면이 이 날짜 이후까지 이어짐)
            end_date: 조회 종료일 (YYYY-MM-DD, 선택사항)
                — regime.start_date <= end_date (국면이 이 날짜 이전에 시작됨)

        Returns:
            국면 데이터 리스트 (ticker 포함)
        """
        try:
            query = """
            SELECT
                id,
                ticker,
                regime_id,
                start_date,
                end_date,
                direction,
                cum_return,
                days,
                vol_trend,
                news_count,
                tokens_in,
                created_at
            FROM regime
            WHERE 1=1
            """

            params: dict[str, Any] = {}

            if tickers:
                placeholders = ", ".join(f":ticker_{i}" for i in range(len(tickers)))
                query += f" AND ticker IN ({placeholders})"
                for i, t in enumerate(tickers):
                    params[f"ticker_{i}"] = t

            if start_date:
                query += " AND end_date >= :start_date"
                params["start_date"] = start_date

            if end_date:
                query += " AND start_date <= :end_date"
                params["end_date"] = end_date

            query += " ORDER BY ticker ASC, start_date ASC"

            with self.engine.connect() as conn:
                result = conn.execute(text(query), params)
                rows = result.fetchall()

            regimes = []
            for row in rows:
                regimes.append({
                    "id": row[0],
                    "ticker": row[1],
                    "regime_id": row[2],
                    "start": row[3],
                    "end": row[4],
                    "direction": row[5],
                    "cum_return": row[6],
                    "days": row[7],
                    "vol_trend": row[8],
                    "news_count": row[9],
                    "tokens_in": row[10],
                    "created_at": row[11],
                })

            logger.info(
                f"✓ 국면 데이터 로드: "
                f"(tickers={tickers or '-'}, {start_date or '-'} ~ {end_date or '-'}): "
                f"{len(regimes)}개"
            )
            return regimes

        except Exception as e:
            logger.error(f"❌ 국면 데이터 로드 실패: {e}")
            return []

    def get_regime_by_id(self, regime_id: int) -> Optional[dict[str, Any]]:
        """
        특정 국면 조회

        Args:
            regime_id: regime 테이블의 id (PK)

        Returns:
            국면 데이터 또는 None
        """
        try:
            query = """
            SELECT
                id,
                ticker,
                regime_id,
                start_date,
                end_date,
                direction,
                cum_return,
                days,
                vol_trend,
                news_count,
                tokens_in,
                created_at
            FROM regime
            WHERE id = :regime_id
            """

            with self.engine.connect() as conn:
                result = conn.execute(text(query), {"regime_id": regime_id})
                row = result.fetchone()

            if not row:
                return None

            return {
                "id": row[0],
                "ticker": row[1],
                "regime_id": row[2],
                "start": row[3],
                "end": row[4],
                "direction": row[5],
                "cum_return": row[6],
                "days": row[7],
                "vol_trend": row[8],
                "news_count": row[9],
                "tokens_in": row[10],
                "created_at": row[11],
            }

        except Exception as e:
            logger.error(f"❌ 국면 조회 실패 (ID={regime_id}): {e}")
            return None

    def get_regime_count(self) -> int:
        """
        DB의 전체 국면 개수 조회

        Returns:
            국면 개수
        """
        try:
            query = "SELECT COUNT(*) FROM regime"

            with self.engine.connect() as conn:
                result = conn.execute(text(query))
                count = result.scalar()

            logger.info(f"✓ 전체 국면: {count}개")
            return count or 0

        except Exception as e:
            logger.error(f"❌ 국면 개수 조회 실패: {e}")
            return 0

    def get_asset_info(self, ticker: str) -> Optional[dict[str, str]]:
        """
        asset 테이블에서 종목명/섹터 조회

        Args:
            ticker: 종목코드 (예: 005930)

        Returns:
            {"ticker": ..., "name": ..., "sector": ...} 또는 None
        """
        try:
            query = "SELECT ticker, name, sector FROM asset WHERE ticker = :ticker"

            with self.engine.connect() as conn:
                result = conn.execute(text(query), {"ticker": ticker})
                row = result.fetchone()

            if not row:
                logger.warning(f"⚠️ asset 테이블에 종목 정보 없음: {ticker}")
                return None

            return {"ticker": row[0], "name": row[1], "sector": row[2] or ""}

        except Exception as e:
            logger.error(f"❌ 종목 정보 조회 실패 ({ticker}): {e}")
            return None

    def get_distinct_tickers(self) -> list[str]:
        """
        regime 테이블에 존재하는 모든 ticker 목록 조회

        Returns:
            종목코드 리스트
        """
        try:
            query = "SELECT DISTINCT ticker FROM regime ORDER BY ticker ASC"

            with self.engine.connect() as conn:
                result = conn.execute(text(query))
                rows = result.fetchall()

            return [row[0] for row in rows]

        except Exception as e:
            logger.error(f"❌ 티커 목록 조회 실패: {e}")
            return []

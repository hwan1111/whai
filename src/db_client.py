import os
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from dotenv import load_dotenv

load_dotenv()


class MySQLClient:
    """MySQL 데이터베이스 연결 및 관리."""

    def __init__(self):
        self.host = os.getenv("MYSQL_HOST")
        self.port = os.getenv("MYSQL_PORT", "3306")
        self.user = os.getenv("MYSQL_USER")
        self.password = os.getenv("MYSQL_PASSWORD")
        self.database = os.getenv("MYSQL_DATABASE")
        
        self.engine: Engine | None = None
        self._connection_string: str | None = None

    @property
    def connection_string(self) -> str:
        """데이터베이스 연결 문자열 생성."""
        if not self._connection_string:
            self._connection_string = (
                f"mysql+pymysql://{self.user}:{self.password}@"
                f"{self.host}:{self.port}/{self.database}"
            )
        return self._connection_string

    def connect(self) -> Engine:
        """MySQL 데이터베이스 연결."""
        if not self.engine:
            try:
                self.engine = create_engine(self.connection_string, echo=False)
            except Exception as e:
                raise ConnectionError(f"MySQL 연결 실패: {e}")
        return self.engine

    def test_connection(self) -> bool:
        """데이터베이스 연결 테스트."""
        try:
            engine = self.connect()
            with engine.connect() as connection:
                result = connection.execute(text("SELECT 1"))
                return result.fetchone() is not None
        except Exception as e:
            print(f"연결 테스트 실패: {e}")
            return False

    def execute_query(self, query: str, params: dict | None = None) -> list[dict]:
        """SQL 쿼리 실행 및 결과 반환."""
        try:
            engine = self.connect()
            with engine.connect() as connection:
                result = connection.execute(text(query), params or {})
                columns = result.keys()
                return [dict(zip(columns, row)) for row in result.fetchall()]
        except Exception as e:
            raise RuntimeError(f"쿼리 실행 실패: {e}")

    def execute_update(self, query: str, params: dict | None = None) -> int:
        """INSERT, UPDATE, DELETE 쿼리 실행."""
        try:
            engine = self.connect()
            with engine.begin() as connection:
                result = connection.execute(text(query), params or {})
                return result.rowcount
        except Exception as e:
            raise RuntimeError(f"업데이트 실패: {e}")

    def close(self):
        """데이터베이스 연결 종료."""
        if self.engine:
            self.engine.dispose()
            self.engine = None

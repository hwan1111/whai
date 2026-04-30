import pytest
from src.db_client import MySQLClient
import os


class TestMySQLConnection:
    """MySQL 데이터베이스 연결 테스트."""

    @pytest.fixture
    def db_client(self):
        """데이터베이스 클라이언트 인스턴스."""
        client = MySQLClient()
        yield client
        client.close()

    def test_connection_string(self, db_client):
        """연결 문자열 생성 테스트."""
        connection_str = db_client.connection_string
        assert connection_str.startswith("mysql+pymysql://")
        assert db_client.host in connection_str
        assert db_client.database in connection_str

    def test_environment_variables(self):
        """필수 환경변수 확인."""
        required_vars = ["MYSQL_HOST", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE"]
        for var in required_vars:
            assert os.getenv(var), f"환경변수 {var}가 설정되지 않았습니다"

    def test_test_connection(self, db_client):
        """데이터베이스 연결 테스트."""
        result = db_client.test_connection()
        assert isinstance(result, bool)
        assert result is True, "MySQL 서버 연결 실패"

    def test_execute_query(self, db_client):
        """단순 SELECT 쿼리 테스트."""
        result = db_client.execute_query("SELECT 1 as test_value")
        assert len(result) > 0
        assert result[0]["test_value"] == 1

    def test_execute_update_insert(self, db_client):
        """INSERT 쿼리 테스트."""
        # 테스트 테이블 생성
        db_client.execute_update(
            "CREATE TABLE IF NOT EXISTS test_table (id INT PRIMARY KEY, name VARCHAR(100))"
        )
        
        # INSERT
        result = db_client.execute_update("INSERT INTO test_table VALUES (1, 'test')")
        assert result > 0
        
        # 정리
        db_client.execute_update("DROP TABLE test_table")


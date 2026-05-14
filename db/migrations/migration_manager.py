"""마이그레이션 관리자 - SQL 파일 실행 및 추적"""

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
import logging

import pymysql
from pymysql import cursors

logger = logging.getLogger(__name__)


class MigrationManager:
    """SQL 마이그레이션 파일을 관리하고 실행하는 클래스"""

    MIGRATION_TABLE = "migration_history"

    def __init__(self, db_url: str, migration_dir: str = None):
        """
        Args:
            db_url: MySQL 연결 문자열 (mysql+pymysql://user:pass@host:port/db)
            migration_dir: SQL 파일이 있는 디렉토리 (기본: db/)
        """
        self.db_url = db_url
        self.migration_dir = Path(migration_dir or __file__).parent.parent
        self.connection = None
        self._parse_db_config()

    def _parse_db_config(self):
        """db_url에서 연결 정보 파싱

        형식: mysql+pymysql://user:pass@host:port/database[?ssl_ca=...]
        """
        # 쿼리 파라미터 분리 (예: ?ssl_ca=path/to/ca.pem)
        url = self.db_url
        query_params = {}

        if "?" in url:
            url, query_string = url.split("?", 1)
            # 쿼리 파라미터 파싱
            for param in query_string.split("&"):
                if "=" in param:
                    key, value = param.split("=", 1)
                    query_params[key] = value

        # 기본 URL 파싱
        match = re.match(
            r"mysql\+pymysql://([^:]+):([^@]+)@([^:]+):(\d+)/([^/?]+)",
            url
        )
        if not match:
            raise ValueError(f"Invalid database URL format: {self.db_url}")

        self.db_config = {
            "user": match.group(1),
            "password": match.group(2),
            "host": match.group(3),
            "port": int(match.group(4)),
            "database": match.group(5),
        }

        # SSL 인증서 경로 처리
        if "ssl_ca" in query_params:
            ssl_ca_path = query_params["ssl_ca"]
            # 상대 경로를 절대 경로로 변환
            if not ssl_ca_path.startswith("/"):
                ssl_ca_path = Path(self.migration_dir).parent / ssl_ca_path

            if Path(ssl_ca_path).exists():
                self.db_config["ssl_ca"] = str(ssl_ca_path)
                logger.debug(f"SSL certificate configured: {ssl_ca_path}")
            else:
                logger.warning(f"SSL certificate not found: {ssl_ca_path}")

        logger.debug(f"Database config parsed: {self.db_config['host']}:{self.db_config['port']}/{self.db_config['database']}")

    def connect(self):
        """데이터베이스 연결"""
        try:
            self.connection = pymysql.connect(
                **self.db_config,
                charset="utf8mb4",
                cursorclass=cursors.DictCursor,
            )
            logger.info(f"✅ Connected to {self.db_config['host']}:{self.db_config['port']}/{self.db_config['database']}")
        except Exception as e:
            logger.error(f"❌ Connection failed: {e}")
            raise

    def disconnect(self):
        """데이터베이스 연결 종료"""
        if self.connection:
            self.connection.close()
            logger.info("Disconnected from database")

    def _ensure_migration_table(self):
        """마이그레이션 히스토리 테이블 생성"""
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")

        create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS `{self.MIGRATION_TABLE}` (
            `id` BIGINT NOT NULL AUTO_INCREMENT,
            `migration_name` VARCHAR(255) NOT NULL UNIQUE COMMENT '마이그레이션 파일명',
            `executed_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '실행 시간',
            `status` ENUM('success', 'failed', 'pending') DEFAULT 'success' COMMENT '실행 상태',
            `error_message` TEXT COMMENT '오류 메시지',
            PRIMARY KEY (`id`),
            INDEX `idx_migration_name` (`migration_name`),
            INDEX `idx_executed_at` (`executed_at`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        COMMENT='마이그레이션 실행 이력';
        """

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(create_table_sql)
            self.connection.commit()
            logger.info(f"✅ Migration history table '{self.MIGRATION_TABLE}' ready")
        except Exception as e:
            logger.error(f"❌ Failed to create migration table: {e}")
            raise

    def _get_executed_migrations(self) -> set:
        """이미 실행된 마이그레이션 조회"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT migration_name FROM `{self.MIGRATION_TABLE}` WHERE status = 'success'"
                )
                result = cursor.fetchall()
                return {row["migration_name"] for row in result}
        except Exception:
            return set()

    def _record_migration(self, name: str, status: str, error_message: str = None):
        """마이그레이션 실행 기록"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    INSERT INTO `{self.MIGRATION_TABLE}`
                    (migration_name, status, error_message)
                    VALUES (%s, %s, %s)
                    """,
                    (name, status, error_message),
                )
            self.connection.commit()
        except pymysql.IntegrityError:
            # 이미 기록된 마이그레이션이면 무시
            pass
        except Exception as e:
            logger.warning(f"Failed to record migration: {e}")

    def get_migration_files(self) -> list:
        """마이그레이션 SQL 파일 목록 조회 (번호 순서)"""
        sql_files = sorted([
            f for f in os.listdir(self.migration_dir)
            if f.endswith(".sql") and f[0].isdigit()
        ])
        return sql_files

    def get_status(self) -> dict:
        """마이그레이션 상태 조회"""
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")

        all_migrations = self.get_migration_files()
        executed = self._get_executed_migrations()

        status = {
            "total": len(all_migrations),
            "executed": len(executed),
            "pending": len(all_migrations) - len(executed),
            "migrations": {},
        }

        for migration in all_migrations:
            status["migrations"][migration] = {
                "status": "✅ executed" if migration in executed else "⏳ pending",
                "file": self.migration_dir / migration,
            }

        return status

    def run_migration(self, migration_name: str = None, dry_run: bool = False) -> bool:
        """
        마이그레이션 실행

        Args:
            migration_name: 특정 마이그레이션만 실행 (None이면 모두 실행)
            dry_run: True면 실제 실행하지 않고 파일만 읽음

        Returns:
            성공 여부
        """
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")

        # 마이그레이션 테이블 생성
        self._ensure_migration_table()

        # 실행할 파일 목록
        all_migrations = self.get_migration_files()
        executed = self._get_executed_migrations()

        if migration_name:
            # 특정 마이그레이션만 실행
            if migration_name not in all_migrations:
                logger.error(f"❌ Migration file not found: {migration_name}")
                return False
            migrations_to_run = [migration_name]
        else:
            # 미실행 마이그레이션만 실행
            migrations_to_run = [m for m in all_migrations if m not in executed]

        if not migrations_to_run:
            logger.info("✅ All migrations are already executed")
            return True

        logger.info(f"\n📋 Running {len(migrations_to_run)} migration(s)...")
        success_count = 0

        for migration in migrations_to_run:
            file_path = self.migration_dir / migration
            logger.info(f"\n🔄 Executing: {migration}")

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    sql_content = f.read()

                if dry_run:
                    logger.info(f"[DRY RUN] Would execute {len(sql_content)} bytes")
                    self._record_migration(migration, "pending")
                    success_count += 1
                    continue

                # SQL 파일 실행
                with self.connection.cursor() as cursor:
                    # 여러 문장을 분리해서 실행
                    for statement in self._split_sql(sql_content):
                        if statement.strip():
                            cursor.execute(statement)

                self.connection.commit()
                self._record_migration(migration, "success")
                logger.info(f"✅ {migration} executed successfully")
                success_count += 1

            except Exception as e:
                self.connection.rollback()
                error_msg = str(e)
                self._record_migration(migration, "failed", error_msg)
                logger.error(f"❌ {migration} failed: {error_msg}")

        logger.info(f"\n✅ Migration complete: {success_count}/{len(migrations_to_run)} successful")
        return success_count == len(migrations_to_run)

    @staticmethod
    def _split_sql(sql_content: str) -> list:
        """SQL 파일을 여러 문장으로 분리"""
        statements = []
        current = []
        in_string = False
        string_char = None

        for line in sql_content.split("\n"):
            # 주석 제거
            stripped = line.split("--")[0].strip()
            if not stripped:
                continue

            current.append(stripped + " ")

            # 세미콜론으로 문장 종료 (따옴표 밖에서만)
            if ";" in stripped:
                statements.append("".join(current))
                current = []

        if current:
            statements.append("".join(current))

        return statements

    def get_migration_info(self, migration_name: str) -> dict:
        """특정 마이그레이션 정보 조회"""
        file_path = self.migration_dir / migration_name

        if not file_path.exists():
            raise FileNotFoundError(f"Migration file not found: {migration_name}")

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 첫 번째 주석 추출 (설명)
        match = re.search(r"--\s*(.+?)(?:\n|$)", content)
        description = match.group(1) if match else "No description"

        executed = self._get_executed_migrations()

        return {
            "name": migration_name,
            "path": str(file_path),
            "size": len(content),
            "description": description,
            "status": "executed" if migration_name in executed else "pending",
        }

    def print_status(self):
        """마이그레이션 상태 출력"""
        status = self.get_status()

        print("\n" + "=" * 70)
        print("📊 MIGRATION STATUS")
        print("=" * 70)
        print(f"Total:   {status['total']}")
        print(f"Execute: {status['executed']}")
        print(f"Pending: {status['pending']}")
        print("=" * 70)
        print("\nMigrations:")
        for name, info in status["migrations"].items():
            print(f"  {info['status']}  {name}")
        print("=" * 70 + "\n")

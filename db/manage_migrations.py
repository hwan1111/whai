#!/usr/bin/env python3
"""마이그레이션 관리 CLI 도구"""

import os
import sys
import argparse
import logging
from pathlib import Path
from dotenv import load_dotenv

from migrations.migration_manager import MigrationManager

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def load_env():
    """환경 변수 로드"""
    # 현재 디렉토리의 .env.local 또는 프로젝트 루트의 .env 찾기
    env_paths = [
        Path(__file__).parent.parent / ".env.local",
        Path(__file__).parent.parent / ".env",
    ]

    for env_path in env_paths:
        if env_path.exists():
            load_dotenv(env_path)
            logger.info(f"Loaded environment from: {env_path}")
            return

    logger.warning("No .env or .env.local file found")


def cmd_status(args):
    """마이그레이션 상태 조회"""
    db_url = os.getenv("SERVICE_DATABASE_URL")
    if not db_url:
        logger.error("❌ SERVICE_DATABASE_URL not set in environment")
        sys.exit(1)

    manager = MigrationManager(db_url)
    manager.connect()

    try:
        manager.print_status()
    finally:
        manager.disconnect()


def cmd_run(args):
    """마이그레이션 실행"""
    db_url = os.getenv("SERVICE_DATABASE_URL")
    if not db_url:
        logger.error("❌ SERVICE_DATABASE_URL not set in environment")
        sys.exit(1)

    manager = MigrationManager(db_url)
    manager.connect()

    try:
        success = manager.run_migration(
            migration_name=args.migration,
            dry_run=args.dry_run
        )
        sys.exit(0 if success else 1)
    finally:
        manager.disconnect()


def cmd_info(args):
    """특정 마이그레이션 정보 조회"""
    db_url = os.getenv("SERVICE_DATABASE_URL")
    if not db_url:
        logger.error("❌ SERVICE_DATABASE_URL not set in environment")
        sys.exit(1)

    manager = MigrationManager(db_url)
    manager.connect()

    try:
        info = manager.get_migration_info(args.migration)
        print("\n" + "=" * 70)
        print(f"📄 Migration Info: {info['name']}")
        print("=" * 70)
        print(f"Path:        {info['path']}")
        print(f"Size:        {info['size']} bytes")
        print(f"Status:      {info['status']}")
        print(f"Description: {info['description']}")
        print("=" * 70 + "\n")
    except FileNotFoundError as e:
        logger.error(f"❌ {e}")
        sys.exit(1)
    finally:
        manager.disconnect()


def cmd_list(args):
    """마이그레이션 파일 목록"""
    db_url = os.getenv("SERVICE_DATABASE_URL")
    if not db_url:
        logger.error("❌ SERVICE_DATABASE_URL not set in environment")
        sys.exit(1)

    manager = MigrationManager(db_url)
    files = manager.get_migration_files()

    print("\n" + "=" * 70)
    print("📋 Migration Files")
    print("=" * 70)
    for i, f in enumerate(files, 1):
        print(f"{i:2d}. {f}")
    print("=" * 70 + "\n")


def main():
    """메인 CLI 엔트리포인트"""
    load_env()

    parser = argparse.ArgumentParser(
        description="🔄 Database Migration Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python manage_migrations.py status              # Show migration status
  python manage_migrations.py run                 # Run all pending migrations
  python manage_migrations.py run --migration 01_basic_tables.sql  # Run specific
  python manage_migrations.py run --dry-run       # Simulate execution
  python manage_migrations.py info 01_basic_tables.sql  # Show migration info
  python manage_migrations.py list                # List all migration files
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # status 명령어
    subparsers.add_parser("status", help="Show migration status")

    # run 명령어
    run_parser = subparsers.add_parser("run", help="Run migrations")
    run_parser.add_argument(
        "--migration",
        type=str,
        help="Specific migration file to run (optional)"
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate execution without actual changes"
    )

    # info 명령어
    info_parser = subparsers.add_parser("info", help="Show migration info")
    info_parser.add_argument("migration", type=str, help="Migration file name")

    # list 명령어
    subparsers.add_parser("list", help="List all migration files")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # 명령어 실행
    commands = {
        "status": cmd_status,
        "run": cmd_run,
        "info": cmd_info,
        "list": cmd_list,
    }

    try:
        commands[args.command](args)
    except KeyError:
        logger.error(f"Unknown command: {args.command}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("\n⏸️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

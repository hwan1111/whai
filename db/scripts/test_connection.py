#!/usr/bin/env python3
"""Test Aiven database connections."""

import sys
from pathlib import Path

# Add db config to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.aiven import AivenConfig


def test_database(host: str, port: int, user: str, password: str, db_name: str, db_type: str):
    """Test connection to a specific database.

    Args:
        host: Database host
        port: Database port
        user: Database user
        password: Database password
        db_name: Database name
        db_type: Database type label (e.g., "Service", "Admin")

    Returns:
        True if successful, False otherwise
    """
    try:
        import mysql.connector
    except ImportError:
        return False

    print(f"\n🔍 Testing {db_type} database: {db_name}")

    try:
        conn = mysql.connector.connect(
            host=host, port=port, user=user, password=password, database=db_name
        )
        cursor = conn.cursor()

        # Get MySQL version
        cursor.execute("SELECT VERSION()")
        version = cursor.fetchone()
        print(f"   ✅ Connected! MySQL version: {version[0]}")

        # Get table count
        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = %s",
            (db_name,),
        )
        table_count = cursor.fetchone()
        print(f"   📊 Tables: {table_count[0]}")

        if table_count[0] > 0:
            cursor.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = %s",
                (db_name,),
            )
            tables = cursor.fetchall()
            for (table,) in tables[:5]:  # Show first 5 tables
                print(f"      - {table}")
            if len(tables) > 5:
                print(f"      ... and {len(tables) - 5} more")

        cursor.close()
        conn.close()
        return True

    except mysql.connector.Error as e:
        if "Unknown database" in str(e):
            print(f"   ⚠️  Database does not exist: {db_name}")
            print(f"      Run: python db/scripts/init_databases.py")
        else:
            print(f"   ❌ Connection failed: {e}")
        return False
    except Exception as e:
        print(f"   ❌ Unexpected error: {e}")
        return False


def test_all_connections():
    """Test all database connections."""
    config = AivenConfig()

    print("=" * 70)
    print("Aiven MySQL Connection Test")
    print("=" * 70)

    try:
        import mysql.connector
    except ImportError:
        print("\n⚠️  mysql-connector-python not installed. Installing...")
        import subprocess

        subprocess.run(
            ["pip", "install", "mysql-connector-python", "--break-system-packages"],
            check=True,
        )

    # Get connection credentials
    host, port = config.get_host_port()
    user, password = config.get_credentials()

    print(f"\n🔗 Host: {host}:{port}")
    print(f"📝 User: {user}\n")

    # Test service database
    service_db_name = config.get_database_name(config.service_db)
    service_ok = test_database(host, port, user, password, service_db_name, "Service")

    # Test admin database
    admin_db_name = config.get_database_name(config.admin_db)
    admin_ok = test_database(host, port, user, password, admin_db_name, "Admin")

    print("\n" + "=" * 70)
    if service_ok and admin_ok:
        print("✨ All connections successful!")
    else:
        print("⚠️  Some connections failed. Run init_databases.py to create databases.")
    print("=" * 70)

    return service_ok and admin_ok


if __name__ == "__main__":
    try:
        success = test_all_connections()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)
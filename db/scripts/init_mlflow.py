#!/usr/bin/env python3
"""Initialize MLflow backend database on Aiven."""

import sys
from pathlib import Path

# Add db config to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.aiven import AivenConfig


def init_mlflow_db():
    """Initialize MLflow backend database."""
    config = AivenConfig()

    print("=" * 60)
    print("MLflow Backend Database Initialization")
    print("=" * 60)
    print(f"\nConfiguration loaded:")
    print(f"  Main DB: {config.main_db_url.split('@')[1] if '@' in config.main_db_url else 'N/A'}")
    print(f"  MLflow Backend URI: {config.mlflow_db_url.split('@')[1] if '@' in config.mlflow_db_url else 'N/A'}")

    try:
        import mysql.connector
    except ImportError:
        print("\n⚠️  mysql-connector-python not installed")
        print("Installing dependencies...")
        import subprocess

        subprocess.run(
            ["pip", "install", "mysql-connector-python", "--break-system-packages"],
            check=True,
        )
        import mysql.connector

    # Parse connection details
    from urllib.parse import urlparse

    parsed = urlparse(config.main_db_url)
    host = parsed.hostname
    port = parsed.port or 3306
    user = parsed.username
    password = parsed.password

    print(f"\n🔗 Connecting to {host}:{port}...")

    try:
        # Connect to MySQL
        conn = mysql.connector.connect(
            host=host, port=port, user=user, password=password, ssl_disabled=False
        )
        cursor = conn.cursor()

        # Create mlflow_backend database
        print("📝 Creating mlflow_backend database...")
        cursor.execute("CREATE DATABASE IF NOT EXISTS mlflow_backend")
        print("✅ Database created")

        cursor.close()
        conn.close()

        print("\n" + "=" * 60)
        print("✨ MLflow initialization complete!")
        print("=" * 60)
        print("\n📌 Next steps:")
        print("  1. Add MLFLOW_BACKEND_STORE_URI to .env:")
        print(f"\n     MLFLOW_BACKEND_STORE_URI={config.mlflow_db_url}\n")
        print("  2. Run MLflow server:")
        print("\n     python script/run_mlflow.py\n")

    except mysql.connector.Error as e:
        print(f"\n❌ Database error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    init_mlflow_db()

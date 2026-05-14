#!/usr/bin/env python3
"""Run MLflow server with configuration from mlflow.yaml"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from urllib.parse import urlparse
import subprocess


def load_env():
    """Load environment from .env.local or .env"""
    env_local = Path(__file__).parent.parent / ".env.local"
    if env_local.exists():
        load_dotenv(env_local)


def test_db_connection(database_url: str, ca_path: str) -> bool:
    """Test database connection before starting MLflow."""
    try:
        import mysql.connector
    except ImportError:
        print("⚠️  mysql-connector-python not installed, skipping connection test")
        return True

    parsed = urlparse(database_url)
    try:
        conn = mysql.connector.connect(
            host=parsed.hostname,
            port=parsed.port or 3306,
            user=parsed.username,
            password=parsed.password,
            database=parsed.path.strip("/"),
            ssl_disabled=False,
            ssl_ca=os.path.expanduser(ca_path),
            autocommit=True
        )
        conn.close()
        print(f"   ✅ Database connection successful")
        return True
    except Exception as e:
        print(f"   ❌ Database connection failed: {e}")
        return False


def load_mlflow_config() -> dict:
    """Load MLflow configuration from mlflow.yaml"""
    config_path = Path(__file__).parent.parent / "config/mlflow.yaml"

    if not config_path.exists():
        raise FileNotFoundError(f"mlflow.yaml not found at {config_path}")

    import yaml
    with open(config_path) as f:
        config = yaml.safe_load(f)

    return config.get("server", {})


def run_mlflow_server(config: dict, mlflow_url: str, artifact_root: str) -> None:
    """Start MLflow server with the given configuration"""
    cmd = ["mlflow", "server"]

    # Build command arguments from config
    if "port" in config:
        cmd.extend(["--port", str(config["port"])])

    if "host" in config:
        cmd.extend(["--host", config["host"]])

    # Use database URL directly
    cmd.extend(["--backend-store-uri", mlflow_url])

    if artifact_root:
        cmd.extend(["--default-artifact-root", artifact_root])

    print(f"🚀 Starting MLflow server")
    print(f"   Port: {config.get('port')}")
    print(f"   Host: {config.get('host')}")
    print(f"   Backend: Aiven MySQL (mlflow)")
    print(f"   SSL CA: {os.getenv('CA_PATH')}\n")

    subprocess.run(cmd)


if __name__ == "__main__":
    load_env()
    
    mlflow_url = os.getenv("MLFLOW_DATABASE_URL")
    ca_path = os.getenv("CA_PATH", "./config/certs/ca.pem")
    artifact_root = os.getenv("MLFLOW_ARTIFACTS_BUCKET")
    
    if not mlflow_url:
        print("❌ MLFLOW_DATABASE_URL not set")
        sys.exit(1)

    print("🔗 Testing database connection...")
    if not test_db_connection(mlflow_url, ca_path):
        sys.exit(1)

    config = load_mlflow_config()
    run_mlflow_server(config, mlflow_url, artifact_root)
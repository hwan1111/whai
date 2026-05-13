#!/usr/bin/env python3
"""Run MLflow server with configuration from mlflow.yaml"""

import os
import subprocess
import yaml
from pathlib import Path
from dotenv import load_dotenv


def load_env():
    """Load environment from .env.local or .env"""
    env_local = Path(__file__).parent.parent / ".env.local"

    if env_local.exists():
        load_dotenv(env_local)


def expand_env_vars(value: str) -> str:
    """Expand environment variables in a string.

    Supports ${VAR} syntax.

    Args:
        value: String that may contain ${VAR} placeholders

    Returns:
        String with environment variables expanded
    """
    if not isinstance(value, str):
        return value

    import re

    # Replace ${VAR} with environment variable values
    def replace_var(match):
        var_name = match.group(1)
        return os.getenv(var_name, match.group(0))

    return re.sub(r'\$\{([^}]+)\}', replace_var, value)


def load_mlflow_config() -> dict:
    """Load MLflow configuration from mlflow.yaml"""
    config_path = Path(__file__).parent.parent / "config/mlflow.yaml"

    if not config_path.exists():
        raise FileNotFoundError(f"mlflow.yaml not found at {config_path}")

    with open(config_path) as f:
        config = yaml.safe_load(f)

    return config.get("server", {})


def run_mlflow_server(config: dict) -> None:
    """Start MLflow server with the given configuration"""
    cmd = ["mlflow", "server"]

    # Build command arguments from config
    if "port" in config:
        cmd.extend(["--port", str(config["port"])])

    if "host" in config:
        cmd.extend(["--host", config["host"]])

    if "backend_store_uri" in config:
        backend_uri = expand_env_vars(config["backend_store_uri"])
        cmd.extend(["--backend-store-uri", backend_uri])

    if "default_artifact_root" in config:
        artifact_root = expand_env_vars(config["default_artifact_root"])
        cmd.extend(["--default-artifact-root", artifact_root])

    print(f"🚀 Starting MLflow server")
    print(f"   Port: {config.get('port')}")
    print(f"   Host: {config.get('host')}")
    print(f"   Backend: Aiven MySQL (mlflow)\n")

    subprocess.run(cmd)


if __name__ == "__main__":
    load_env()
    config = load_mlflow_config()
    run_mlflow_server(config)

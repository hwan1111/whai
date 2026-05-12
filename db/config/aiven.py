"""Aiven database connection configuration."""

import os
from urllib.parse import urlparse, urlunparse
from dotenv import load_dotenv


class AivenConfig:
    """Aiven database configuration manager."""

    def __init__(self):
        """Initialize with environment variables."""
        # Load .env files
        env_local = ".env.local"
        env_file = ".env"

        if os.path.exists(env_local):
            load_dotenv(env_local)
        elif os.path.exists(env_file):
            load_dotenv(env_file)

        self.service_db_url = os.getenv("DATABASE_URL")
        self.admin_db_url = os.getenv("ADMIN_DATABASE_URL")
        self.mlflow_backend_uri = os.getenv("MLFLOW_BACKEND_STORE_URI")

    @property
    def service_db(self) -> str:
        """Get service database URL (applications data)."""
        if not self.service_db_url:
            raise ValueError("DATABASE_URL not set in .env")
        return self.service_db_url

    @property
    def admin_db(self) -> str:
        """Get admin database URL (MLflow, logging, monitoring)."""
        if not self.admin_db_url:
            raise ValueError("ADMIN_DATABASE_URL not set in .env")
        return self.admin_db_url

    @property
    def mlflow_db_url(self) -> str:
        """Get MLflow backend store URI.

        Returns admin_db if MLFLOW_BACKEND_STORE_URI is set, otherwise uses admin_db.
        """
        if self.mlflow_backend_uri:
            return self.mlflow_backend_uri
        return self.admin_db

    def get_host_port(self, db_url: str = None) -> tuple[str, int]:
        """Extract host and port from database URL.

        Args:
            db_url: Database URL (default: service_db)

        Returns:
            Tuple of (host, port)
        """
        if db_url is None:
            db_url = self.service_db

        parsed = urlparse(db_url)
        host = parsed.hostname
        port = parsed.port or 3306
        return host, port

    def get_credentials(self, db_url: str = None) -> tuple[str, str]:
        """Extract username and password from database URL.

        Args:
            db_url: Database URL (default: service_db)

        Returns:
            Tuple of (username, password)
        """
        if db_url is None:
            db_url = self.service_db

        parsed = urlparse(db_url)
        return parsed.username, parsed.password

    def get_database_name(self, db_url: str) -> str:
        """Extract database name from URL."""
        parsed = urlparse(db_url)
        return parsed.path.strip("/")

    def __repr__(self) -> str:
        """String representation."""
        try:
            service_db_name = self.get_database_name(self.service_db)
            admin_db_name = self.get_database_name(self.admin_db)
            return (
                f"<AivenConfig "
                f"service_db={service_db_name} "
                f"admin_db={admin_db_name}>"
            )
        except:
            return "<AivenConfig (unconfigured)>"

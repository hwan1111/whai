from pathlib import Path
from urllib.parse import urlparse
from dotenv import dotenv_values


class AivenConfig:
    def __init__(self) -> None:
        env = dotenv_values(Path(__file__).resolve().parents[1] / ".env")
        self.service_db: str = env.get("SERVICE_DATABASE_URL", "")
        self.admin_db: str = env.get("MLFLOW_DATABASE_URL", "")
        self._parsed = urlparse(self.service_db)

    def get_host_port(self) -> tuple[str, int]:
        return self._parsed.hostname or "", self._parsed.port or 3306

    def get_credentials(self) -> tuple[str, str]:
        return self._parsed.username or "", self._parsed.password or ""

    def get_database_name(self, db_url: str) -> str:
        return urlparse(db_url).path.lstrip("/")

"""
correlation_insight 테이블 생성 스크립트

실행:
    python script/others/create_correlation_insight_table.py
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env", override=True)
sys.stdout.reconfigure(encoding="utf-8")

CA_PATH = str(ROOT / "config" / "certs" / "ca.pem")


def get_engine():
    raw_url = os.environ["SERVICE_DATABASE_URL"]
    if "ssl_ca=" in raw_url:
        base_url = raw_url.split("?")[0]
        url = f"{base_url}?charset=utf8mb4"
        connect_args = {"ssl": {"ca": CA_PATH}}
    else:
        url = raw_url
        connect_args = {}
    return create_engine(url, connect_args=connect_args, pool_pre_ping=True)


CREATE_SQL = """
CREATE TABLE IF NOT EXISTS correlation_insight (
    id          BIGINT UNSIGNED  AUTO_INCREMENT PRIMARY KEY,
    pair_key    VARCHAR(50)      NOT NULL,
    date        DATE             NOT NULL,
    description TEXT             NOT NULL,
    created_at  DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_corr_insight_pair_date (pair_key, date),
    INDEX idx_corr_insight_date (date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""


def main():
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(CREATE_SQL))
    print("correlation_insight 테이블 생성 완료 (이미 존재하면 스킵)")


if __name__ == "__main__":
    main()

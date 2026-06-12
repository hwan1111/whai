"""
model_config 테이블 생성 스크립트

역할:
  drift 감지 시 재학습 DAG가 특정 종목을 force_priority_2 로 전환할 때 기록.
  예측 DAG가 매일 이 테이블을 읽어 강제 전환 여부를 확인한다.

실행:
    python script/others/create_model_config_table.py
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
CREATE TABLE IF NOT EXISTS model_config (
    ticker          VARCHAR(20)  NOT NULL PRIMARY KEY,

    -- NULL = 정상 운영 (1순위 사용), 'priority_2' = 강제 2순위 전환
    force_priority  VARCHAR(20),

    -- 강제 전환 사유 (drift MAPE 값, PatchTST 여부 등)
    reason          TEXT,

    -- 재학습 방법 ('sklearn' | 'patchtst' | NULL)
    retrain_type    VARCHAR(20),

    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                             ON UPDATE CURRENT_TIMESTAMP
)
ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;
"""


def main():
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(CREATE_SQL))
    print("model_config 테이블 생성 완료 (이미 존재하면 스킵)")


if __name__ == "__main__":
    main()

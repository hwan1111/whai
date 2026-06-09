"""
prediction 테이블 생성 스크립트

실행:
    python script/create_prediction_table.py
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env.local", override=True)
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
CREATE TABLE IF NOT EXISTS prediction (
    id              BIGINT          AUTO_INCREMENT PRIMARY KEY,

    -- 종목 정보
    ticker          VARCHAR(20)     NOT NULL,

    -- 날짜
    date            DATE            NOT NULL,   -- 예측 실행일 (오늘)
    target_date     DATE            NOT NULL,   -- 예측 대상일 (D+5 거래일)

    -- 사용 모델 정보
    model_used      VARCHAR(20)     NOT NULL,   -- 'priority_1' | 'priority_2'
    model_name      VARCHAR(50)     NOT NULL,   -- 'ARIMA' | 'Prophet' | 'PatchTST' 등
    model_source    VARCHAR(10)     NOT NULL,   -- 'Choi' | 'SU'

    -- 예측값
    base_price      DECIMAL(18,4)   NOT NULL,   -- 예측 기준 종가 (오늘 종가)
    pred_price_d5   DECIMAL(18,4)   NOT NULL,   -- D+5 예측 종가
    pred_return_d5  DECIMAL(10,6)   NOT NULL,   -- D+5 예측 로그 수익률

    -- 신뢰구간 (CI)
    ci_pct          DECIMAL(4,2)    NOT NULL DEFAULT 0.80,
    ci_upper_d5     DECIMAL(18,4)   NOT NULL,   -- D+5 CI 상단
    ci_lower_d5     DECIMAL(18,4)   NOT NULL,   -- D+5 CI 하단
    vol_20d         DECIMAL(10,6)   NOT NULL,   -- CI 계산에 사용한 rolling 20일 변동성

    -- 드리프트 감지
    drift_detected  TINYINT(1)      NOT NULL DEFAULT 0,
    rolling_mape    DECIMAL(8,4),               -- rolling 20거래일 MAPE (이력 부족 시 NULL)
    threshold       DECIMAL(8,4)    NOT NULL,   -- baseline_mape x 1.5
    retrain_needed  TINYINT(1)      NOT NULL DEFAULT 0,

    -- Choi 전체 예측 (프론트 차트용, SU 채택 시 NULL)
    -- forecast 배열: [{horizon, date, price, ci_upper, ci_lower}, ...]
    -- Choi = 20개, SU = 5개 (D+5 롤링 방식)
    forecast_json   JSON,

    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_ticker_date (ticker, date),
    INDEX idx_ticker_target (ticker, target_date),
    INDEX idx_date (date)
)
ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;
"""


def main():
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(CREATE_SQL))
    print("prediction 테이블 생성 완료 (이미 존재하면 스킵)")


if __name__ == "__main__":
    main()

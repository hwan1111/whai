"""user 테이블 생성 스크립트. 최초 1회만 실행."""
import os
import pymysql
from dotenv import load_dotenv

load_dotenv(".env.local")

conn = pymysql.connect(
    host=os.getenv("MYSQL_HOST"),
    port=int(os.getenv("MYSQL_PORT", 3306)),
    user=os.getenv("MYSQL_USER"),
    password=os.getenv("MYSQL_PASSWORD"),
    database=os.getenv("MYSQL_DATABASE"),
    charset="utf8mb4",
)

DDL = """
CREATE TABLE IF NOT EXISTS user (
    user_id      VARCHAR(50)  NOT NULL PRIMARY KEY,
    name         VARCHAR(100) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    birth_year   SMALLINT,
    gender       ENUM('M', 'F', 'OTHER'),
    portfolio    TEXT,
    created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

with conn.cursor() as cur:
    cur.execute(DDL)
conn.commit()
conn.close()
print("user 테이블 생성 완료")

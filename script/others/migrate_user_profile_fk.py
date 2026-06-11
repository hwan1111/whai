"""user_profile.user_id BIGINT → VARCHAR(20), FK to member. 최초 1회만 실행."""
from pathlib import Path
from urllib.parse import urlparse
import pymysql
from dotenv import load_dotenv, dotenv_values

env = dotenv_values(Path(__file__).resolve().parents[1] / ".env")
url = env.get("DATABASE_URL") or env.get("ADMIN_DATABASE_URL")
if not url:
    raise SystemExit("DATABASE_URL이 .env에 없습니다.")

parsed = urlparse(url)
conn = pymysql.connect(
    host=parsed.hostname,
    port=parsed.port or 3306,
    user=parsed.username,
    password=parsed.password,
    database="whai",
    charset="utf8mb4",
    ssl={"ca": str(Path(__file__).resolve().parents[1] / "config" / "certs" / "ca.pem")},
)

with conn.cursor() as cur:
    cur.execute("ALTER TABLE user_profile MODIFY COLUMN user_id VARCHAR(20) NOT NULL;")
    cur.execute("""
        ALTER TABLE user_profile
        ADD CONSTRAINT fk_user_profile_member
        FOREIGN KEY (user_id) REFERENCES member(user_id)
        ON DELETE CASCADE ON UPDATE CASCADE;
    """)

conn.commit()
conn.close()
print("user_profile FK 마이그레이션 완료")

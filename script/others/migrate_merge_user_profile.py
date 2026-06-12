"""user_profile 컬럼을 user 테이블로 합병. 최초 1회만 실행."""
import re
import sys
from pathlib import Path

import pymysql
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
env = dotenv_values(ROOT / ".env")
db_url = env.get("SERVICE_DATABASE_URL")
if not db_url:
    raise SystemExit("SERVICE_DATABASE_URL이 .env에 없습니다.")

match = re.match(r"mysql\+pymysql://([^:]+):([^@]+)@([^:]+):(\d+)/([^/?]+)", db_url)
if not match:
    raise SystemExit("SERVICE_DATABASE_URL 형식이 올바르지 않습니다.")

conn = pymysql.connect(
    host=match.group(3),
    port=int(match.group(4)),
    user=match.group(1),
    password=match.group(2),
    database=match.group(5),
    charset="utf8mb4",
    ssl={"ca": str(ROOT / "config" / "certs" / "ca.pem")},
)

NEW_COLUMNS = [
    ("age_group",         "VARCHAR(50)  NULL AFTER `gender`"),
    ("invest_type",       "VARCHAR(10)  NULL AFTER `age_group`"),
    ("profile_image_url", "VARCHAR(500) NULL AFTER `invest_type`"),
    ("original_file_name","VARCHAR(255) NULL AFTER `profile_image_url`"),
    ("updated_at",        "DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP AFTER `created_at`"),
]


def get_existing_columns(cur, table: str) -> set:
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = %s",
        (table,),
    )
    return {row[0] for row in cur.fetchall()}


def table_exists(cur, table: str) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = DATABASE() AND table_name = %s",
        (table,),
    )
    return cur.fetchone()[0] > 0


try:
    with conn:
        with conn.cursor() as cur:
            # 1. user 테이블에 없는 컬럼만 추가
            existing = get_existing_columns(cur, "user")
            to_add = [(col, defn) for col, defn in NEW_COLUMNS if col not in existing]

            if to_add:
                clauses = ", ".join(f"ADD COLUMN `{col}` {defn}" for col, defn in to_add)
                print(f"⏳ user 테이블에 컬럼 추가 ({', '.join(c for c, _ in to_add)})...")
                cur.execute(f"ALTER TABLE `user` {clauses}")
                conn.commit()
                print("✅ 컬럼 추가 완료")
            else:
                print("⏭️  user 컬럼 추가 건너뜀 (이미 존재)")

            # 2. user_profile → user 데이터 이관
            if table_exists(cur, "user_profile"):
                print("⏳ user_profile → user 데이터 이관...")
                cur.execute("""
                    UPDATE `user` u
                    JOIN `user_profile` up ON u.user_id = up.user_id
                    SET
                        u.age_group          = up.age_group,
                        u.invest_type        = up.invest_type,
                        u.profile_image_url  = up.profile_image_url,
                        u.original_file_name = up.original_file_name,
                        u.updated_at         = up.updated_at
                """)
                conn.commit()
                print("✅ 데이터 이관 완료")

                # 3. user_profile 삭제
                print("⏳ user_profile 테이블 삭제...")
                cur.execute("DROP TABLE `user_profile`")
                conn.commit()
                print("✅ user_profile 삭제 완료")
            else:
                print("⏭️  user_profile 없음 — 이관/삭제 건너뜀")

    print("\n✅ 마이그레이션 완료")
except Exception as e:
    print(f"\n❌ 마이그레이션 실패: {e}", file=sys.stderr)
    sys.exit(1)

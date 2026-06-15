import os, sys, pymysql
sys.stdout.reconfigure(encoding="utf-8")
from dotenv import load_dotenv
load_dotenv(".env", override=True)

conn = pymysql.connect(
    host="mysql-12676458-whai.b.aivencloud.com", port=16935, db="whai_service",
    user=os.environ["BACKEND_DB_USER"], password=os.environ["BACKEND_DB_PASSWORD"],
    charset="utf8mb4", ssl={"ca": "config/certs/ca.pem"},
    cursorclass=pymysql.cursors.DictCursor,
)
with conn.cursor() as cur:
    cur.execute("SELECT COUNT(*) as cnt FROM regime WHERE ticker = '000000'")
    print("전체 KOSPI 국면:", cur.fetchone()["cnt"])

    cur.execute("""
        SELECT COUNT(*) as cnt FROM regime r
        LEFT JOIN regime_summary rs ON r.id = rs.regime_pk
        WHERE r.ticker = '000000' AND rs.regime_pk IS NULL
    """)
    print("regime_summary 없는 국면:", cur.fetchone()["cnt"])

    cur.execute("""
        SELECT COUNT(*) as cnt FROM regime r
        JOIN regime_summary rs ON r.id = rs.regime_pk
        WHERE r.ticker = '000000' AND (rs.cause IS NULL OR rs.cause = '')
    """)
    print("cause 비어있는 국면:", cur.fetchone()["cnt"])
conn.close()

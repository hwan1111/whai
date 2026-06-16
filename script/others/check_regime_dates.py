import os
import pymysql
from urllib.parse import urlparse
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parents[2] / ".env")
raw = os.environ["SERVICE_DATABASE_URL"]
url = urlparse(raw.replace("mysql+pymysql://", "mysql://").split("?")[0])
conn = pymysql.connect(
    host=url.hostname, port=url.port or 3306, db=url.path.lstrip("/"),
    user=url.username, password=url.password, charset="utf8mb4",
    ssl={"ca": str(Path(__file__).parents[2] / "config" / "certs" / "ca.pem")},
    cursorclass=pymysql.cursors.DictCursor, autocommit=True,
)
with conn.cursor() as cur:
    cur.execute("SELECT ticker, MIN(start_date) min_d, MAX(end_date) max_d, COUNT(*) cnt FROM regime GROUP BY ticker ORDER BY ticker")
    for r in cur.fetchall():
        print(f"{r['ticker']:>8}  {r['min_d']} ~ {r['max_d']}  ({r['cnt']}건)")
conn.close()

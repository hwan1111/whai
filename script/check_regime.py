"""
Usage:
    python script/check_regime.py --ticker 055550
    python script/check_regime.py --ticker 055550 --limit 30
"""
import argparse, os, pymysql
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env.local", override=True)

parser = argparse.ArgumentParser()
parser.add_argument("--ticker", required=True)
parser.add_argument("--limit", type=int, default=20)
args = parser.parse_args()

conn = pymysql.connect(
    host="mysql-12676458-whai.b.aivencloud.com", port=16935,
    db="whai_service",
    user=os.environ["BACKEND_DB_USER"], password=os.environ["BACKEND_DB_PASSWORD"],
    charset="utf8mb4", ssl={"ca": str(Path("config/certs/ca.pem"))},
    cursorclass=pymysql.cursors.DictCursor,
)
with conn.cursor() as cur:
    cur.execute(
        "SELECT regime_id, start_date, end_date, days, direction "
        "FROM regime WHERE ticker=%s ORDER BY start_date DESC LIMIT %s",
        (args.ticker, args.limit),
    )
    rows = cur.fetchall()

print(f"{'id':>5}  {'start':>12}  {'end':>12}  {'days':>5}  direction")
print("-" * 55)
for r in reversed(rows):
    print(f"{r['regime_id']:>5}  {str(r['start_date']):>12}  {str(r['end_date']):>12}  {r['days']:>5}  {r['direction']}")

conn.close()

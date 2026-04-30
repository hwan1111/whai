import argparse
import json
from pathlib import Path

from src.db_client import MySQLClient
from src.pykrx_client import get_price_data

CONFIG_FILE = Path(__file__).resolve().parents[1] / "config" / "krx_sector_top3.json"


def load_sector_list(config_path: Path) -> list[dict[str, str]]:
    """JSON 파일에서 ticker 리스트와 섹터 정보를 로드한다."""
    with config_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    sectors = []
    for sector in data.get("sectors", []):
        sector_name = sector.get("name")
        for company in sector.get("top", []):
            ticker = company.get("code", "").strip()
            if not ticker:
                continue
            sectors.append(
                {
                    "ticker": ticker,
                    "name": company.get("name", ""),
                    "sector": sector_name,
                    "currency_code": "KRW",
                }
            )

    return sectors


def insert_company(client: MySQLClient, company: dict[str, str]) -> int:
    """company 테이블에 upsert 처리."""
    query = (
        "REPLACE INTO company (ticker, name, sector, currency_code) "
        "VALUES (:ticker, :name, :sector, :currency_code)"
    )
    return client.execute_update(query, company)


def insert_prices(client: MySQLClient, ticker: str, data: list[dict]) -> int:
    """price 테이블에 행 단위로 upsert 처리."""
    if not data:
        return 0

    query = (
        "REPLACE INTO price (ticker, date, close, volume) "
        "VALUES (:ticker, :date, :close, :volume)"
    )
    return client.execute_update(query, data)


def build_price_rows(df) -> list[dict]:
    return [
        {
            "ticker": row["ticker"],
            "date": row["date"].isoformat() if hasattr(row["date"], "isoformat") else row["date"],
            "close": float(row["close"]),
            "volume": int(row["volume"]),
        }
        for _, row in df.iterrows()
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="KRX 섹터 top3 종목을 JSON에서 읽어와 company/price 테이블에 적재합니다."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="DB에 쓰지 않고 어떤 종목을 처리할지 확인합니다.",
    )
    parser.add_argument(
        "--start-date",
        default="20200101",
        help="가져올 데이터 시작일 (YYYYMMDD). 기본값 20200101",
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="가져올 데이터 종료일 (YYYYMMDD). 기본값 오늘",
    )
    args = parser.parse_args()

    sector_list = load_sector_list(CONFIG_FILE)
    if not sector_list:
        raise SystemExit("JSON에서 유효한 종목을 읽어오지 못했습니다.")

    client = MySQLClient()
    try:
        if not client.test_connection():
            raise SystemExit("MySQL 서버에 연결할 수 없습니다.")

        print(f"총 {len(sector_list)}개 종목을 처리합니다.")

        for company in sector_list:
            ticker = company["ticker"]
            print(f"\n[{ticker}] {company['name']} / {company['sector']}")
            if args.dry_run:
                continue

            insert_company(client, company)
            try:
                df = get_price_data(ticker, start_date=args.start_date, end_date=args.end_date)
                rows = build_price_rows(df)
                inserted = insert_prices(client, ticker, rows)
                print(f"  price rows: {len(rows)} -> inserted/upserted {inserted}")
            except Exception as exc:
                print(f"  ⚠️ {ticker} 처리 중 오류 발생: {exc}")
                continue

    finally:
        client.close()


if __name__ == "__main__":
    main()

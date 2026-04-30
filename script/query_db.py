"""MySQL 데이터베이스 조회 및 관리 스크립트."""

from src.db_client import MySQLClient
import argparse
import sys


def show_tables(client: MySQLClient):
    """모든 테이블 조회."""
    result = client.execute_query("SHOW TABLES")
    print("=== 데이터베이스 테이블 ===")
    for row in result:
        table_name = list(row.values())[0]
        print(f"  - {table_name}")
    return result


def show_table_schema(client: MySQLClient, table_name: str):
    """테이블 스키마 조회."""
    result = client.execute_query(f"DESCRIBE {table_name}")
    print(f"\n=== {table_name} 테이블 구조 ===")
    for row in result:
        print(f"  {row}")
    return result


def show_table_count(client: MySQLClient, table_name: str):
    """테이블 행 개수 조회."""
    result = client.execute_query(f"SELECT COUNT(*) as count FROM {table_name}")
    count = result[0]["count"]
    print(f"\n=== {table_name} 테이블 행 개수 ===")
    print(f"  {count} rows")
    return count


def show_table_data(client: MySQLClient, table_name: str, limit: int = 10):
    """테이블 데이터 조회."""
    result = client.execute_query(f"SELECT * FROM {table_name} LIMIT {limit}")
    print(f"\n=== {table_name} 테이블 데이터 (상위 {limit}개) ===")
    if result:
        # 헤더 출력
        headers = list(result[0].keys())
        print(f"  {' | '.join(headers)}")
        print(f"  {'-' * 80}")
        # 데이터 출력
        for row in result:
            print(f"  {' | '.join(str(v) for v in row.values())}")
    else:
        print("  (데이터 없음)")
    return result


def show_company_price_data(client: MySQLClient, ticker: str, limit: int = 20, output_csv: str | None = None):
    """회사 정보와 종가/거래량 데이터를 CSV 형태로 보여준다."""
    company_query = "SELECT * FROM company WHERE ticker = :ticker"
    price_query = (
        "SELECT * FROM price WHERE ticker = :ticker ORDER BY date DESC LIMIT :limit"
    )

    company = client.execute_query(company_query, {"ticker": ticker})
    prices = client.execute_query(price_query, {"ticker": ticker, "limit": limit})

    print(f"\n=== company 테이블 조회: ticker={ticker} ===")
    if company:
        for row in company:
            print(row)
    else:
        print("  회사 정보가 없습니다.")

    print(f"\n=== price 테이블 조회: ticker={ticker} (최대 {limit}개) ===")
    if prices:
        headers = list(prices[0].keys())
        print(f"  {' , '.join(headers)}")
        for row in prices:
            print(f"  {' , '.join(str(row[h]) for h in headers)}")
    else:
        print("  가격 데이터가 없습니다.")

    if output_csv and prices:
        import csv

        with open(output_csv, "w", newline='', encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=headers)
            writer.writeheader()
            writer.writerows(prices)
        print(f"\n✅ CSV로 저장되었습니다: {output_csv}")

    return company, prices


def show_database_info(client: MySQLClient):
    """데이터베이스 정보 조회."""
    result = client.execute_query("SELECT DATABASE() as current_db, VERSION() as mysql_version")
    print("=== 데이터베이스 정보 ===")
    for key, value in result[0].items():
        print(f"  {key}: {value}")
    return result


def main():
    """메인 함수."""
    parser = argparse.ArgumentParser(description="MySQL DB 조회 및 회사별 가격 데이터 테스트")
    parser.add_argument("--ticker", help="조회할 회사 ticker", default=None)
    parser.add_argument("--limit", help="조회할 price 행 수", type=int, default=20)
    parser.add_argument("--csv", help="CSV로 저장할 파일 경로", default=None)
    args = parser.parse_args()

    client = MySQLClient()
    
    try:
        # 데이터베이스 연결 확인
        if not client.test_connection():
            print("❌ MySQL 서버에 연결할 수 없습니다")
            sys.exit(1)
        
        print("✅ MySQL 서버 연결 성공\n")
        
        # 회사별 조회 모드
        if args.ticker:
            show_company_price_data(client, args.ticker, limit=args.limit, output_csv=args.csv)
            return
        
        # 기본 정보 조회
        show_database_info(client)
        
        # 테이블 목록 조회
        tables = show_tables(client)
        
        if tables:
            # 각 테이블 정보 조회
            table_names = [list(row.values())[0] for row in tables]
            for table_name in table_names:
                print(f"\n{'=' * 80}")
                show_table_schema(client, table_name)
                show_table_count(client, table_name)
                show_table_data(client, table_name, limit=5)
        else:
            print("\n❌ 테이블이 없습니다. 스키마를 먼저 생성하세요.")
    
    except Exception as e:
        print(f"❌ 오류: {e}")
        sys.exit(1)
    
    finally:
        client.close()
        print(f"\n{'=' * 80}")
        print("✅ 연결 종료")


if __name__ == "__main__":
    main()

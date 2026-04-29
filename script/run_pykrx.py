from src.pykrx_client import get_price_data

ticker = input("종목코드 입력: ")
df = get_price_data(ticker)

print(df)
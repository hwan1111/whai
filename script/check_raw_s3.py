import boto3, sys
sys.stdout.reconfigure(encoding="utf-8")
from dotenv import load_dotenv
load_dotenv(".env", override=True)
s3 = boto3.client("s3")

prefixes = [
    "raw/005930", "raw/000660", "raw/005380", "raw/000270",
    "raw/079550", "raw/012450", "raw/105560", "raw/055550",
    "raw/051910", "raw/096770",
    "raw/USD", "raw/USD_KRW", "raw/KOSPI200",
]

print(f"{'prefix':<22} {'파일수':>6}  {'첫날':<12} {'마지막날':<12}")
print("-" * 58)
for prefix in prefixes:
    pag = s3.get_paginator("list_objects_v2")
    keys = []
    for page in pag.paginate(Bucket="fisa-news-archive", Prefix=prefix):
        keys.extend(obj["Key"] for obj in page.get("Contents", []))
    if keys:
        keys.sort()
        first = keys[0].split("/")[-1][:10]
        last  = keys[-1].split("/")[-1][:10]
        print(f"{prefix:<22} {len(keys):>6}  {first:<12} {last:<12}")
    else:
        print(f"{prefix:<22}   없음")

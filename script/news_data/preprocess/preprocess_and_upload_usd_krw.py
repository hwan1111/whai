import os
import re
import glob
import json
import boto3
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed

load_dotenv('.env')

s3 = boto3.client('s3')
BUCKET_NAME = 'fisa-news-archive'
LOCAL_DIR = 'data/news/원달러_USD_KRW'
TICKER = 'USD_KRW'


def clean_financial_news(text: str) -> str:
    if not text:
        return ""

    text = re.sub(r"(<저작권자|▶|ⓒ).*$", "", text, flags=re.MULTILINE | re.DOTALL)
    text = re.sub(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", "", text)

    text = re.sub(r"\[머니투데이.*?\]", "", text)
    text = re.sub(r"\(.*?\=연합뉴스\)", "", text)
    text = re.sub(r"사진\s*=\s*\S+", "", text)
    text = re.sub(r"사진제공\s*=\s*\S+", "", text)

    text = re.sub(r"[^\w\s.,%+\-가-힣]", " ", text)

    text = re.sub(r" +", " ", text)
    text = re.sub(r"\n+", "\n", text)

    return text.strip()


json_files = glob.glob(f"{LOCAL_DIR}/**/*.json", recursive=True) + glob.glob(f"{LOCAL_DIR}/*.json")
json_files = list(set(json_files))
total_files = len(json_files)

print(f"[시작] 총 {total_files}개의 USD_KRW 뉴스 파일을 찾았습니다.")
print(f"[{BUCKET_NAME}] 버킷의 preprocessed/{TICKER}/ 경로로 업로드를 시작합니다...\n")


def preprocess_and_upload(filepath):
    filename = os.path.basename(filepath)
    year = filename[:4]
    month = filename[5:7]
    s3_key = f"preprocessed/{TICKER}/{year}/{month}/{filename}"

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    fulltext = data.get('fulltext', '')
    cleaned = clean_financial_news(fulltext)

    data['fulltext'] = cleaned
    data['fulltext_length'] = len(cleaned)

    body = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')

    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=s3_key,
        Body=body,
        ContentType='application/json; charset=utf-8'
    )
    return True


success_count = 0
with ThreadPoolExecutor(max_workers=10) as executor:
    futures = [executor.submit(preprocess_and_upload, fp) for fp in json_files]

    for idx, future in enumerate(as_completed(futures), 1):
        try:
            future.result()
            success_count += 1
            if idx % 500 == 0 or idx == total_files:
                print(f"진행 상황: {idx} / {total_files} 완료...")
        except Exception as e:
            print(f"오류: {e}")

print(f"\n[완료] USD_KRW S3 preprocessed 업로드 완료! (성공: {success_count}/{total_files}개)")

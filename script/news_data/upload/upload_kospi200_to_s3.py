import os
import glob
import json
import boto3
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed

# 1. 환경변수 로드 (.env)
load_dotenv('.env')

# 2. S3 클라이언트 및 버킷 설정
s3 = boto3.client('s3')
BUCKET_NAME = 'fisa-news-archive'
DATA_DIR = 'data/news'
TARGET_FOLDERS = [
    "코스피200_KOSPI200"
]

json_files = []
for folder in TARGET_FOLDERS:
    folder_path = os.path.join(DATA_DIR, folder)
    json_files.extend(glob.glob(f"{folder_path}/**/*.json", recursive=True))

total_files = len(json_files)

print(f"[시작] 총 {total_files}개의 KOSPI200 뉴스 파일을 찾았습니다.")
print(f"[{BUCKET_NAME}] 버킷의 raw 경로로 병렬 업로드를 시작합니다...\n")

def upload_file_to_s3(filepath):
    filename = os.path.basename(filepath)
    folder_name = os.path.basename(os.path.dirname(filepath))
    ticker = folder_name.split('_')[-1] # KOSPI200
    
    year = filename[:4]
    month = filename[5:7]

    # S3 경로 규격: raw/KOSPI200/{year}/{month}/{filename}
    s3_key = f"raw/{ticker}/{year}/{month}/{filename}"

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    fulltext = data.get('fulltext')
    data['fulltext_length'] = len(fulltext) if fulltext else 0

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
    futures = [executor.submit(upload_file_to_s3, fp) for fp in json_files]
    
    for idx, future in enumerate(as_completed(futures), 1):
        try:
            future.result()
            success_count += 1
            if idx % 500 == 0 or idx == total_files:
                print(f"진행 상황: {idx} / {total_files} 업로드 완료...")
        except Exception as e:
            print(f"업로드 오류 발생: {e}")

print(f"\n[완료] KOSPI200 S3 raw 업로드 완료! (성공: {success_count}/{total_files}개)")

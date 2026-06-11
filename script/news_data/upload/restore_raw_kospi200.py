import os
import json
import boto3
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed

load_dotenv('.env')
s3 = boto3.client('s3')

BUCKET_NAME = 'fisa-news-archive'
S3_PREFIX = 'raw/KOSPI200/'
LOCAL_DIR = 'data/news/코스피200_KOSPI200'

def restore_file(s3_key):
    try:
        filename = os.path.basename(s3_key)
        local_path = os.path.join(LOCAL_DIR, filename)
        
        # S3에서 파일 다운로드
        response = s3.get_object(Bucket=BUCKET_NAME, Key=s3_key)
        content = response['Body'].read().decode('utf-8')
        
        # 파일 저장
        with open(local_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    except Exception as e:
        print(f"오류 ({s3_key}): {e}")
        return False

def main():
    os.makedirs(LOCAL_DIR, exist_ok=True)
    print(f"[시작] S3의 {S3_PREFIX} 경로에서 원본 raw 파일을 목록화하는 중...")
    
    paginator = s3.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=BUCKET_NAME, Prefix=S3_PREFIX)
    
    s3_keys = []
    for page in pages:
        if 'Contents' in page:
            for obj in page['Contents']:
                if obj['Key'].endswith('.json'):
                    s3_keys.append(obj['Key'])
                    
    total = len(s3_keys)
    print(f"다운로드할 원본 파일 개수: {total}개")
    
    success = 0
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(restore_file, key) for key in s3_keys]
        for idx, future in enumerate(as_completed(futures), 1):
            if future.result():
                success += 1
            if idx % 500 == 0 or idx == total:
                print(f"복원 진행률: {idx} / {total} 완료...")
                
    print(f"[완료] 로컬 raw 파일 복원 완료! (성공: {success}/{total}개)")

if __name__ == '__main__':
    main()

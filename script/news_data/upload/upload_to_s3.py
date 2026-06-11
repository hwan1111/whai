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
# 3. 명시된 10개 종목 폴더에서만 JSON 파일 찾기
TARGET_FOLDERS = [
    "기아_000270",
    "삼성전자_005930",
    "신한지주_055550",
    "한화에어로스페이스_012450",
    "현대차_005380",
    "KB금융_105560",
    "LG화학_051910",
    "LIG디펜스앤에어로스페이스_079550",
    "SK이노베이션_096770",
    "SK하이닉스_000660"
]

json_files = []
for folder in TARGET_FOLDERS:
    folder_path = os.path.join(DATA_DIR, folder)
    # 해당 종목 폴더 안의 json 파일만 수집
    json_files.extend(glob.glob(f"{folder_path}/**/*.json", recursive=True))

total_files = len(json_files)

print(f"[시작] 총 {total_files}개의 뉴스 파일을 찾았습니다.")
print(f"[{BUCKET_NAME}] 버킷으로 병렬 업로드를 시작합니다...\n")

# 4. 단일 파일 업로드 함수
def upload_file_to_s3(filepath):
    # 로컬 경로 예: data/news/삼성전자_005930/2020-01-01.json

    # 파일명 추출 (예: 2020-01-01.json)
    filename = os.path.basename(filepath)

    # 상위 폴더명 추출 (예: 삼성전자_005930)
    folder_name = os.path.basename(os.path.dirname(filepath))

    # 티커 추출 (예: 005930)
    ticker = folder_name.split('_')[-1]

    # 연도와 월 추출
    year = filename[:4]
    month = filename[5:7]

    # 팀 규칙에 맞춘 최종 S3 경로 생성
    # 규칙: raw/{ticker}/{year}/{month}/{filename}
    s3_key = f"raw/{ticker}/{year}/{month}/{filename}"

    # JSON 읽기 → fulltext_length 필드 추가 → S3에 업로드
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    fulltext = data.get('fulltext')  # None 또는 문자열
    data['fulltext_length'] = len(fulltext) if fulltext else 0

    body = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')

    # put_object로 수정된 내용을 직접 업로드 (로컬 파일은 변경하지 않음)
    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=s3_key,
        Body=body,
        ContentType='application/json; charset=utf-8'
    )
    return True

# 5. 병렬 처리 (10개씩 동시에 업로드)
success_count = 0
with ThreadPoolExecutor(max_workers=10) as executor:
    # 모든 파일을 스레드풀에 예약
    futures = [executor.submit(upload_file_to_s3, fp) for fp in json_files]
    
    # 완료되는 순서대로 카운트
    for idx, future in enumerate(as_completed(futures), 1):
        try:
            future.result()
            success_count += 1
            # 1000개마다 진행 상황 출력
            if idx % 1000 == 0 or idx == total_files:
                print(f"진행 상황: {idx} / {total_files} 업로드 완료...")
        except Exception as e:
            print(f"업로드 오류 발생: {e}")

print(f"\n[완료] S3 업로드 완료! (성공: {success_count}/{total_files}개)")

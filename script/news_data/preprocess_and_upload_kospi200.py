import os
import re
import glob
import json
import boto3
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed

# 1. 환경변수 로드 (.env.local)
load_dotenv('.env.local')

# 2. S3 클라이언트 및 버킷 설정
s3 = boto3.client('s3')
BUCKET_NAME = 'fisa-news-archive'
DATA_DIR = 'data/news'
TARGET_FOLDERS = [
    "코스피200_KOSPI200"
]

# 3. 사용자 정의 clean_financial_news 함수 적용
def clean_financial_news(text: str) -> str:
    if not text:
        return ""

    # 1. 기사 하단 저작권 및 배너 문구 제거 (가장 먼저 잘라내기)
    text = re.sub(r"(<저작권자|▶|ⓒ).*$", "", text, flags=re.MULTILINE | re.DOTALL)
    text = re.sub(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", "", text) # 이메일 제거

    # 2. 언론사별 상단 메타데이터 및 말머리 제거
    text = re.sub(r"\[머니투데이.*?\]", "", text) # 머니투데이 대괄호 마크
    text = re.sub(r"\(.*?\=연합뉴스\)", "", text) # (서울=연합뉴스) 형태
    text = re.sub(r"사진\s*=\s*\S+", "", text) # 사진=머니S 등 제거
    text = re.sub(r"사진제공\s*=\s*\S+", "", text)

    # 3. 불필요한 특수문자 제거 (★ 마침표, 쉼표, %, +,- 기호는 반드시 제외)
    text = re.sub(r"[^\w\s.,%+\-가-힣]", " ", text)

    # 4. 줄바꿈 기호를 띄어쓰기로 대체 및 공백 압축 (토큰 절감 핵심)
    text = re.sub(r"[\r\n]+", " ", text)     # 모든 줄바꿈을 공백으로 대체
    text = re.sub(r" +", " ", text)          # 연속된 띄어쓰기를 단일 공백으로

    return text.strip()

json_files = []
for folder in TARGET_FOLDERS:
    folder_path = os.path.join(DATA_DIR, folder)
    json_files.extend(glob.glob(f"{folder_path}/**/*.json", recursive=True))

total_files = len(json_files)

print(f"[시작] 총 {total_files}개의 KOSPI200 뉴스 파일을 찾았습니다.")
print(f"[{BUCKET_NAME}] 버킷의 preprocessed 경로로 병렬 업로드를 시작합니다...\n")

def preprocess_and_upload_file(filepath):
    filename = os.path.basename(filepath)
    folder_name = os.path.basename(os.path.dirname(filepath))
    ticker = folder_name.split('_')[-1] # KOSPI200
    
    year = filename[:4]
    month = filename[5:7]

    # S3 경로 규격: preprocessed/KOSPI200/{year}/{month}/{filename}
    s3_key = f"preprocessed/{ticker}/{year}/{month}/{filename}"

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    fulltext = data.get('fulltext', '')
    
    # 사용자 정의 clean_financial_news 전처리 함수 호출
    preprocessed_text = clean_financial_news(fulltext)
    
    data['fulltext'] = preprocessed_text
    data['fulltext_length'] = len(preprocessed_text)

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
    futures = [executor.submit(preprocess_and_upload_file, fp) for fp in json_files]
    
    for idx, future in enumerate(as_completed(futures), 1):
        try:
            future.result()
            success_count += 1
            if idx % 500 == 0 or idx == total_files:
                print(f"진행 상황: {idx} / {total_files} 업로드 완료...")
        except Exception as e:
            print(f"업로드 오류 발생: {e}")

print(f"\n[완료] KOSPI200 S3 preprocessed 업로드 완료! (성공: {success_count}/{total_files}개)")

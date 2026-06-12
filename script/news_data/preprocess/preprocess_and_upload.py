import os
import re
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

# 3. 10개 종목 폴더 정의
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

# 4. 전처리 함수 (금융 도메인용 — 마침표/쉼표/%/+/- 등 금융 기호 보존)
#    이전 Option B는 모든 특수기호를 제거해 "3.7%", "8,500억원", "+2.3%" 같은
#    금융 수치가 뭉개졌다. 본 함수는 금융 기호를 살리고 노이즈만 정제한다.
def clean_financial_news(text: str) -> str:
    if not text:
        return ""

    # 1. 기사 하단 저작권 및 배너 문구 제거 (가장 먼저 잘라내기)
    text = re.sub(r"(<저작권자|▶|ⓒ).*$", "", text, flags=re.MULTILINE | re.DOTALL)
    # 이메일 제거
    text = re.sub(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", "", text)

    # 2. 언론사별 상단 메타데이터 및 말머리 제거
    text = re.sub(r"\[머니투데이.*?\]", "", text)      # 머니투데이 대괄호 마크
    text = re.sub(r"\(.*?\=연합뉴스\)", "", text)       # (서울=연합뉴스) 형태
    text = re.sub(r"사진\s*=\s*\S+", "", text)          # 사진=머니S 등 제거
    text = re.sub(r"사진제공\s*=\s*\S+", "", text)

    # 3. 불필요한 특수문자 제거 (★ 마침표, 쉼표, %, +, - 기호는 반드시 보존)
    #    금융 수치에 쓰이는 기호와 문장 마침표를 제외한 나머지 특수문자만 청소
    text = re.sub(r"[^\w\s.,%+\-가-힣]", " ", text)

    # 4. 줄바꿈(\n, \r) 제거 → 공백으로 대체 후 연속 공백 압축 (토큰 절감 핵심)
    text = text.replace("\n", " ").replace("\r", " ")   # 줄바꿈 기호 제거
    text = re.sub(r" +", " ", text)                     # 연속된 띄어쓰기 → 단일 공백

    return text.strip()

# 5. 개별 파일 전처리 및 S3 업로드 함수
def preprocess_and_upload_file(filepath):
    # 파일명 추출 (예: 2020-01-01.json)
    filename = os.path.basename(filepath)
    
    # 상위 폴더명 추출 (예: 삼성전자_005930)
    folder_name = os.path.basename(os.path.dirname(filepath))
    
    # 티커 추출 (예: 005930)
    ticker = folder_name.split('_')[-1]
    
    # 연도와 월 추출
    year = filename[:4]
    month = filename[5:7]
    
    # S3 preprocessed 경로 생성
    s3_key = f"preprocessed/{ticker}/{year}/{month}/{filename}"
    
    # JSON 파일 읽기
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    fulltext = data.get('fulltext', '')

    # 금융 도메인 전처리 적용 (금융 기호 보존)
    preprocessed_text = clean_financial_news(fulltext)
    
    # JSON 내용 업데이트
    data['fulltext'] = preprocessed_text
    data['fulltext_length'] = len(preprocessed_text)
    
    # S3 업로드용 body 직렬화
    body = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
    
    # S3 preprocessed 경로에 업로드
    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=s3_key,
        Body=body,
        ContentType='application/json; charset=utf-8'
    )
    return True

def main():
    json_files = []
    for folder in TARGET_FOLDERS:
        folder_path = os.path.join(DATA_DIR, folder)
        if os.path.exists(folder_path):
            json_files.extend(glob.glob(f"{folder_path}/**/*.json", recursive=True))
            
    total_files = len(json_files)
    print(f"[시작] 총 {total_files}개의 뉴스 파일을 찾았습니다.")
    print(f"[{BUCKET_NAME}] 버킷의 preprocessed 경로로 병렬 업로드를 시작합니다...\n")
    
    success_count = 0
    # 병렬 처리 (10개 스레드)
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(preprocess_and_upload_file, fp) for fp in json_files]
        
        for idx, future in enumerate(as_completed(futures), 1):
            try:
                future.result()
                success_count += 1
                if idx % 1000 == 0 or idx == total_files:
                    print(f"진행 상황: {idx} / {total_files} 완료...")
            except Exception as e:
                print(f"오류 발생: {e}")
                
    print(f"\n[완료] S3 전처리 업로드 완료! (성공: {success_count}/{total_files}개)")

if __name__ == "__main__":
    main()

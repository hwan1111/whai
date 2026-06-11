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

# 4. Option B 전처리 함수 정의
def preprocess_option_b(text):
    if not text:
        return ""
    
    # R1: 줄바꿈 기호를 공백으로 대체
    temp_text = text.replace('\n', ' ').replace('\r', ' ')
    
    # 문장 분할 (마침표로 분할)
    sentences = [s.strip() for s in temp_text.split('.') if s.strip()]
    
    processed_sentences = []
    for sentence in sentences:
        # R3: 저작권/저작권자 포함 문장 제외
        if "저작권" in sentence or "저작권자" in sentence:
            continue
            
        # R5: 기사/기자 포함 문장 제외
        if "기사" in sentence or "기자" in sentence:
            continue
            
        # R6: 이메일 제거
        sentence = re.sub(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', '', sentence)
        
        # R2: 특수기호 날리기 (한글, 영문, 숫자, 공백 제외 제거)
        sentence = re.sub(r'[^가-힣ㄱ-ㅎㅏ-ㅣa-zA-Z0-9\s]', '', sentence)
        
        # 연속된 공백 정리
        sentence = re.sub(r'\s+', ' ', sentence).strip()
        if sentence:
            processed_sentences.append(sentence)
            
    # 마침표가 사라졌으므로 문장들을 다시 띄어쓰기로 결합
    return " ".join(processed_sentences)

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
    
    # Option B 전처리 적용
    preprocessed_text = preprocess_option_b(fulltext)
    
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

import os
import re
import sys
import json
import glob
import subprocess
from itertools import combinations

# 1. 자동 패키지 설치 (kiwipiepy, matplotlib, pandas)
def install_requirements():
    required_packages = ["kiwipiepy", "matplotlib", "pandas"]
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            print(f"[설치] '{package}' 라이브러리가 설치되지 않았습니다. 설치를 진행합니다...")
            subprocess.run([sys.executable, "-m", "pip", "install", package], check=True)
            print(f"[완료] '{package}' 설치가 완료되었습니다.")

install_requirements()

from kiwipiepy import Kiwi
import matplotlib.pyplot as plt
import pandas as pd

# 2. 형태소 분석기 초기화
try:
    kiwi = Kiwi()
    print("[성공] Kiwi 형태소 분석기 로드 완료.")
except Exception as e:
    print(f"[오류] Kiwi 형태소 분석기 로드 실패: {e}")
    kiwi = None

# 3. 전처리 규칙 함수 정의
def apply_rules(text, rule_mask):
    """
    rule_mask: 6비트 정수 (예: 63 -> 모든 규칙 활성화, 0 -> 모든 규칙 비활성화)
    bits:
      bit 0 (R1): 줄바꿈 기호를 띄어쓰기로 대체
      bit 1 (R2): 특수기호 날리기
      bit 2 (R3): '저작권자', '저작권' 문장 날리기
      bit 3 (R4): 조사 날리기 (Kiwi POS tag 'J*' 제거)
      bit 4 (R5): '기사', '기자' 문장 날리기
      bit 5 (R6): 이메일 날리기
    """
    r1 = bool(rule_mask & (1 << 0))
    r2 = bool(rule_mask & (1 << 1))
    r3 = bool(rule_mask & (1 << 2))
    r4 = bool(rule_mask & (1 << 3))
    r5 = bool(rule_mask & (1 << 4))
    r6 = bool(rule_mask & (1 << 5))

    # 문장 분할
    if r1:
        # 줄바꿈을 공백으로 대체 후 마침표로만 분할
        temp_text = text.replace('\n', ' ').replace('\r', ' ')
        sentences = [s.strip() for s in temp_text.split('.') if s.strip()]
    else:
        # 줄바꿈과 마침표 모두로 분할
        sentences = [s.strip() for s in re.split(r'\.|\n|\r', text) if s.strip()]

    processed_sentences = []
    
    for sentence in sentences:
        # R3: 저작권 관련 문장 날리기
        if r3 and ("저작권" in sentence or "저작권자" in sentence):
            continue
            
        # R5: 기사/기자 관련 문장 날리기
        if r5 and ("기사" in sentence or "기자" in sentence):
            continue

        # R6: 이메일 날리기
        if r6:
            sentence = re.sub(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', '', sentence)

        # R2: 특수기호 날리기 (한글, 영문, 숫자, 공백 제외 제거)
        if r2:
            sentence = re.sub(r'[^가-힣ㄱ-ㅎㅏ-ㅣa-zA-Z0-9\s]', '', sentence)

        # R4: 조사 날리기 (Kiwi 형태소 분석기 활용)
        if r4 and kiwi:
            mask = [True] * len(sentence)
            try:
                tokens = kiwi.tokenize(sentence)
                for token in tokens:
                    if token.tag.startswith('J'): # 조사는 'J'로 시작함 (JKS, JKO, JX 등)
                        for idx in range(token.start, token.end):
                            if idx < len(mask):
                                mask[idx] = False
                sentence = "".join([c for idx, c in enumerate(sentence) if mask[idx]])
            except Exception:
                pass

        # 공백 정리
        sentence = re.sub(r'\s+', ' ', sentence).strip()
        if sentence:
            processed_sentences.append(sentence)

    # 최종 병합
    return " ".join(processed_sentences)

# 4. 데이터 로드 (종목당 최대 100개씩 총 300개 로드)
def load_sample_data():
    target_tickers = [
        ("삼성전자", "005930"),
        ("SK하이닉스", "000660"),
        ("KB금융", "105560")
    ]
    base_dirs = ["data/news", "data"]
    articles = []

    for comp_name, ticker in target_tickers:
        folder_path = None
        # 기사의 실제 경로를 동적으로 검색
        for base in base_dirs:
            if not os.path.exists(base):
                continue
            # data/news/*_005930 이나 data/*_005930 형태 매칭
            matching_dirs = glob.glob(os.path.join(base, f"*_{ticker}"))
            if matching_dirs:
                folder_path = matching_dirs[0]
                break
        
        if not folder_path or not os.path.exists(folder_path):
            print(f"[경고] {comp_name} ({ticker}) 폴더를 찾지 못했습니다. 경로 확인 필요.")
            continue
            
        folder_name = os.path.basename(folder_path)
        files = glob.glob(f"{folder_path}/**/*.json", recursive=True)
        # 최대 100개 슬라이싱
        files = sorted(files)[:100]
        
        print(f"[데이터 로드] {folder_name} 폴더에서 {len(files)}개 파일 로드 중...")
        for filepath in files:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                fulltext = data.get("fulltext")
                if fulltext and len(fulltext.strip()) > 50:
                    articles.append({
                        "ticker": ticker,
                        "name": comp_name,
                        "filename": os.path.basename(filepath),
                        "text": fulltext.strip()
                    })
            except Exception as e:
                print(f"파일 읽기 오류 ({filepath}): {e}")
                
    print(f"[완료] 총 {len(articles)}개의 뉴스 기사 데이터를 확보했습니다.")
    return articles

def main():
    # 데이터 불러오기
    articles = load_sample_data()
    if not articles:
        print("[오류] 분석할 기사 데이터가 없습니다. data/news 디렉토리를 확인하세요.")
        return

    # 63가지 조합 시뮬레이션 (0은 원본 유지이므로 1~63까지 진행)
    # 조합별 총 글자 수 기록
    results = []
    
    rule_names = {
        0: "R1(줄바꿈)",
        1: "R2(특수기호)",
        2: "R3(저작권)",
        3: "R4(조사)",
        4: "R5(기사기자)",
        5: "R6(이메일)"
    }
    
    # baseline 원본 크기 계산
    total_orig_len = sum(len(a["text"]) for a in articles)
    avg_orig_len = total_orig_len / len(articles)
    
    print(f"\n[시뮬레이션] 시작... 총 {len(articles)}개 기사의 원본 평균 길이는 {avg_orig_len:.1f}자입니다.")
    
    for mask in range(64):
        # 활성화된 규칙 리스트 구하기
        active_rules = []
        for i in range(6):
            if mask & (1 << i):
                active_rules.append(rule_names[i])
        
        comb_name = "+".join(active_rules) if active_rules else "원본(None)"
        
        # 기사별로 전처리 후 총 길이 구하기
        total_proc_len = 0
        for article in articles:
            proc_text = apply_rules(article["text"], mask)
            total_proc_len += len(proc_text)
            
        avg_proc_len = total_proc_len / len(articles)
        reduction_rate = ((total_orig_len - total_proc_len) / total_orig_len) * 100
        
        results.append({
            "mask": mask,
            "rules_count": len(active_rules),
            "combination": comb_name,
            "avg_length": avg_proc_len,
            "reduction_rate": reduction_rate
        })
        
        # 진행상황 출력
        if mask % 10 == 0 or mask == 63:
            print(f"  진행 상황: 조합 {mask}/63 완료 ({comb_name}) -> 감소율 {reduction_rate:.2f}%")

    df_res = pd.DataFrame(results)
    
    # 5. 결과 저장 (CSV 및 JSON)
    os.makedirs("data", exist_ok=True)
    df_res.to_csv("data/preprocess_simulation_results.csv", index=False, encoding="utf-8-sig")
    print("\n[완료] 시뮬레이션 결과가 data/preprocess_simulation_results.csv에 저장되었습니다.")

    # 6. 시각화 (그래프 생성)
    # 감소율 순으로 정렬하여 상위 25개 시각화
    df_sorted = df_res.sort_values(by="reduction_rate", ascending=False)
    
    # Matplotlib 한글 폰트 설정 (Windows 기준 맑은 고딕 사용)
    plt.rcParams['font.family'] = 'Malgun Gothic'
    plt.rcParams['axes.unicode_minus'] = False

    fig, ax = plt.subplots(figsize=(14, 8))
    
    # 63개 다 그리면 복잡하므로 감소율 기준 내림차순 상위 20개 조합 그리기
    top_n = 20
    df_plot = df_sorted.head(top_n)
    
    bars = ax.barh(df_plot["combination"], df_plot["reduction_rate"], color="skyblue", edgecolor="grey")
    ax.invert_yaxis()  # 상위가 제일 위로 오도록 설정
    ax.set_xlabel("텍스트 감소율 (%)", fontsize=12)
    ax.set_ylabel("규칙 조합", fontsize=12)
    ax.set_title(f"전처리 규칙 조합별 텍스트 감소율 Top {top_n} (총 {len(articles)}개 기사 분석)", fontsize=14, fontweight="bold")
    
    # 바 우측에 값 라벨 추가
    for bar in bars:
        width = bar.get_width()
        ax.text(width + 0.5, bar.get_y() + bar.get_height()/2, f"{width:.2f}%", 
                va="center", ha="left", fontsize=9, fontweight="semibold")

    plt.tight_layout()
    
    # 아티팩트 디렉토리 및 로컬 저장 경로 설정
    # conversation artifacts directory
    artifacts_dir = r"C:\Users\최성민\.gemini\antigravity\brain\334f3241-aae0-420e-b8b5-71ae375c8b19\artifacts"
    os.makedirs(artifacts_dir, exist_ok=True)
    
    chart_path = os.path.join(artifacts_dir, "preprocess_reduction_chart.png")
    plt.savefig(chart_path, dpi=150)
    # 로컬 작업폴더에도 백업용 저장
    local_chart_path = r"c:\ITStudy\3\preprocess_reduction_chart.png"
    plt.savefig(local_chart_path, dpi=150)
    plt.close()
    
    print(f"[완료] 그래프 이미지가 저장되었습니다:\n  - {chart_path}\n  - {local_chart_path}")

if __name__ == "__main__":
    main()

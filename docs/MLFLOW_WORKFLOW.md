# MLflow 뉴스 요약 파이프라인 가이드

완전 동적 MLflow 연동 - 코드 수정 없이 Web UI에서 모든 설정 관리

## 📋 개요

```
📝 프롬프트 관리 (Web UI)
         ↓
💻 로컬 코드 실행 (Python)
         ↓
📊 실험 기록 (Web UI)
```

- **프롬프트**: MLflow Model Registry에서 관리
- **실험**: MLflow Experiments에서 자동 기록
- **데이터셋**: MLflow Datasets에서 자동 등록
- **코드**: 로컬 Python 스크립트에서 실행

---

## 🔧 필수 설정

### 1. 프롬프트 등록 (최초 1회)

**URL**: http://52.78.237.104:5001

#### Step 1: Model Registry 접속
```
http://52.78.237.104:5001/#/models
```

#### Step 2: 새 모델 생성
1. "Create Model" 버튼 클릭
2. Model Name: `news_summary_prompt`
3. Create 버튼 클릭

#### Step 3: 프롬프트 텍스트 등록
Version 1에 아래 프롬프트 입력:

```
다음 뉴스 기사를 간결하게 요약하세요. 3-5 문장으로 요약하되, 핵심 내용만 포함하세요.

제목: {title}

본문:
{fulltext}

요약:
```

#### Step 4: 저장
Save 또는 Register 버튼 클릭

### 2. (선택사항) 상세 요약 프롬프트

Version 2 생성 또는 다른 모델 생성:

**Model Name**: `news_summary_detailed_prompt`

```
다음 뉴스 기사를 상세하게 요약하세요. 5-10 문장으로 요약하되, 다음 항목을 포함하세요:
1. 주요 이슈
2. 영향받는 당사자
3. 잠재적 영향
4. 관련 배경

제목: {title}

본문:
{fulltext}

상세 요약:
```

---

## 🚀 실행 방법

### Step 1: 레퍼런스 생성

```bash
python script/generate_news_reference.py
```

**작업**:
- S3 `preprocessed/` 폴더에서 각 티커별 데이터 로드
- 각 티커마다 10개 날짜 랜덤 샘플링
- 레퍼런스 생성 및 S3 `reference/` 에 저장
- MLflow Datasets에 자동 등록

**결과**:
```
✓ reference/ 폴더에 {ticker}_reference.json 생성
✓ S3에 reference/{ticker}/{year}/{month}/{date}.json 저장
✓ MLflow Datasets에 news_reference_{ticker} 등록
```

### Step 2: 요약 생성 (MLflow 추적)

```bash
python script/summarize_news.py
```

**작업**:
1. MLflow run 시작
2. MLflow에서 프롬프트 로드 (Web UI의 `news_summary_prompt` 참조)
3. 각 뉴스별로 LLM 호출하여 요약 생성
4. 요약 결과를 S3 `summarized/` 에 저장
5. MLflow에 자동으로 기록

**결과**:
```
✓ summarized/ 폴더에 {ticker}_summaries.json 생성
✓ S3에 summarized/{ticker}/{year}/{month}/{date}.json 저장
✓ MLflow run 생성 (Parameters, Metrics, Traces 자동 기록)
✓ evaluation datasets 링크 기록
```

---

## 📊 결과 확인

### Experiments 확인

**URL**: http://52.78.237.104:5001/#/experiments

```
Experiments
  └─ news_summary_service
     ├─ Run 1 (2024-06-11 10:00)
     │  ├─ Parameters
     │  │  ├─ prompt_key: news_summarization
     │  │  ├─ prompt_source: mlflow
     │  │  ├─ endpoint_name: mid_performance_llm
     │  │  └─ ...
     │  ├─ Metrics
     │  │  ├─ summaries_005930: 45
     │  │  ├─ dates_005930: 10
     │  │  └─ ...
     │  ├─ Traces
     │  │  └─ llm_summary (span)
     │  │     └─ LLM 호출 상세 기록
     │  └─ Datasets (Input)
     │     └─ news_reference_005930
     └─ ...
```

### Datasets 확인

**URL**: http://52.78.237.104:5001/#/datasets

```
Datasets
  ├─ news_reference_005930
  ├─ news_reference_000660
  └─ ...
```

### Model Registry 확인

**URL**: http://52.78.237.104:5001/#/models

```
Models
  ├─ news_summary_prompt
  │  └─ Version 1 (Latest)
  │     └─ 프롬프트 텍스트
  └─ ...
```

---

## 🔄 프롬프트 수정

**코드 수정 불필요!**

### 방법 1: 새 Version 생성 (추천)

1. Model Registry에서 `news_summary_prompt` 선택
2. "Create Version" 버튼
3. 새로운 프롬프트 텍스트 입력
4. Save

그 다음 실행:
```bash
python script/summarize_news.py
```
→ 자동으로 최신 Version (v2) 로드

### 방법 2: 버전 지정

`summarize_news.py`에서 버전 명시 (만약 필요하면):
```python
# prompt_registry.load_prompt("news_summarization", version="1")
# 현재는 "latest" 자동 사용
```

---

## 💡 주요 특징

### ✅ 완전 동적 연동
- 모든 프롬프트는 MLflow Web UI에서 관리
- 코드에 프롬프트 하드코딩 없음
- 프롬프트 변경 시 코드 수정 불필요

### ✅ 자동 기록
- Experiments: Parameters, Metrics, Traces 자동 기록
- Datasets: evaluation dataset 자동 등록
- 프롬프트 출처 추적 가능 (`prompt_source: mlflow`)

### ✅ 성능 최적화
- 프롬프트 캐싱으로 네트워크 요청 최소화
- 반복 실행 시 빠른 처리

### ✅ A/B 테스트 지원
- 여러 프롬프트 버전 관리
- Run별로 사용한 프롬프트 추적
- 성능 비교 가능

---

## 🐛 트러블슈팅

### 프롬프트를 찾을 수 없음

**오류 메시지**:
```
❌ MLflow Web UI에서 프롬프트를 찾을 수 없습니다.
모델명: news_summary_prompt
버전: latest
MLflow UI 링크: http://52.78.237.104:5001
→ Model Registry → news_summary_prompt 에서 프롬프트를 등록하세요
```

**해결**:
1. http://52.78.237.104:5001/#/models 접속
2. `news_summary_prompt` 모델이 있는지 확인
3. 없으면 새로 생성 후 프롬프트 등록

### 필요한 변수가 없음

**오류 메시지**:
```
❌ 필요한 변수 'title'이 없습니다.
프롬프트에서 찾은 변수: ['title', 'fulltext', 'summary']
```

**해결**:
- 프롬프트에 `{title}`, `{fulltext}` 변수 포함되어 있는지 확인
- 변수 이름이 정확한지 확인

### MLflow 연결 오류

**원인**: 원격 MLflow 서버가 다운되었거나 네트워크 연결 문제

**확인**:
```bash
curl -u admin:Woorifisateam4 http://52.78.237.104:5001/health
```

응답이 `OK`이면 정상

---

## 📝 파일 구조

```
script/
├─ generate_news_reference.py    # 레퍼런스 생성
└─ summarize_news.py              # 요약 생성 (MLflow 추적)

src/llm_utils/
├─ prompt_registry.py             # MLflow Prompt Registry 관리
├─ mlflow_logger.py               # MLflow 기본 로거
├─ evaluation_engine.py           # 평가 엔진
└─ ...

docs/
└─ MLFLOW_WORKFLOW.md             # 이 파일
```

---

## 🎯 핵심 개념

### Prompt Registry
- MLflow Model Registry에서 프롬프트를 모델처럼 관리
- 버전 관리 지원
- `mlflow.genai.load_prompt()`로 동적 로드

### Evaluation Datasets
- 요약 평가용 reference 데이터셋
- MLflow Datasets에 등록
- Run과 링크됨

### Traces
- LLM 호출 상세 기록
- MLflow Experiments의 Traces 탭에서 확인
- 프롬프트, 응답, 시간 등 기록

---

## 참고 링크

- [MLflow Prompt Registry 공식 문서](https://mlflow.org/docs/latest/genai/prompt-registry/)
- [MLflow Evaluation Datasets](https://mlflow.org/docs/latest/genai/datasets/)
- [MLflow Tracing](https://mlflow.org/docs/latest/genai/tracing/)

---

**마지막 업데이트**: 2026-06-11  
**상태**: 완전 동적 MLflow 연동 (100%)

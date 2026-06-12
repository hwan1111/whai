# MLflow GenAI Token Usage & Cost Tracking

뉴스 요약 파이프라인에서 LLM 토큰 사용량과 비용을 추적하는 시스템입니다.

## 아키텍처

```
news_summary_pipeline.py
    ↓
    ├─ GatewayClient (LLM 호출, 토큰 정보 반환)
    ├─ TokenTracker (토큰 추적, 비용 계산)
    └─ MLflow (토큰 사용량 및 비용 로깅)
```

## 모듈 구조

### 1. TokenTracker (`src/llm_utils/token_tracker.py`)

토큰 사용량 추적 및 비용 계산을 담당합니다.

#### 핵심 클래스

- **TokenUsage**: 토큰 사용량 데이터 클래스
  - `input_tokens`: 입력 토큰 수
  - `output_tokens`: 출력 토큰 수
  - `total_tokens`: 총 토큰 수 (자동 계산)

- **CostInfo**: 비용 정보 데이터 클래스
  - `input_cost`: 입력 비용 (USD)
  - `output_cost`: 출력 비용 (USD)
  - `total_cost`: 총 비용 (자동 계산)

- **TokenTracker**: 메인 추적 클래스
  - `track_usage()`: 토큰 추적 및 비용 계산
  - `log_to_mlflow()`: MLflow에 누적된 토큰 정보 로깅
  - `get_summary()`: 누적 통계 조회
  - `reset()`: 상태 초기화

#### 모델별 비용 설정

```python
MODEL_COSTS = {
    "mid_performance_llm": {
        "input_cost_per_mtok": 0.003,   # $0.003 per M tokens
        "output_cost_per_mtok": 0.009,  # $0.009 per M tokens
    },
    "low_performance_llm": {
        "input_cost_per_mtok": 0.0005,  # $0.0005 per M tokens
        "output_cost_per_mtok": 0.0015, # $0.0015 per M tokens
    },
}
```

비용은 OpenRouter 공식 가격을 기준으로 설정되며, 필요에 따라 `MODEL_COSTS`에서 수정 가능합니다.

### 2. NewsSummaryPipeline 통합

#### 초기화

```python
class NewsSummaryPipeline:
    def __init__(self, ...):
        ...
        self.token_tracker = TokenTracker()  # 초기화
```

#### 요약 생성 시 토큰 추적

```python
def summarize_news(self, ...):
    ...
    # 토큰 사용량 추적
    cost_info = self.token_tracker.track_usage(
        model=endpoint,
        input_tokens=input_token,
        output_tokens=output_token,
        endpoint=endpoint,
    )
    
    # Span에 토큰 메타데이터 추가
    span.set_usage(
        num_prompt_tokens=input_token,
        num_completion_tokens=output_token,
    )
    
    span.set_attributes({
        "cost_usd": cost_info.total_cost,
        "input_cost_usd": cost_info.input_cost,
        "output_cost_usd": cost_info.output_cost,
    })
```

#### 실행 완료 시 요약 로깅

```python
def run_evaluation(self, ...):
    ...
    # 토큰 사용량 요약
    token_summary = self.token_tracker.get_summary()
    
    # MLflow에 로깅
    self.mlflow_logger.log_metrics({
        "total_input_tokens": token_summary["total_usage"]["input_tokens"],
        "total_output_tokens": token_summary["total_usage"]["output_tokens"],
        "total_tokens": token_summary["total_usage"]["total_tokens"],
        "total_cost_usd": token_summary["total_cost"]["total_cost_usd"],
    })
    self.token_tracker.log_to_mlflow()
```

## 사용 방법

### 평가 모드 (mid vs low 비교)

```bash
python script/llm/news_summary_pipeline.py \
  --mode evaluation \
  --tickers 005930 000660 \
  --sample-size 10
```

**로그 출력 예시**:
```
📥 LLM 응답 수신: 250자 (input_token=1234, output_token=567, cost=$0.004321)
...
✅ 평가 완료
📊 토큰 사용량 요약:
   → 총 토큰: 45678 (입력: 30000, 출력: 15678)
   → 총 비용: $0.067234 USD
```

### 프로덕션 모드 (low로 전체 처리)

```bash
python script/llm/news_summary_pipeline.py \
  --mode production \
  --tickers 005930 000660
```

## MLflow UI에서 확인

### 1. Run-level 메트릭
- `total_input_tokens`: 총 입력 토큰
- `total_output_tokens`: 총 출력 토큰
- `total_tokens`: 총 토큰
- `total_cost_usd`: 총 비용 (USD)

### 2. Span-level 메타데이터
- `cost_usd`: 개별 요약의 비용
- `input_cost_usd`: 입력 비용
- `output_cost_usd`: 출력 비용

### 3. Span Usage
- `num_prompt_tokens`: 입력 토큰 (span 표준)
- `num_completion_tokens`: 출력 토큰 (span 표준)

## 테스트

```bash
# TokenTracker 단위 테스트
python -m pytest test/src/llm_utils/test_token_tracker.py -v
```

## 비용 추정 예시

### 평가 모드 (10개 샘플 × 2개 엔드포인트)
- 각 뉴스당 ~100 input tokens, ~80 output tokens

**mid_performance_llm**:
- 입력: (1000 뉴스 × 100 tokens) = 100,000 tokens → $0.30
- 출력: (1000 뉴스 × 80 tokens) = 80,000 tokens → $0.72
- 소계: $1.02

**low_performance_llm**:
- 입력: 100,000 tokens → $0.05
- 출력: 80,000 tokens → $0.12
- 소계: $0.17

**총 비용**: $1.19

## 비용 최적화

### 1. 샘플 크기 조정
```bash
# 작은 샘플로 먼저 테스트
--sample-size 5  # 비용 50% 감소
```

### 2. 저비용 모델 사용
- `low_performance_llm`은 `mid_performance_llm`의 약 17% 비용

### 3. 배치 처리
- 여러 뉴스를 한 번에 요약하는 배치 모드 추가 계획

## 참고

- [MLflow GenAI Token Usage & Cost Tracking](https://mlflow.org/docs/3.12.0/genai/tracing/token-usage-cost/)
- [OpenRouter API Pricing](https://openrouter.ai/docs#models)

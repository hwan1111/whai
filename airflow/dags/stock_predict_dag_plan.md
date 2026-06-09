# 주가 예측 시스템 설계 기획서

> 작성일: 2026-06-09  
> 작성자: Choi  
> 목적: 종목별 우선순위 모델 기반 일일 주가 예측 자동화 + 데이터 드리프트 감지 + UI 시각화

---

## 문서 구성

| 파트 | 대상 | 내용 |
|------|------|------|
| **PART 1** | 데이터 엔지니어 / 백엔드 | DAG 설계, DB 스키마, 오차범위 계산, API 명세 |
| **PART 2** | UI 개발자 | 화면 구성, 데이터 소스, 렌더링 분기 로직 |

---

# PART 1. DAG 설계 + DB 적재

---

## 1. 배경 및 목적

`model/주가예측모델/integration/model_priority.ipynb` 에서 10종목에 대해 Choi(통계/Prophet)와 SU(ML/DL) 모델을 비교·확정한 결과를 바탕으로, 매일 자동으로 예측을 생성하고 모델 성능 저하를 감지해 자동 전환하는 Airflow 파이프라인을 구축한다.

---

## 2. 종목별 우선순위 모델 현황

| 종목 | 티커 | 1순위 모델 | MAPE | 출처 | 예측 방식 | 2순위 모델 | MAPE | 출처 | 예측 방식 |
|------|------|----------|------|------|---------|----------|------|------|---------|
| KB금융 | 105560 | ARIMA(3,0,0) | 1.56% | Choi | monthly | LGBMRegressor(quantile) | 7.07% | SU | D+5 단일 |
| 신한지주 | 055550 | Prophet | 1.72% | Choi | monthly | XGBRegressor | 2.08% | SU | D+5 단일 |
| 한화에어로스페이스 | 012450 | Prophet | 3.43% | Choi | monthly | LGBMRegressor(quantile) | 11.94% | SU | D+5 단일 |
| 기아 | 000270 | Prophet | 3.52% | Choi | monthly | ElasticNet | 7.44% | SU | D+5 단일 |
| LG화학 | 051910 | Prophet | 4.78% | Choi | monthly | PatchTST | 8.08% | SU | D+5 단일 |
| SK이노베이션 | 096770 | LGBMRegressor(mse) | 5.21% | SU | D+5 단일 | ARIMA(0,0,3) | 5.36% | Choi | monthly |
| LIG넥스원 | 079550 | HuberRegressor | 5.68% | SU | D+5 단일 | VECM | 5.70% | Choi | monthly |
| 현대차 | 005380 | Prophet | 7.82% | Choi | monthly | PatchTST | 9.87% | SU | D+5 단일 |
| 삼성전자 | 005930 | ExtraTreesRegressor | 5.09% | SU | D+5 단일 | Prophet | 10.22% | Choi | monthly |
| SK하이닉스 | 000660 | PatchTST | 10.84% | SU | D+5 단일 | Prophet | 13.13% | Choi | monthly |

### 드리프트 전환 임계값

| 종목 | 1순위 baseline MAPE | 전환 임계값 (×1.5) |
|------|-------------------|-----------------|
| KB금융 | 1.56% | 2.34% |
| 신한지주 | 1.72% | 2.58% |
| 한화에어로스페이스 | 3.43% | 5.15% |
| 기아 | 3.52% | 5.28% |
| LG화학 | 4.78% | 7.17% |
| SK이노베이션 | 5.21% | 7.82% |
| LIG넥스원 | 5.68% | 8.52% |
| 현대차 | 7.82% | 11.73% |
| 삼성전자 | 5.09% | 7.64% |
| SK하이닉스 | 10.84% | 16.26% |

---

## 3. 전체 시스템 아키텍처

```
[장 마감 15:30 KST]
        ↓
┌─────────────────────────────────────────────────┐
│         finance_stock_predict_daily DAG          │
│                                                  │
│  fetch_market_data                               │
│    ├── yfinance: 10종목 + KOSPI200 + 외생변수    │
│    ├── pykrx:    KOSPI 일별 OHLCV                │
│    └── FDR:      S&P500, NDX, VIX, USD/KRW       │
│          ↓                                       │
│  predict_ticker (10종목 병렬)                     │
│    ├── Choi 1순위 (6종목)                         │
│    │   ARIMA / Prophet / VECM                    │
│    │   → forecast(20거래일) → D+5 추출           │
│    │   (나머지 D+1~D+4, D+6~D+20은 별도 저장)    │
│    └── SU 1순위 (4종목)                           │
│        pkl 로드 + 피처 계산 → D+5 단일 예측       │
│    ※ 두 방식 모두 D+5 가격 1개로 통일            │
│          ↓                                       │
│    MySQL에서 과거 20거래일 예측값 로드              │
│    → 실제 주가와 비교 → rolling MAPE 계산         │
│    → baseline MAPE × 1.5 초과 시                 │
│      → 2순위 모델로 재예측 (동일 D+5 통일 방식)   │
│          ↓                                       │
│  save_predictions_to_mysql                       │
│    prediction 테이블에 D+5 예측값 저장            │
│    (드리프트 감지 이력 누적 용도)                  │
│          ↓                                       │
│  (드리프트 감지 결과는 DB에만 기록)              │
└─────────────────────────────────────────────────┘
```

---

## 4. DAG 파일 구조

```
airflow/dags/
└── finance_stock_predict_daily.py      ← 메인 DAG
```

---

## 5. `finance_stock_predict_daily.py` 상세 설계

### 5-1. 스케줄 및 기본 설정

| 항목 | 값 |
|------|---|
| schedule | `30 6 * * 1-5` (06:30 UTC = 15:30 KST, 평일) |
| catchup | False |
| retries | 1 |
| retry_delay | 10분 |
| tags | `["finance", "prediction", "drift"]` |

### 5-2. Task 목록 및 흐름

```
predict_and_save (dynamic: 10종목 병렬)
```

> 예측 · 드리프트 감지 · 2순위 전환 · MySQL 저장을 종목당 1개 태스크로 처리.  
> 종목별로 독립적이므로 dynamic task mapping으로 병렬 실행 (최대 4개 동시).

### 5-3. Task별 상세

#### `fetch_market_data`

```
입력: 실행일 (execution_date)
출력: XCom → market_data dict

수집 항목:
- pykrx:   KOSPI 일별 종가 (2021-01-01 ~ 실행일)
- FDR:     S&P500, NDX, VIX, USD/KRW (2021-01-01 ~ 실행일)
- yfinance: 10종목 종가 + 외생변수 (USDKRW, WTI, VIX, KOSPI200) — Choi 모델용
            (2020-01-01 ~ 실행일)
```

#### `predict_ticker` (종목당 1개 task, 병렬 실행)

```
입력: ticker, market_data (XCom)
출력: XCom → prediction_result dict

흐름:
  1. 1순위 모델 예측 실행
     ├── Choi (source='Choi'):
     │   - TRAIN_WINDOWS 동적 계산 (실행일 기준)
     │   - 전처리 적용 (config.preprocess)
     │   - 모델 fit (ARIMA / Prophet / VECM)
     │   - forecast(~20거래일)
     │   - D+5 인덱스 추출 → 단일 포인트
     └── SU (source='SU'):
         - parquet 로드 → 피처 계산 (9 or 12개)
         - MSAR regime 피처 계산 (필요 종목만)
         - pkl 로드 (sklearn) 또는 state_dict 로드 (PatchTST)
         - predict → D+5 로그 수익률 → 주가 환산

  2. MySQL에서 과거 20거래일 예측값 로드
     SELECT * FROM prediction WHERE ticker=X ORDER BY date DESC LIMIT 20
     → 실제 종가와 비교 → rolling MAPE 계산
     → baseline_mape × 1.5 초과 여부 판단

  3. 드리프트 감지 시:
     → 2순위 모델로 동일 흐름 재실행

  4. 최종 예측값 반환
     {
       "ticker": "105560",
       "date": "2026-06-09",
       "model_used": "priority_1 | priority_2",
       "model_name": "ARIMA",
       "pred_return_d5": 0.023,
       "pred_price_d5": 85000,
       "drift_detected": false,
       "rolling_mape": 1.8,
       "retrain_needed": false
     }
```

#### `save_predictions_to_mysql`

```
저장 테이블: prediction
저장 내용: predict_ticker 반환 dict 전체

드리프트 감지를 위한 이력 누적 목적.
5일 후 실제 주가(stock 테이블)와 JOIN해 rolling MAPE 계산에 사용됨.

-- 드리프트 감지 쿼리 예시
SELECT p.pred_price_d5, s.close AS actual_price
FROM prediction p
JOIN stock s ON s.ticker = p.ticker AND s.date = p.target_date
WHERE p.ticker = '105560'
ORDER BY p.date DESC
LIMIT 20
```

---

## 6. 모델별 추론 상세

### 6-1. Choi 모델 (통계 / Prophet)

| 구분 | 내용 |
|------|------|
| 데이터 소스 | yfinance (`{ticker}.KS`, `KRW=X`, `CL=F`, `^VIX`, `^KS200`) |
| 학습 시작 | 실행일 기준 동적 계산 (Super_Short=6개월 ~ Full=2020-01-01) |
| 전처리 | 8종 중 종목별 최적 옵션 (raw / log / diff1 / ret / diff2 / log_diff2 / seas5 / log_seas5) |
| 역변환 | 전처리 종류에 따라 cumsum + exp 조합으로 원래 주가 스케일 복원 |
| 예측 범위 | forecast(20거래일) → index 5번째 = D+5 추출 |
| 소요 시간 | ARIMA/VECM: 수 초, Prophet: 30~60초/종목 |

**종목별 Choi 설정 요약:**

| 종목 | 모델 | preprocess | train_window | 추가 설정 |
|------|------|-----------|-------------|---------|
| KB금융 | ARIMA(3,0,0) | log | Super_Short | — |
| 신한지주 | Prophet | diff1 | Short | yearly+weekly seasonality |
| 한화에어로스페이스 | Prophet | ret | Mid_Short | yearly+weekly seasonality |
| 기아 | Prophet | raw | Recent | yearly+weekly seasonality |
| LG화학 | Prophet | diff1 | Full | yearly+weekly seasonality |
| SK이노베이션 | ARIMA(0,0,3) | raw | Super_Short | — |
| LIG넥스원 | VECM | level | Mid | exog: KOSPI200+WTI+VIX, deterministic='co' |
| 현대차 | Prophet | log | Short | yearly+weekly seasonality |
| 삼성전자 | Prophet | diff1 | Super_Short | yearly+weekly seasonality |
| SK하이닉스 | Prophet | log_diff2 | Recent | yearly+weekly seasonality |

### 6-2. SU 모델 (ML / DL)

| 구분 | 내용 |
|------|------|
| 데이터 소스 | pykrx (KOSPI), FDR (S&P500/NDX/VIX/USD-KRW), parquet (종목별 OHLCV) |
| 기본 피처 (9개) | ret_1d, ret_5d, ret_20d, vol_norm, kospi_ret, sp500_ret, ndx_ret, usdkrw_ret, vix_chg |
| 확장 피처 (3개) | regime_prob, regime_duration, regime_change (MSAR k=2, order=1로 계산) |
| 타겟 | log(close_d+5 / close) — D+5 로그 수익률 |
| sklearn 계열 추론 | 최신 1행 → model.predict(X) → 로그 수익률 → 현재가 × exp(pred) |
| PatchTST 추론 | 최근 512거래일 × 9피처 시퀀스 → forward → D+5 합산 → RevIN 역정규화 |
| pkl 경로 | `model/주가예측모델/su/data/saved_models/{ticker}.pkl` |
| PatchTST pkl | `model/주가예측모델/su/model/patchtst_v18_model.pkl` (state_dict, 종목별 key) |

**종목별 SU 설정 요약:**

| 종목 | 모델 | 피처 수 | pkl 키 |
|------|------|--------|--------|
| KB금융 | LGBMRegressor(quantile) | 9 | saved_models/105560.pkl |
| 신한지주 | XGBRegressor | 12 | saved_models/055550.pkl |
| 한화에어로스페이스 | LGBMRegressor(quantile) | 12 | saved_models/012450.pkl |
| 기아 | ElasticNet | 12 | saved_models/000270.pkl |
| LG화학 | PatchTST | 9 | patchtst_v18_model.pkl / 'LG Chem' |
| SK이노베이션 | LGBMRegressor(mse) | 11 | saved_models/096770.pkl |
| LIG넥스원 | HuberRegressor | 12 | saved_models/079550.pkl |
| 현대차 | PatchTST | 9 | patchtst_v18_model.pkl / 'Hyundai Motor' |
| 삼성전자 | ExtraTreesRegressor | 12 | saved_models/005930.pkl |
| SK하이닉스 | PatchTST | 9 | patchtst_v18_model.pkl / 'SK Hynix' |

---

## 7. 드리프트 감지 메커니즘

### Choi vs SU 예측 범위 통일

Choi 모델은 실행일 기준 20거래일 전체를 한 번에 예측하고,  
SU 모델은 D+5 단일 포인트만 예측한다. DAG에서는 **D+5 가격 1개**로 통일해 비교한다.

```
Choi: [D+1, D+2, D+3, D+4, ★D+5★, D+6 ... D+20]
                              ↑ 이것만 사용 (나머지는 DB에 별도 저장)
SU:                          ★D+5★
                              ↑ 그대로 사용

→ 두 모델 모두 pred_price_d5 하나로 MAPE 계산 및 드리프트 감지
```

Choi의 MAPE는 중간 데이터 없이 예측한 값이라 SU보다 보수적이지만,  
임계값이 이미 각 모델의 baseline MAPE 기준으로 설정되어 있으므로 별도 보정 불필요.

### 드리프트 감지 흐름

```
매 실행일:
  1. MySQL에서 과거 20거래일치 예측 이력 로드
     SELECT * FROM prediction WHERE ticker=X ORDER BY date DESC LIMIT 20

  2. stock 테이블과 JOIN → D+5 실제 종가 조회
     → MAPE = |예측가 - 실제가| / 실제가 × 100

  3. rolling 20거래일 평균 MAPE 계산

  4. rolling MAPE > baseline_mape × 1.5 → 드리프트 감지

  5. 드리프트 감지 시:
     → 2순위 모델로 오늘 예측 재실행 (동일하게 D+5 추출)
     → 2순위도 임계값 초과 시 retrain_needed = True

  6. 최초 20거래일치 예측이 쌓이지 않은 경우:
     → 드리프트 감지 스킵, 1순위 예측 그대로 사용
```

### 왜 MySQL인가 (S3 대비)

| | MySQL | S3 |
|--|-------|----|
| 드리프트 감지 쿼리 | SQL 한 줄로 해결 | 파일 20개 다운로드 후 파싱 |
| 실제 주가와 비교 | stock 테이블과 JOIN | 별도 코드 필요 |
| 운영 복잡도 | 기존 Aiven 연결 재사용 | boto3 추가 관리 |
| 저장 비용 | Aiven 이미 사용 중 | 추가 비용 없지만 관리 포인트 증가 |

→ 예측 이력은 MySQL에 저장. S3는 뉴스/원본 데이터 전용으로 유지.

### 왜 rolling 20거래일인가

한국 주식시장 월 평균 거래일 수 ≈ 20일.  
rolling 20거래일 = rolling 1개월로, 모델 평가 기간(최근 1달)과 단위를 일치시키기 위함.

---

## 8. MySQL 저장 스키마

### prediction 테이블

```sql
CREATE TABLE prediction (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    ticker         VARCHAR(10)    NOT NULL,
    date           DATE           NOT NULL,   -- 예측 실행일 (오늘)
    target_date    DATE           NOT NULL,   -- D+5 날짜
    model_used     VARCHAR(20)    NOT NULL,   -- 'priority_1' | 'priority_2'
    model_name     VARCHAR(50)    NOT NULL,   -- 'ARIMA' | 'Prophet' | 'PatchTST' 등
    model_source   VARCHAR(10)    NOT NULL,   -- 'Choi' | 'SU'
    base_price     DECIMAL(12,2)  NOT NULL,   -- 예측 기준 종가 (오늘)
    pred_price_d5  DECIMAL(12,2)  NOT NULL,   -- D+5 예측 종가
    pred_return_d5 DECIMAL(8,6)   NOT NULL,   -- D+5 예측 로그 수익률
    drift_detected TINYINT(1)     NOT NULL DEFAULT 0,
    rolling_mape   DECIMAL(6,4),              -- 계산된 rolling MAPE (NULL = 이력 부족)
    threshold      DECIMAL(6,4)   NOT NULL,   -- baseline × 1.5
    retrain_needed TINYINT(1)     NOT NULL DEFAULT 0,
    -- Choi 전체 예측 (프론트 차트용, SU 채택 시 NULL)
    forecast_json  JSON,                      -- D+1~D+20 전체 예측 (Choi만, SU = NULL)
    created_at     DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_ticker_date (ticker, date)
);
```

### UI 연동 방식

`model_source` 컬럼 하나로 프론트 차트 방식을 분기한다.

```
model_source = 'Choi'
  → forecast_json 파싱 → D+1~D+20 라인 차트 (약 1달 전망)

model_source = 'SU'
  → pred_price_d5 단일값 → D+5 포인트 표시

드리프트 감지로 1순위 → 2순위 전환 시
  → model_source가 자동으로 바뀌므로 UI는 별도 처리 없이 분기됨
```

예: KB금융이 평소엔 Choi(ARIMA) → 20일 라인 차트, 드리프트 발생 시 SU(LGBM) → D+5 포인트로 자동 전환.

### 드리프트 감지 쿼리

```sql
-- 과거 20거래일 예측 vs 실제 주가 비교
SELECT
    p.date,
    p.pred_price_d5,
    s.close AS actual_price,
    ABS(p.pred_price_d5 - s.close) / s.close * 100 AS mape
FROM prediction p
JOIN stock s ON s.ticker = p.ticker AND s.date = p.target_date
WHERE p.ticker = '105560'
ORDER BY p.date DESC
LIMIT 20;
```

---

---

## 9. 오차범위(신뢰구간) 계산 방식

DAG 예측 단계에서 CI를 함께 계산해 MySQL에 저장한다. 백엔드는 저장된 값을 그대로 내려주고, UI는 이를 시각화에 활용한다.

### 계산 공식

```
sigma      = rolling 20거래일 log return의 표준편차
CI_Z       = 1.28  (80% 신뢰구간, norm.ppf(0.9))
CI_half(h) = CI_Z × sigma × sqrt(h)   # h = 예측 horizon(일)

상단 = base_price × exp(log_return + CI_half(h))
하단 = base_price × exp(log_return - CI_half(h))
```

- **Choi (monthly)**: D+1 ~ D+20 각 시점마다 `sqrt(h)` 적용 → 시간이 갈수록 CI 폭이 넓어짐
- **SU (D+5 단일)**: `h=5` 고정 → 단일 CI 밴드

### MySQL 저장 컬럼 (prediction 테이블 추가)

```sql
vol_20d        DECIMAL(8,6)   NOT NULL,   -- 계산에 사용한 rolling 20일 변동성(sigma)
ci_pct         DECIMAL(4,2)   NOT NULL DEFAULT 0.80,   -- 신뢰구간 %
ci_upper_d5    DECIMAL(12,2)  NOT NULL,   -- D+5 CI 상단
ci_lower_d5    DECIMAL(12,2)  NOT NULL,   -- D+5 CI 하단
-- forecast_json 구조에도 상단/하단 포함 (아래 참고)
```

### forecast_json 구조 (Choi 전용)

```json
{
  "forecast": [
    { "horizon": 1, "date": "2026-06-10", "price": 84100, "ci_upper": 84900, "ci_lower": 83300 },
    { "horizon": 2, "date": "2026-06-11", "price": 84300, "ci_upper": 85400, "ci_lower": 83200 },
    { "horizon": 5, "date": "2026-06-16", "price": 85300, "ci_upper": 87100, "ci_lower": 83500 },
    { "horizon": 10, "date": "2026-06-23", "price": 85800, "ci_upper": 88900, "ci_lower": 82700 },
    { "horizon": 20, "date": "2026-07-07", "price": 86200, "ci_upper": 91200, "ci_lower": 81200 }
  ]
}
```

> CI 폭은 horizon이 늘수록 `sqrt(h)` 비율로 넓어지므로 20일 전망일수록 불확실성이 시각적으로 드러난다.

---

## 10. 백엔드 API 명세

> **담당자 참고**: `backend/` 서비스에서 아래 엔드포인트를 구현한다.  
> prediction 테이블에서 데이터를 읽어 프론트에 내려주는 역할만 한다. 추론 로직은 없음.

### `GET /api/v1/predictions/{ticker}/latest`

가장 최근 예측 결과 1건을 반환한다. 프론트 메인 차트에서 사용.

**Response (Choi 채택 시)**

```json
{
  "ticker": "105560",
  "name": "KB금융",
  "date": "2026-06-09",
  "base_price": 83800,
  "model_source": "Choi",
  "model_name": "ARIMA",
  "model_used": "priority_1",
  "drift_detected": false,
  "rolling_mape": 1.72,
  "d5": {
    "target_date": "2026-06-16",
    "price": 85300,
    "return": 0.018,
    "ci_upper": 87100,
    "ci_lower": 83500,
    "ci_pct": 0.80
  },
  "forecast": [
    { "horizon": 1, "date": "2026-06-10", "price": 84100, "ci_upper": 84900, "ci_lower": 83300 },
    { "horizon": 2, "date": "2026-06-11", "price": 84300, "ci_upper": 85400, "ci_lower": 83200 },
    "..."
    { "horizon": 20, "date": "2026-07-07", "price": 86200, "ci_upper": 91200, "ci_lower": 81200 }
  ]
}
```

**Response (SU 채택 시)**

```json
{
  "ticker": "105560",
  "name": "KB금융",
  "date": "2026-06-09",
  "base_price": 83800,
  "model_source": "SU",
  "model_name": "LGBMRegressor",
  "model_used": "priority_2",
  "drift_detected": true,
  "rolling_mape": 2.51,
  "d5": {
    "target_date": "2026-06-16",
    "price": 84600,
    "return": 0.009,
    "ci_upper": 86200,
    "ci_lower": 83000,
    "ci_pct": 0.80
  },
  "forecast": [
    { "horizon": 1, "date": "2026-06-10", "price": 84200, "ci_upper": 85800, "ci_lower": 82600 },
    { "horizon": 2, "date": "2026-06-11", "price": 84350, "ci_upper": 85950, "ci_lower": 82750 },
    { "horizon": 3, "date": "2026-06-12", "price": 84400, "ci_upper": 86000, "ci_lower": 82800 },
    { "horizon": 4, "date": "2026-06-13", "price": 84500, "ci_upper": 86100, "ci_lower": 82900 },
    { "horizon": 5, "date": "2026-06-16", "price": 84600, "ci_upper": 86200, "ci_lower": 83000 }
  ]
}
```

> SU는 D+5 롤링 방식으로 D+1~D+5 궤적을 생성하므로 `forecast`가 항상 5개 존재한다.  
> Choi는 20개, SU는 5개 — `model_source`로 구분.

---

### `GET /api/v1/predictions/{ticker}/history`

과거 예측 이력과 실제 주가를 함께 반환한다. 드리프트 현황 차트에서 사용.

**Query params**: `days=20` (기본값 20)

**Response**

```json
{
  "ticker": "105560",
  "history": [
    {
      "date": "2026-06-09",
      "model_source": "Choi",
      "pred_price_d5": 85300,
      "actual_price_d5": null,
      "mape": null
    },
    {
      "date": "2026-05-30",
      "model_source": "Choi",
      "pred_price_d5": 83100,
      "actual_price_d5": 83800,
      "mape": 0.83
    }
  ],
  "rolling_mape": 1.72,
  "threshold": 2.34,
  "drift_detected": false
}
```

> `actual_price_d5`가 `null`이면 아직 D+5가 도래하지 않은 예측임.

---

## 11. UI 시각화 가이드

> **담당자 참고**: 아래는 데이터 구조와 렌더링 분기 기준이다.  
> 레이아웃 비중, 컬러, 컴포넌트 구체적 디자인은 UI 설계에 따라 자유롭게 변형 가능.

### 분기 기준

```
model_source = 'Choi'  →  forecast 20개, CI 폭이 시간에 따라 넓어지는 부채꼴
model_source = 'SU'    →  forecast 5개,  CI 폭 일정한 짧은 밴드
```

두 모드 모두 `forecast_json` + CI 밴드 구조는 동일하다.  
`model_source`만 보고 렌더링 범위(20일 vs 5일)와 CI 스타일을 다르게 적용하면 된다.  
드리프트로 전환되면 `model_source`가 자동으로 바뀌므로 UI는 별도 처리 없이 분기된다.

---

### Choi 모드 — 라인 차트 + CI 밴드

```
[실제 주가 히스토리] ─────────────────────┐ 오늘
                                          │
                                          │   [예측 라인 - - - - - - - -]
                                          │  [   CI 밴드 (점점 넓어짐)  ]
                                          │ [                            ]
                                          │[                              ]
────────────────────────────── D+5 ─── D+10 ─── D+20
```

| 요소 | 데이터 필드 |
|------|-----------|
| 실제 주가 히스토리 | stock 테이블 (별도 API) |
| 예측 라인 | `forecast[].price` |
| CI 상단 밴드 | `forecast[].ci_upper` |
| CI 하단 밴드 | `forecast[].ci_lower` |
| D+5 강조 포인트 | `d5.price` |
| CI % 표시 | `d5.ci_pct` → `"80% 신뢰구간"` 레이블 |

> CI 밴드는 horizon이 늘수록 자동으로 넓어진 값이 이미 저장되어 있음.  
> 프론트에서 별도 계산 없이 `ci_upper` / `ci_lower` 그대로 사용.

---

### SU 모드 — D+1~D+5 롤링 궤적 + CI 밴드

SU 모델은 D+5 단일 포인트만 예측하지만, **"N일 전 기준으로 D+5를 예측한 값 = D+(5-N)"** 방식으로 롤링하면 D+1~D+5 궤적을 만들 수 있다. 모델을 5번 실행해 선처럼 보이게 하는 방식으로, 추론 노트북(`stock_prediction_inference.ipynb`)에서 이미 이 방식으로 시각화하고 있음.

```
4일 전 기준 → D+5 예측 = 내일(D+1) 포인트
3일 전 기준 → D+5 예측 = 모레(D+2) 포인트
2일 전 기준 → D+5 예측 = D+3 포인트
1일 전 기준 → D+5 예측 = D+4 포인트
오늘 기준   → D+5 예측 = D+5 포인트
→ 5개 점을 이어 라인 + CI 밴드로 표시
```

```
[실제 주가 히스토리] ─────────────────────┐ 오늘
                                          │
                                          │  [예측 라인 - - - -]
                                          │  [  CI 밴드(일정폭) ]
──────────────────────────────────────── D+1 D+2 D+3 D+4 D+5
```

Choi와 달리 CI 폭은 `sigma × sqrt(5)` 고정이므로 시간이 지나도 밴드 폭이 일정하다.

| | Choi | SU |
|--|------|-----|
| 예측 범위 | D+1~D+20 | D+1~D+5 |
| CI 폭 | sqrt(h)로 날마다 넓어지는 부채꼴 | sqrt(5) 고정, 일정한 폭 |
| 데이터 출처 | 1회 fit 후 forecast | 5번 롤링 predict |

| 요소 | 데이터 필드 |
|------|-----------|
| 실제 주가 히스토리 | stock 테이블 (별도 API) |
| 예측 라인 | DAG가 롤링 실행 후 `forecast_json`에 D+1~D+5 저장 |
| CI 상단 밴드 | `forecast_json[].ci_upper` |
| CI 하단 밴드 | `forecast_json[].ci_lower` |

> SU도 `forecast_json`을 사용하므로, UI 분기 기준은 `model_source`로 변경.
> `model_source='SU'`이면 `forecast_json`의 길이가 5, `model_source='Choi'`이면 20.

---

### 드리프트 현황 차트 (선택적 추가 컴포넌트)

```
MAPE(%)
  │
  │ - - - - - - - - 임계값(threshold) - - - - - - - - - - -
  │            ●
  │      ●           ●
  │  ●                    ●    ●
  │                                   ●    ●    ●
  └──────────────────────────────────────────────────── 날짜
    D-19  D-17  D-15  D-13  D-10  D-8  D-5  D-3  D-1
```

| 요소 | 데이터 필드 |
|------|-----------|
| MAPE 점들 | `history[].mape` |
| 임계값 점선 | `threshold` |
| 드리프트 발생일 | `drift_detected=true`인 날짜 강조 |

> `actual_price_d5`가 `null`인 미래 예측은 이 차트에서 제외.

---

## 12. 파일 구현 목록

| 파일 | 상태 | 설명 |
|------|------|------|
| `airflow/dags/finance_stock_predict_daily.py` | **완료** | 메인 예측 DAG |
| `script/create_prediction_table.py` | **완료** | prediction 테이블 생성 스크립트 |
| `model/주가예측모델/integration/model_priority.ipynb` | 완료 | 종목별 모델 설정 정의 |
| `model/주가예측모델/su/model/stock_prediction_inference.ipynb` | 완료 | SU 추론 코드 참조 |
| `model/주가예측모델/choi/Traditional_statistical_models_2차.ipynb` | 완료 | Choi 추론 코드 참조 |

---

## 13. 기술 스택 및 의존성

| 라이브러리 | 용도 |
|-----------|------|
| `apache-airflow` | 파이프라인 오케스트레이션 |
| `yfinance` | Choi 모델용 주가/외생변수 수집 |
| `pykrx` | SU 모델용 KOSPI 데이터 수집 |
| `FinanceDataReader` | SU 모델용 매크로 데이터 수집 |
| `statsmodels` | ARIMA, VECM 학습/추론 |
| `prophet` | Prophet 학습/추론 |
| `scikit-learn` | ExtraTrees, ElasticNet, HuberRegressor |
| `lightgbm` | LGBMRegressor |
| `xgboost` | XGBRegressor |
| `torch` | PatchTST 추론 |
| `sqlalchemy` + `pymysql` | MySQL 예측 이력 저장/조회 |
| `pandas`, `numpy` | 데이터 처리 |

---

## 14. 미결 사항

| 항목 | 내용 |
|------|------|
| parquet 갱신 주기 | SU 모델용 `data/model_v2/{ticker}.parquet`를 매일 갱신하는 로직 필요 (기존 `finance_market_data_daily` DAG와 연계 검토) |
| 재학습 DAG 설계 | `finance_model_retrain_trigger.py` 상세 설계 필요 (SU pkl 재생성 + Choi 파라미터 재탐색) |
| 055550 데이터 | 신한지주 SU pkl이 없음 — `data/saved_models/055550.pkl` 생성 필요 (별도 이슈) |
| EC2 배포 환경 | Docker Compose 기반 Airflow 환경에서 torch, prophet 등 heavy 패키지 설치 확인 필요 |
| CI 계산 방식 | SU 모델의 CI가 rolling 변동성 기반인지 모델 자체 신뢰도 기반인지 SU 팀원에게 확인 필요 |

---

---

# PART 2. UI 설계 가이드

> **이 파트는 UI 개발자를 위한 문서입니다.**  
> 어떤 API를 호출해서 어떤 데이터를 받아야 하는지, 그 데이터를 화면에 어떻게 매핑하는지를 정리했습니다.  
> 세부 레이아웃 · 컬러 · 폰트 · 컴포넌트 구조는 UI 개발자의 재량입니다.

---

## UI-1. 화면 구성 개요

주가 예측 화면은 두 가지 차트 영역으로 구성됩니다.

```
┌─────────────────────────────────────────────────────────┐
│  [종목 선택]  KB금융 ▼                                   │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  A. 최근 1달 성능 검증 차트                               │
│     실제 주가 vs 모델이 예측했던 값 + 오차범위             │
│                                                         │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  B. 미래 예측 차트                                        │
│     오늘부터 D+5 (또는 D+20) 예측값 + 구름형 오차범위     │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## UI-2. 데이터 소스 (API 엔드포인트)

UI에서 호출할 API는 세 가지입니다. 백엔드 API 상세 스펙은 PART 1의 **섹션 10**을 참고하세요.

### 엔드포인트 1 — 최신 예측 (미래 차트용)

```
GET /api/v1/predictions/{ticker}/latest
```

| 필드 | 타입 | 용도 |
|------|------|------|
| `model_source` | `"Choi"` \| `"SU"` | 렌더링 분기 기준 |
| `base_price` | number | 오늘 종가 (차트 연결점) |
| `d5.price` | number | D+5 예측 종가 |
| `d5.ci_upper` | number | D+5 CI 상단 |
| `d5.ci_lower` | number | D+5 CI 하단 |
| `d5.ci_pct` | number | CI 신뢰도 (0.80) |
| `forecast` | array | D+1~D+20(Choi) 또는 D+1~D+5(SU) 예측 배열 |
| `forecast[].date` | string | 예측 날짜 |
| `forecast[].price` | number | 예측 종가 |
| `forecast[].ci_upper` | number | CI 상단 |
| `forecast[].ci_lower` | number | CI 하단 |

---

### 엔드포인트 2 — 과거 예측 이력 (성능 검증 차트용)

```
GET /api/v1/predictions/{ticker}/history?days=20
```

| 필드 | 타입 | 용도 |
|------|------|------|
| `history[].target_date` | string | 예측의 대상 날짜 (D+5) — **x축 기준** |
| `history[].pred_price_d5` | number | 당시 예측했던 D+5 종가 |
| `history[].ci_upper` | number | 당시 CI 상단 |
| `history[].ci_lower` | number | 당시 CI 하단 |
| `history[].actual_price_d5` | number \| null | 실제 D+5 종가 (미래면 null) |
| `history[].model_source` | string | 해당 시점 모델 출처 |

---

### 엔드포인트 3 — 실제 주가 히스토리 (두 차트 공통)

```
GET /api/v1/stocks/{ticker}/prices?days=25
```

| 필드 | 타입 | 용도 |
|------|------|------|
| `prices[].date` | string | 날짜 |
| `prices[].close` | number | 실제 종가 |

---

## UI-3. 컴포넌트 A — 최근 1달 성능 검증 차트

### 목적

"모델이 지난 한 달 동안 실제로 얼마나 맞췄는지"를 시각적으로 보여줍니다.  
실제 주가 선 위에 예측 포인트와 오차범위를 겹쳐서 모델 신뢰도를 직관적으로 전달합니다.

### x축 기준 — `target_date` 사용

```
prediction.date        = 2026-05-26  (예측 실행일)
prediction.target_date = 2026-06-02  (D+5, 예측 대상일)

→ x축에는 target_date를 사용해야 실제 주가 선과 날짜가 맞아 비교 가능
→ date(실행일)를 x축으로 쓰면 실제 주가와 5일 어긋남
```

### 화면 구성 요소

| 요소 | 데이터 소스 | 설명 |
|------|------------|------|
| 실제 주가 선 | `/stocks` → `prices[].close` | 연속 라인, x = `date` |
| 예측 포인트 | `/history` → `pred_price_d5` | 마커, x = `target_date` |
| 오차 범위 | `/history` → `ci_upper` / `ci_lower` | 각 포인트에 수직 막대 또는 구간 표시 |
| actual null인 포인트 | `actual_price_d5 === null` | 아직 미래 → 표시 생략 권장 |
| 모델 전환 시점 | `model_source`가 바뀐 날짜 | 세로 점선 또는 색 구분 등 자유롭게 |

### 이 차트의 의미

- CI 80% 신뢰구간이므로 실제 주가가 밴드 안에 드는 비율이 약 80%에 가까우면 모델이 잘 보정된 것입니다.
- 실제 주가가 밴드 밖으로 자주 벗어나면 모델 성능 저하 또는 드리프트 신호입니다.
- 이 차트가 "모델을 지금 믿어도 되는가"를 사용자에게 직접 보여주는 역할을 합니다.

---

## UI-4. 컴포넌트 B — 미래 예측 차트 (구름형 오차범위)

### 목적

오늘 이후 D+5(또는 D+20)까지의 예측을 구름 형태의 CI 밴드와 함께 보여줍니다.

### 데이터 조합 방법

```
실제 주가 히스토리  ← /stocks/{ticker}/prices?days=25
오늘 기준점         ← /predictions/{ticker}/latest → base_price
미래 예측 라인      ← /predictions/{ticker}/latest → forecast[].price
구름형 CI 밴드      ← /predictions/{ticker}/latest → forecast[].ci_upper / ci_lower
```

### 렌더링 분기

```
model_source = 'Choi'  →  forecast 배열 길이 20  →  D+1~D+20 표시
model_source = 'SU'    →  forecast 배열 길이  5  →  D+1~D+5  표시
```

두 경우 모두 차트 구조는 동일합니다. forecast 배열 길이만 다릅니다.

### 화면 구성 요소

| 요소 | 데이터 소스 | 설명 |
|------|------------|------|
| 실제 주가 히스토리 | `/stocks` → `prices[].close` | 오늘까지의 실선 |
| 오늘 기준점 | `base_price` | 히스토리 선과 예측 선의 연결점 |
| 예측 라인 | `forecast[].price` | 오늘 이후 점선 |
| 구름형 CI 밴드 | `forecast[].ci_upper` ~ `forecast[].ci_lower` | fill 영역, 구름 형태 |
| D+5 강조 포인트 | `d5.price` | 예측 종가 수치 표시 권장 |

### CI 밴드 형태 차이

```
Choi (D+1~D+20):
  → CI 폭이 시간이 갈수록 넓어지는 부채꼴 모양
  → 멀리 예측할수록 불확실성이 크다는 것을 솔직하게 표현

SU (D+1~D+5):
  → CI 폭이 균일한 짧은 밴드
  → 5일이라는 단기 예측이라 불확실성이 비교적 균등
```

> 밴드가 넓어지는 것은 버그가 아닙니다. 통계적으로 올바른 표현입니다.

---

## UI-5. 전체 데이터 흐름 요약

```
화면 진입 (종목 선택)
  │
  ├── GET /api/v1/predictions/{ticker}/latest
  │     → forecast[]       미래 예측 라인 + 구름형 CI (차트 B)
  │     → base_price       오늘 종가 기준점 (차트 B)
  │
  ├── GET /api/v1/predictions/{ticker}/history?days=20
  │     → pred_price_d5    과거 예측 포인트 (차트 A)
  │     → ci_upper/lower   과거 CI 오차막대 (차트 A)
  │
  └── GET /api/v1/stocks/{ticker}/prices?days=25
        → close            실제 주가 라인 (차트 A + B 공통)
```

---

## UI-6. 설계 자유도 안내

아래 항목은 **UI 개발자가 자유롭게 결정**해도 됩니다.

- 차트 A, B의 배치 순서 및 크기 비중
- 컬러 팔레트 (Choi/SU 구분 색, 실제/예측 구분 색)
- CI 밴드 투명도 및 질감
- 예측 라인 스타일 (점선, 굵기 등)
- D+5 포인트 강조 방식 (마커 크기, 수치 라벨 위치)
- 모델 전환 시점 표시 방식
- 종목 선택 UI 형태
- 반응형 브레이크포인트

**변경하면 안 되는 부분** (데이터 계약):

- 컴포넌트 A x축: 반드시 `target_date` 사용 (`date` 아님)
- CI 수치: `ci_upper` / `ci_lower` 그대로 사용, 재계산 불필요
- 렌더링 분기: `model_source` 기준으로 Choi(20일) / SU(5일) 구분
- forecast 배열: API가 자동으로 길이 다르게 내려줌, 프론트 계산 불필요

---

---

# PART 3. DAG 코드 구조 최종 정리

> **`airflow/dags/finance_stock_predict_daily.py` 코드를 처음 보는 사람을 위한 안내.**  
> 파일이 길어 보이지만 크게 4개 블록으로 나뉜다.

---

## 블록 1 — 상수 + MODEL_PRIORITY (1~229줄)

파일 상단에 전역 설정값이 있다.

```python
CI_Z             = 1.28   # 80% 신뢰구간 z값 (norm.ppf(0.9))
HORIZON          = 5      # D+5 예측
DRIFT_MULTIPLIER = 1.5    # baseline MAPE × 1.5 → 드리프트 임계값
VOL_DAYS         = 20     # rolling 변동성 계산 기간 (= 약 1달)
MIN_DRIFT_SAMPLES = 5     # 드리프트 감지 시작 최소 이력 수
```

`MODEL_PRIORITY`는 10종목 각각의 1순위·2순위 모델 설정을 담은 dict다.  
DAG가 실행될 때마다 이 dict를 보고 어떤 모델로 예측할지 결정한다.

```python
'105560': {
    'priority_1': {
        'model': 'ARIMA', 'source': 'Choi', 'mape': 1.56,
        'config': { 'order': (3,0,0), 'preprocess': 'log', 'train_window': 'Super_Short' }
    },
    'priority_2': {
        'model': 'LGBMRegressor', 'source': 'SU', 'mape': 7.07,
        'config': { 'pkl': 'su/data/saved_models/105560.pkl', 'features': 9 }
    }
}
```

`mape`는 노트북 백테스트 기준 baseline MAPE(%)로, 드리프트 임계값 계산에만 쓰인다.

---

## 블록 2 — DAG 선언 (244~252줄)

```python
@dag(schedule="30 6 * * 1-5", ...)   # 평일 06:30 UTC = 15:30 KST
def finance_stock_predict_daily():
    ...

finance_stock_predict_daily()   # ← 이 줄이 있어야 Airflow가 DAG를 인식
```

`@dag` 데코레이터로 선언하고 마지막 줄에서 직접 호출해야 Airflow UI에 등록된다.

---

## 블록 3 — `predict_and_save` 태스크 (255~872줄)

10종목이 이 태스크를 각자 병렬로 실행한다.  
helper 함수들이 태스크 내부에 중첩 정의되어 있는데, Airflow 직렬화 문제를 피하기 위한 표준 패턴이다.

### 공통 helper

| 함수 | 역할 |
|------|------|
| `_get_engine()` | Aiven MySQL 연결 (SSL + 환경변수) |
| `_window_start(name)` | `"Super_Short"` → 6개월 전 날짜 등 학습 구간 시작일 계산 |
| `_ci(base, log_ret, vol, h)` | `base × exp(log_ret ± 1.28 × vol × √h)` → (ci_upper, ci_lower) |
| `_rolling_mape()` | `prediction` JOIN `price` → 최근 20거래일 MAPE 반환 |

### Choi 전용 helper

| 함수 | 역할 |
|------|------|
| `_fetch_choi()` | yfinance로 종목 종가 + 외생변수(KOSPI200, WTI, VIX, USDKRW) 수집 |
| `_choi_preprocess()` | raw/log/diff1/ret 등 8종 전처리 |
| `_choi_inverse()` | 예측값을 원래 주가 스케일로 역변환 (cumsum + exp 조합) |
| `_predict_arima(close, cfg)` | ARIMA fit → forecast → 역변환 |
| `_predict_prophet(close, cfg)` | Prophet fit → future predict → 역변환 |
| `_predict_vecm(choi, cfg)` | VECM fit (close + volume + 외생변수 패널) → 역변환 |
| `_run_choi(priority)` | 모델명 보고 위 세 함수 dispatch → `(pred_price_d5, vol, prices_array)` |
| `_build_choi_forecast(prices, base, vol)` | D+1~D+20 배열 구성, 각 시점 CI 계산 (√h로 확장) |

### SU 전용 helper

| 함수/클래스 | 역할 |
|------|------|
| `_RevIN`, `_AdvancedPatchTST` | PatchTST 모델 클래스 (torch) — 추론에만 사용 |
| `_fetch_su()` | pykrx(KOSPI) + FDR(매크로) + MySQL price 테이블로 피처 DataFrame 구성, MSAR 레짐 피처 계산 |
| `_load_su_model(cfg)` | sklearn pkl 또는 PatchTST state_dict 로드 |
| `_su_single_pred(model, df, feat_cols, base_dt, is_patchtst)` | 특정 날짜 기준 D+5 로그수익률 예측 |
| `_run_su(priority)` | 오늘 D+5 예측 + D+1~D+5 롤링 forecast 구성 → `(pred_price_d5, vol, forecast_list)` |

### 메인 플로우 (Step 1~4)

```
Step 1: 1순위 예측
        source='Choi' → _fetch_choi() + _run_choi()
        source='SU'   → _fetch_su()   + _run_su()

Step 2: 드리프트 감지
        _rolling_mape() → rolling_mape > baseline_mape × 1.5?

Step 3: 드리프트 시 2순위 실행
        이미 받아놓은 데이터(choi_data / su_df) 재사용, 재다운로드 없음
        2순위도 임계값 초과 시 retrain_needed = True (DB에만 기록)

Step 4: prediction 테이블 UPSERT
        ON DUPLICATE KEY UPDATE → 같은 날 재실행해도 덮어씀
        실패 시 except에서 {status: 'failed'} dict 반환 (DAG 전체는 계속 실행)
```

---

## 블록 4 — DAG 흐름 (875줄)

```python
predict_and_save.expand(ticker=list(MODEL_PRIORITY.keys()))
```

`expand()`는 Airflow 2.x의 동적 병렬 태스크 생성 방식이다.  
10개 ticker 리스트를 넘기면 `predict_and_save__105560`, `predict_and_save__055550` 등 10개 태스크가 자동 생성된다.  
`max_active_tasks=4`로 동시 실행 수를 제한해 API rate limit을 방지한다.

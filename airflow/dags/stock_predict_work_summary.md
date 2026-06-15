# 주가 예측 시스템 — 작업 현황 및 설계 정리

> 작성일: 2026-06-09  
> 작성자: Choi  
> 목적: 현재까지 완료된 작업 + 앞으로 해야 할 작업 전체 정리

---

## 목차

1. [전체 시스템 구조](#1-전체-시스템-구조)
2. [완료된 작업](#2-완료된-작업)
3. [DAG 파일 구조 설명](#3-dag-파일-구조-설명)
4. [앞으로 해야 할 작업](#4-앞으로-해야-할-작업)
5. [두 DAG 연동 설계](#5-두-dag-연동-설계)
6. [S3 pkl 관리 설계](#6-s3-pkl-관리-설계)
7. [model_config 테이블 설계](#7-model_config-테이블-설계)
8. [finance_model_retrain.py 설계](#8-finance_model_retrainpy-설계)
9. [MySQL 테이블 전체 목록](#9-mysql-테이블-전체-목록)
10. [파일 구현 목록 (전체)](#10-파일-구현-목록-전체)
11. [미결 사항](#11-미결-사항)

---

## 1. 전체 시스템 구조

```
[장 마감 15:30 KST]
        ↓
┌──────────────────────────────────────────────────────┐
│          finance_stock_predict_daily.py               │
│                                                      │
│  predict_and_save (×10 병렬, max 4 동시)              │
│    1. model_config 테이블 읽기 → 강제 전환 여부 확인  │
│    2. S3에서 pkl 다운로드 (SU 모델인 경우)            │
│    3. 1순위 모델로 D+5 예측                           │
│       Choi: yfinance → ARIMA/Prophet/VECM 재학습     │
│       SU:   pkl 로드 → 피처 계산 → predict           │
│    4. MySQL price 테이블 JOIN → rolling MAPE 계산     │
│    5. MAPE > threshold × 1.5 → 드리프트 감지         │
│    6. 드리프트 시 2순위 모델로 재실행                 │
│    7. 2순위도 초과 → retrain_needed = True           │
│    8. prediction 테이블 UPSERT                       │
│    9. retrain_needed=True → TriggerDagRunOperator    │
└──────────────────────────────────────────────────────┘
        ↓ (retrain_needed=True 시만)
┌──────────────────────────────────────────────────────┐
│          finance_model_retrain.py                     │
│                                                      │
│  retrain_model(ticker)                               │
│    ├── SU sklearn 종목                               │
│    │   데이터 수집 → 피처 계산 → refit               │
│    │   → 새 pkl S3 업로드                            │
│    │   → 검증 MAPE 계산                              │
│    │   → 통과: model_config 초기화 (정상 운영 복귀)  │
│    │   → 실패: model_config에 force_priority_2 기록  │
│    │                                                  │
│    └── SU PatchTST 종목 (SK하이닉스/현대차/LG화학)   │
│        model_config에 force_priority_2 기록          │
│        → Choi 2순위로 자동 전환                      │
│        로그: "SU 재학습 후 S3 업로드 시 자동 복구"   │
└──────────────────────────────────────────────────────┘
```

### 의존 DAG

```
finance_market_data_daily.py   ← 반드시 실행되어야 함
  매일 00:00 KST (15:00 UTC)
  → MySQL price 테이블에 10종목 실제 종가 적재
  → 이게 없으면 드리프트 감지 JOIN 불가, SU 피처 계산 불가
```

---

## 2. 완료된 작업

### 2-1. MySQL prediction 테이블 생성

`script/create_prediction_table.py` 실행 완료. Aiven MySQL에 테이블 존재 확인됨.

```sql
CREATE TABLE prediction (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    ticker          VARCHAR(20)   NOT NULL,
    date            DATE          NOT NULL,   -- 예측 실행일
    target_date     DATE          NOT NULL,   -- D+5 날짜
    model_used      VARCHAR(20)   NOT NULL,   -- 'priority_1' | 'priority_2'
    model_name      VARCHAR(50)   NOT NULL,   -- 'ARIMA' | 'Prophet' | 'PatchTST' 등
    model_source    VARCHAR(10)   NOT NULL,   -- 'Choi' | 'SU'
    base_price      DECIMAL(18,4) NOT NULL,
    pred_price_d5   DECIMAL(18,4) NOT NULL,
    pred_return_d5  DECIMAL(10,6) NOT NULL,
    ci_pct          DECIMAL(4,2)  NOT NULL DEFAULT 0.80,
    ci_upper_d5     DECIMAL(18,4) NOT NULL,
    ci_lower_d5     DECIMAL(18,4) NOT NULL,
    vol_20d         DECIMAL(10,6) NOT NULL,
    drift_detected  TINYINT(1)    NOT NULL DEFAULT 0,
    rolling_mape    DECIMAL(8,4),
    threshold       DECIMAL(8,4)  NOT NULL,
    retrain_needed  TINYINT(1)    NOT NULL DEFAULT 0,
    forecast_json   JSON,
    created_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_ticker_date (ticker, date),
    INDEX idx_ticker_target (ticker, target_date),
    INDEX idx_date (date)
);
```

### 2-2. finance_stock_predict_daily.py 작성 완료

`airflow/dags/finance_stock_predict_daily.py`

- 10종목 병렬 예측 (dynamic task mapping)
- Choi: ARIMA / Prophet / VECM (yfinance 매일 재학습)
- SU: sklearn / PatchTST (pkl 로컬 로드)
- 드리프트 감지: rolling 20거래일 MAPE > baseline × 1.5
- CI: 80% (z=1.28, rolling 20일 변동성 기반)
- forecast_json: Choi D+1~D+20, SU D+1~D+5 롤링
- prediction 테이블 UPSERT

### 2-3. 종목별 우선순위 모델 확정

| 종목 | 티커 | 1순위 | 출처 | 2순위 | 출처 |
|------|------|-------|------|-------|------|
| KB금융 | 105560 | ARIMA(3,0,0) | Choi | LGBMRegressor | SU |
| 신한지주 | 055550 | Prophet | Choi | XGBRegressor | SU |
| 한화에어로스페이스 | 012450 | Prophet | Choi | LGBMRegressor | SU |
| 기아 | 000270 | Prophet | Choi | ElasticNet | SU |
| LG화학 | 051910 | Prophet | Choi | PatchTST | SU |
| SK이노베이션 | 096770 | LGBMRegressor | SU | ARIMA(0,0,3) | Choi |
| LIG넥스원 | 079550 | HuberRegressor | SU | VECM | Choi |
| 현대차 | 005380 | Prophet | Choi | PatchTST | SU |
| 삼성전자 | 005930 | ExtraTreesRegressor | SU | Prophet | Choi |
| SK하이닉스 | 000660 | PatchTST | SU | Prophet | Choi |

### 2-4. 드리프트 임계값

| 종목 | baseline MAPE | 임계값 (×1.5) |
|------|--------------|--------------|
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

## 3. DAG 파일 구조 설명

> 자세한 내용은 `stock_predict_dag_plan.md` PART 3 참고.

`finance_stock_predict_daily.py`는 4개 블록으로 구성:

```
블록 1 (1~229줄)    — 상수 + MODEL_PRIORITY dict (10종목 설정)
블록 2 (244~252줄)  — @dag 선언 + 스케줄 설정
블록 3 (255~872줄)  — predict_and_save 태스크
                      ├── 공통: _get_engine, _ci, _rolling_mape
                      ├── Choi: _fetch_choi, _predict_arima/prophet/vecm, _run_choi
                      └── SU:   _fetch_su, _load_su_model, _su_single_pred, _run_su
블록 4 (875줄)      — predict_and_save.expand(ticker=...) 호출
```

---

## 4. 앞으로 해야 할 작업

### 우선순위 순서

```
Step 1. S3에 pkl 업로드 스크립트 작성
Step 2. model_config 테이블 MySQL 생성
Step 3. finance_stock_predict_daily.py 수정
         - S3에서 pkl 다운로드로 변경
         - model_config 읽어서 강제 전환 반영
         - retrain_needed=True 시 TriggerDagRunOperator 추가
Step 4. finance_model_retrain.py 작성
Step 5. 브랜치에 전체 커밋 + 푸시
```

---

## 5. 두 DAG 연동 설계

### 트리거 메커니즘

Airflow의 `TriggerDagRunOperator`를 사용해 DAG 간 연동.

```python
# finance_stock_predict_daily.py 내부
from airflow.operators.trigger_dagrun import TriggerDagRunOperator

@task
def trigger_retrain_if_needed(results: list[dict]):
    retrain_tickers = [r['ticker'] for r in results if r.get('retrain_needed')]
    for ticker in retrain_tickers:
        TriggerDagRunOperator(
            task_id=f"trigger_retrain_{ticker}",
            trigger_dag_id="finance_model_retrain",
            conf={"ticker": ticker},
        ).execute(context={})
```

### 연동 흐름

```
predict_and_save (×10)
        ↓
trigger_retrain_if_needed
  → retrain_needed=True인 종목만 finance_model_retrain DAG 트리거
  → 각 종목별로 별도 DAG run 생성
```

---

## 6. S3 pkl 관리 설계

### S3 경로

```
s3://{BUCKET}/models/su/saved_models/{ticker}.pkl   ← sklearn 7종목
s3://{BUCKET}/models/su/patchtst_v18_model.pkl      ← PatchTST 3종목
```

### 업로드 스크립트 (신규 작성 필요)

`script/upload_su_models_to_s3.py`

```python
# 현재 로컬 pkl → S3 초기 업로드
# 로컬 경로: model/주가예측모델/su/data/saved_models/{ticker}.pkl
# S3 경로:   s3://{BUCKET}/models/su/saved_models/{ticker}.pkl
```

### DAG에서 다운로드

```python
def _load_su_model(cfg: dict, tmp_dir: str) -> tuple:
    import boto3
    s3 = boto3.client('s3')
    pkl_s3_key = cfg['s3_key']           # 'models/su/saved_models/105560.pkl'
    local_path  = Path(tmp_dir) / Path(pkl_s3_key).name
    if not local_path.exists():
        s3.download_file(S3_BUCKET, pkl_s3_key, str(local_path))
    # 이후 기존 로드 로직 동일
```

### SU 재학습 후 배포 흐름

```
SU 팀원: 노트북으로 재학습
    ↓
새 pkl을 S3에 업로드
    ↓
MySQL model_config에서 해당 종목 row 삭제 (또는 force_priority = NULL)
    ↓
다음 날 DAG 실행 시 자동으로 새 pkl 다운로드 → 정상 운영 복귀
```

---

## 7. model_config 테이블 설계

```sql
CREATE TABLE model_config (
    ticker          VARCHAR(20)  NOT NULL PRIMARY KEY,
    force_priority  VARCHAR(20),          -- 'priority_2' | NULL (NULL = 기본값)
    reason          TEXT,                 -- 강제 전환 사유
    retrain_type    VARCHAR(20),          -- 'sklearn' | 'patchtst' | NULL
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                             ON UPDATE CURRENT_TIMESTAMP
);
```

### 사용 예시

```sql
-- PatchTST 드리프트 → Choi 강제 전환 기록
INSERT INTO model_config (ticker, force_priority, reason, retrain_type)
VALUES ('000660', 'priority_2', 'PatchTST drift detected - 수동 재학습 필요', 'patchtst')
ON DUPLICATE KEY UPDATE
    force_priority = 'priority_2',
    reason = VALUES(reason);

-- SU 재학습 완료 후 초기화
DELETE FROM model_config WHERE ticker = '000660';
-- 또는
UPDATE model_config SET force_priority = NULL WHERE ticker = '000660';
```

### finance_stock_predict_daily.py에서 읽는 방법

```python
# 태스크 시작 시 model_config 조회
with engine.connect() as conn:
    row = conn.execute(
        text("SELECT force_priority FROM model_config WHERE ticker = :t"),
        {"t": ticker}
    ).fetchone()
force_priority = row[0] if row else None

# force_priority='priority_2'면 1순위 스킵하고 2순위로 바로 실행
if force_priority == 'priority_2':
    log.info(f"[{ticker}] model_config 강제 전환 → {p2['model']} 사용")
    # 2순위 실행
else:
    # 기존 1순위 로직
```

---

## 8. finance_model_retrain.py 설계

### 스케줄

실행 스케줄 없음 — `finance_stock_predict_daily.py`에서 트리거될 때만 실행.

```python
@dag(
    dag_id="finance_model_retrain",
    schedule=None,          # 수동/트리거 전용
    catchup=False,
    tags=["finance", "retrain"],
)
```

### 태스크 흐름

```
retrain_model(ticker)
    ↓
evaluate_retrained_model(ticker)
    ↓
update_model_config(ticker, result)
```

### retrain_model 로직

```python
@task
def retrain_model(ticker: str) -> dict:
    info    = MODEL_PRIORITY[ticker]
    p1      = info['priority_1']
    p2      = info['priority_2']

    # 재학습 대상 결정
    # - p1이 SU sklearn이면 → sklearn refit
    # - p1이 SU PatchTST이면 → model_config에 force_priority_2 기록 후 종료
    # - p1이 Choi이고 p2가 SU sklearn이면 → p2 sklearn refit
    # - p1이 Choi이고 p2가 PatchTST이면 → force_priority_2 기록 후 종료

    if needs_patchtst_retrain(p1, p2):
        return {'action': 'force_choi', 'ticker': ticker, 'reason': 'PatchTST'}

    # sklearn refit
    df = _fetch_su_data(ticker, engine)
    X, y = _build_xy(df, horizon=5)
    model = _load_su_model_from_s3(ticker)
    model.fit(X, y)
    _upload_pkl_to_s3(model, ticker)

    return {'action': 'retrained', 'ticker': ticker}
```

### PatchTST 종목 처리

```python
def needs_patchtst_retrain(p1, p2) -> bool:
    # 재학습이 필요한 모델이 PatchTST인 경우
    if p1['source'] == 'SU' and p1['model'] == 'PatchTST':
        return True
    if p2['source'] == 'SU' and p2['model'] == 'PatchTST' and drift_on_p1:
        return True
    return False
```

PatchTST 종목 감지 시:

```python
# model_config에 강제 전환 기록
conn.execute(text("""
    INSERT INTO model_config (ticker, force_priority, reason, retrain_type)
    VALUES (:t, 'priority_2', 'PatchTST drift - SU 수동 재학습 필요', 'patchtst')
    ON DUPLICATE KEY UPDATE force_priority='priority_2', reason=VALUES(reason)
"""), {"t": ticker})

log.warning(
    f"[{ticker}] PatchTST 드리프트 감지 → Choi 2순위로 강제 전환.\n"
    f"SU 팀원: 노트북으로 재학습 후 s3://{S3_BUCKET}/models/su/... 에 pkl 업로드,\n"
    f"완료 후 model_config 테이블에서 {ticker} row 삭제하면 자동 복구됨."
)
```

### evaluate_retrained_model 로직

sklearn refit 완료 후 최근 20거래일(1달) 데이터로 MAPE 검증 (드리프트 감지와 동일 기준):

```python
@task
def evaluate_retrained_model(ticker: str, retrain_result: dict) -> dict:
    if retrain_result['action'] == 'force_choi':
        return retrain_result   # PatchTST는 검증 스킵

    # 검증: 최근 20거래일 rolling predict → MAPE (드리프트 감지 기준과 동일)
    mape = _validate_model(ticker)
    p1   = MODEL_PRIORITY[ticker]['priority_1']
    threshold = p1['mape'] * DRIFT_MULTIPLIER

    if mape <= threshold:
        return {'action': 'retrain_success', 'ticker': ticker, 'mape': mape}
    else:
        return {'action': 'force_choi', 'ticker': ticker,
                'reason': f'sklearn retrain 후에도 MAPE {mape:.2f}% > {threshold:.2f}%'}
```

### update_model_config 로직

```python
@task
def update_model_config(ticker: str, eval_result: dict):
    if eval_result['action'] == 'retrain_success':
        # 정상화: model_config row 삭제
        conn.execute(text("DELETE FROM model_config WHERE ticker = :t"), {"t": ticker})
        log.info(f"[{ticker}] 재학습 성공 → model_config 초기화, 정상 운영 복귀")
    else:
        # 강제 전환 유지
        conn.execute(text("""
            INSERT INTO model_config (ticker, force_priority, reason)
            VALUES (:t, 'priority_2', :r)
            ON DUPLICATE KEY UPDATE force_priority='priority_2', reason=VALUES(reason)
        """), {"t": ticker, "r": eval_result['reason']})
        log.warning(f"[{ticker}] {eval_result['reason']} → Choi 강제 전환 유지")
```

### force_priority_2 상태에서 Choi도 drift인 경우

**결정: A안 — Choi 예측값 그냥 저장, 별도 처리 없음**

- Choi(ARIMA/Prophet/VECM)는 매일 yfinance 최신 데이터로 재학습하므로 "재학습"의 의미가 없음
- Choi MAPE 초과 = 해당 종목 자체가 현재 예측하기 어려운 시장 상태 (일시적)
- 3순위 모델 없음 → 있는 것 중 최선인 Choi 예측값 저장
- drift_detected=True, retrain_needed=True는 DB에 기록되므로 운영자가 로그로 파악 가능
- PatchTST 복구는 SU 팀원 수동 처리에 의존 (재학습 완료 + S3 업로드 + model_config row 삭제)

---

## 9. MySQL 테이블 전체 목록

| 테이블 | 역할 | 적재 주체 |
|--------|------|----------|
| `price` | 10종목 일별 실제 종가/거래량 | `finance_market_data_daily.py` |
| `prediction` | D+5 예측값 + CI + 드리프트 이력 | `finance_stock_predict_daily.py` |
| `model_config` | 종목별 강제 모델 전환 상태 | `finance_model_retrain.py` |
| `regime` | 종목별 레짐 구간 정보 | `upload_regime_to_mysql.py` |
| `regime_summary` | 레짐별 LLM 요약 | `upload_regime_to_mysql.py` |

---

## 10. 파일 구현 목록 (전체)

### 완료

| 파일 | 설명 |
|------|------|
| `airflow/dags/finance_stock_predict_daily.py` | 메인 예측 DAG |
| `airflow/dags/stock_predict_dag_plan.md` | 시스템 설계 기획서 (팀 공유용) |
| `airflow/dags/stock_predict_work_summary.md` | 이 파일 — 작업 현황 정리 |
| `script/create_prediction_table.py` | prediction 테이블 생성 |
| `script/upload_regime_to_mysql.py` | regime 데이터 MySQL 업로드 |
| `airflow/dags/finance_market_data_daily.py` | 일별 주가 데이터 적재 (의존 DAG) |

### 작성 예정

| 파일 | 설명 | 우선순위 |
|------|------|---------|
| `script/upload_su_models_to_s3.py` | 로컬 pkl → S3 초기 업로드 | 1 |
| `script/create_model_config_table.py` | model_config 테이블 생성 | 1 |
| `airflow/dags/finance_model_retrain.py` | 재학습 DAG | 2 |
| `finance_stock_predict_daily.py` 수정 | S3 pkl 다운로드 + model_config 읽기 + TriggerDagRunOperator 추가 | 2 |

---

## 11. 미결 사항

| 항목 | 내용 | 담당 |
|------|------|------|
| SU CI 계산 방식 | rolling 변동성 기반으로 구현되어 있음. SU가 "모델 신뢰도 기반"이라고 했다면 수정 필요 | SU 확인 |
| 신한지주 055550 pkl | SU pkl 존재 확인됨 (`saved_models/055550.pkl`) — 정상 | 완료 |
| S3 버킷명 | `S3_BUCKET` 환경변수 설정 필요 (`AWS_BUCKET_NAME` or `.env`) | 인프라 |
| EC2 배포 | Airflow worker에 torch, prophet, lightgbm, pykrx, FinanceDataReader 설치 확인 필요 | 인프라 |
| SU 재학습 트레이닝셋 | sklearn refit 시 어느 기간 데이터를 쓸지 확정 필요 (원래 노트북 기준 참조) | SU 확인 |
| PatchTST 재학습 배포 절차 | 재학습 완료 후 S3 업로드 → model_config 초기화 절차 SU 팀원에게 공유 필요 | Choi → SU |

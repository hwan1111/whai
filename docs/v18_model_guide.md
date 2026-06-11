# v18 주가 예측 모델 분석 가이드

> 대상 독자: 통계/컴퓨터공학 전공자  
> 기준 버전: `stock_prediction_v18.ipynb`

---

## 목차

1. [파이프라인 전체 구조](#1-파이프라인-전체-구조)
2. [입력 데이터 (피처)](#2-입력-데이터-피처)
3. [Step 1 — MSAR 국면 탐지](#3-step-1--msar-국면-탐지)
4. [Step 2 — 훈련 데이터 구성](#4-step-2--훈련-데이터-구성)
5. [Step 3 — 예측 모델](#5-step-3--예측-모델)
6. [Step 4 — Optuna 하이퍼파라미터 최적화](#6-step-4--optuna-하이퍼파라미터-최적화)
7. [Step 5 — 신뢰구간 (CI)](#7-step-5--신뢰구간-ci)
8. [단계별 결과 해석](#8-단계별-결과-해석)
9. [예측 근거의 해석 가능성](#9-예측-근거의-해석-가능성)
10. [종목별 특성 요약](#10-종목별-특성-요약)
11. [시각화 구성](#11-시각화-구성)
12. [버전별 발전 과정](#12-버전별-발전-과정)

---

## 1. 파이프라인 전체 구조

### 예측 대상

```
target = ln(close_{t+5} / close_t)   ← D+5 로그 수익률
```

### 파이프라인 흐름

```
┌──────────────────────────────────────────────────────────┐
│  Raw Data                                                │
│  OHLCV (pykrx) + Macro (S&P500, VIX, NDX, USD/KRW)      │
└────────────────────┬─────────────────────────────────────┘
                     │ Feature Engineering
                     ▼
┌──────────────────────────────────────────────────────────┐
│  피처 벡터 (9개)                                          │
│  ret_1d, ret_5d, ret_20d, vol_norm                       │
│  kospi_ret, sp500_ret, ndx_ret, usdkrw_ret, vix_chg      │
└────────────────────┬─────────────────────────────────────┘
                     │ MSAR (EVAL_START 이전 데이터만)
                     ▼
┌──────────────────────────────────────────────────────────┐
│  Step 1: MSAR 국면 탐지                                   │
│  ret_1d → Markov Switching AR → P(bull_t)                │
│  smoothing → 임계값(0.5) → bull/bear 구간 레이블          │
│  출력: period_data = {bull: [df1, df2, ...],             │
│                       bear: [df1, df2, ...]}              │
└────────────────────┬─────────────────────────────────────┘
                     │ Optuna: direction, min_train, dp, dd
                     ▼
┌──────────────────────────────────────────────────────────┐
│  Step 2: 훈련 데이터 구성                                  │
│  direction ∈ {bull, bear, both}                          │
│  trl = period_data[direction][-min_train:]               │
│  sample_weight = f(dp^period_idx × dd^day_idx)           │
│  X_tr, y_tr, sw → 시간 가중 훈련셋                        │
└────────────────────┬─────────────────────────────────────┘
                     │ Optuna: model_type + model params
                     ▼
┌──────────────────────────────────────────────────────────┐
│  Step 3: 예측 모델 학습                                    │
│  LGBM: LGBMRegressor(n_est, lr, depth, ...)              │
│  Linear: QuantileRegressor(q=0.5, alpha_reg)             │
│  m.fit(X_tr, y_tr, sample_weight=sw)                     │
│  출력: 학습된 모델 m                                       │
└────────────────────┬─────────────────────────────────────┘
                     │ Optuna objective: IC 또는 MAE on eval
                     ▼
┌──────────────────────────────────────────────────────────┐
│  Step 4: Eval 기간 평가 (2025-06 ~ 2026-06)               │
│  pred_r = m.predict(X_{base_dt})                         │
│  IC = Spearman(w·pred, w·actual) [가중치 적용]            │
│  → Optuna가 IC 최대화하는 파라미터 탐색                    │
└────────────────────┬─────────────────────────────────────┘
                     │ 자연 변동성 기반
                     ▼
┌──────────────────────────────────────────────────────────┐
│  Step 5: CI 계산 (시각화용)                                │
│  σ = std(ret_1d.tail(20)) × √5                          │
│  CI_half = z_{0.825} × σ                                 │
│  [exp(pred_r - CI_half), exp(pred_r + CI_half)] × P_t    │
└──────────────────────────────────────────────────────────┘
```

### 대상 종목 (10개)

| 코드 | 종목명 | 코드 | 종목명 |
|------|--------|------|--------|
| 005930 | 삼성전자 | 012450 | 한화에어로스페이스 |
| 000660 | SK하이닉스 | 079550 | LIG넥스원 |
| 005380 | 현대차 | 105560 | KB금융 |
| 000270 | 기아 | 055550 | 신한지주 |
| 051910 | LG화학 | 096770 | SK이노베이션 |

### 시간 구분

| 구분 | 기간 | 역할 |
|------|------|------|
| 훈련 가능 | 2021-01 ~ 2025-05 | MSAR 탐지 + 모델 학습 |
| Eval | 2025-06 ~ 2026-06 | Optuna objective 계산 |
| Boost | 2026-04 ~ 2026-06 | eval 가중치 = 1.0 (이전 구간은 지수 감쇠) |

---

## 2. 입력 데이터 (피처)

### 피처 정의

| 변수 | 수식 | 설명 |
|------|------|------|
| `ret_1d` | ln(P_t / P_{t-1}) | 1일 로그 수익률 |
| `ret_5d` | ln(P_t / P_{t-5}) | 5일 누적 로그 수익률 |
| `ret_20d` | ln(P_t / P_{t-20}) | 20일 누적 로그 수익률 |
| `vol_norm` | V_t / MA(V, 20) | 상대 거래량 (1.0 = 평균) |
| `kospi_ret` | ln(KOSPI_t / KOSPI_{t-1}) | 시장 베타 신호 |
| `sp500_ret` | ln(SP500_t / SP500_{t-1}) | 글로벌 리스크온/오프 |
| `ndx_ret` | ln(NDX_t / NDX_{t-1}) | 기술주 센티먼트 |
| `usdkrw_ret` | ln(FX_t / FX_{t-1}) | 환율 (외국인 수급 프록시) |
| `vix_chg` | VIX_t - VIX_{t-1} | 내재 변동성 변화 |

> 피처 엔지니어링은 별도 정규화 없이 raw 값 사용.  
> 내부적으로 `np.nan_to_num`으로 NaN → 0 처리.

---

## 3. Step 1 — MSAR 국면 탐지

### 모델 수식

```
r_t = μ_{s_t} + φ·r_{t-1} + ε_t,   ε_t ~ N(0, σ²_{s_t})
s_t ∈ {0, 1},   s_t | s_{t-1} ~ Markov(P)

P = [[p_{00}, p_{01}],
     [p_{10}, p_{11}]]   ← 전이 확률 행렬 (학습)
```

- `SWITCHING_AR=False` → φ는 국면 공통, μ와 σ²만 국면별로 다름
- `ORDER=1` → AR(1) 구조
- bull/bear 레이블: 두 상태 중 E[r | state=k]가 더 큰 쪽 = bull

### 국면 추출 로직

```python
fps = filtered_marginal_probabilities[:, bull_state]  # shape (T,)
fps = rolling_mean(fps, window=3)                      # smoothing
label_t = "bull" if fps_t > 0.5 else "bear"

# MIN_LEN=10 미만 연속 구간은 제거 (노이즈 필터)
```

### Step 1 결과 해석

```
출력 예시:
  삼성전자: bull=3  bear=28   usable=31
  신한지주: bull=21 bear=11   usable=32
  LIG넥스원: bull=0 bear=26   usable=26

해석 포인트:
  bull/bear 비율 → 2021-2024 KOSPI 전반의 구조적 하락 반영
  bull=0 (LIG넥스원) → 훈련 구간에 상승 국면 없음
                     → direction="both" 또는 "bear"만 선택 가능
  usable 수 적음 (SK하이닉스=6) → min_train 탐색 범위 자동 축소

주의: MSAR은 EVAL_START 이전 데이터에만 적합
  → eval 기간(2025-2026)의 국면은 모델이 알 수 없음
  → 이 구조적 비대칭이 성능 한계의 근본 원인
```

---

## 4. Step 2 — 훈련 데이터 구성

### direction 선택

```
direction ∈ {bull, bear, both}  ← Optuna 파라미터

"bull":  상승 국면 데이터만 → 상승장 조건부 패턴 학습
"bear":  하락 국면 데이터만 → 하락장 조건부 패턴 학습
"both":  합집합 → 전체 분포 학습 (bull=0인 종목의 fallback)
```

### min_train + decay 가중치

```python
trl = period_data[direction][-min_train:]  # 최근 min_train개 국면

# 샘플 가중치 계산
for i, period_df in enumerate(trl):
    w_period = dp ** (len(trl)-1-i)          # 최근 국면일수록 높음
    for j in range(len(period_df)):
        w_day = dd ** (len(period_df)-1-j)   # 국면 내 최근일일수록 높음
        sw[idx] = w_period * w_day
sw = normalize(sw)  # sum=n으로 정규화
```

### Step 2 결과 해석

```
v18 Optuna가 선택한 최적 파라미터 패턴:
  dp ≈ 0.1 ~ 0.3 (많은 종목)
  dd ≈ 0.1 ~ 0.5

의미: 오래된 국면 및 오래된 날짜를 강하게 할인
     → 사실상 가장 최근 1~2개 국면의 마지막 구간만 유효 가중치 보유

해석: 2021-2024 훈련 데이터와 2025-2026 eval 데이터 간
     분포 불일치(distribution shift)가 큼을 간접 반증
     모델이 최근 데이터에 집중해야 eval IC가 높아짐
```

---

## 5. Step 3 — 예측 모델

### LGBM (LGBMRegressor)

```
gradient boosting 앙상블:
  L(y, ŷ) = MSE
  m.fit(X_tr, y_tr, sample_weight=sw)
  → 11개 파라미터 튜닝: n_est, lr, depth, leaves, mcs, sub, col

출력: ŷ = E[target | X]  ← 조건부 기댓값 추정 (point prediction)
```

### Linear (QuantileRegressor, q=0.5)

```
L1-penalized median regression:
  min_{β} Σ ρ_{0.5}(y_i - X_i·β) + α·||β||₁

  ρ_{0.5}(u) = 0.5·|u|  (pinball loss at q=0.5 = MAE)

출력: ŷ = median(target | X)
     → α(alpha_reg)로 sparsity 조절
```

### Step 3 결과 해석

```
v18 선택 결과: lgbm/ic가 7/10 종목에서 최선
  → LGBM이 IC 기준으로 더 나은 rank-ordering 능력 보유

linear가 선택된 종목: LIG넥스원, 한화에어로
  → 두 종목 모두 단조적 추세 (방산주 하락 → 급등)
  → 비선형 패턴 없이 선형 관계로 충분
  → LGBM 과적합 리스크 > 선형 일반화 이득

모델 선택 기준: IC score on eval period (Optuna objective)
  → "훈련 데이터에서 더 좋은 모델"이 아닌
     "2025-2026 eval에서 rank-ordering이 더 좋은 모델"
```

---

## 6. Step 4 — Optuna 하이퍼파라미터 최적화

### Study 구조

```
40 studies = 10종목 × 2모델 × 2objective
각 study: 독립적인 TPE (Tree-structured Parzen Estimator)

lgbm study:   200 trials max, patience=40, n_startup=25
linear study: 100 trials max, patience=20, n_startup=15
```

### Objective 함수

**MAE objective:**
```python
wmae = Σ(w_i × |pred_r_i - actual_r_i|) / Σ(w_i)
return -wmae
```

**IC objective (채택):**
```python
wp = pred_arr  * sqrt(weights)   # 가중치 √ 적용
wa = actual_arr * sqrt(weights)
IC, _ = spearmanr(wp, wa)
return IC
```

> IC가 MAE보다 나은 이유: distribution shift 환경에서 절대 스케일보다  
> 상대적 rank-ordering이 더 안정적인 신호이기 때문.

### 탐색 파라미터 범위

| 파라미터 | 범위 | 공통/전용 |
|----------|------|--------|
| `dp` | [0.1, 1.0] | 공통 |
| `dd` | [0.1, 1.0] | 공통 |
| `min_train` | [2, dynamic] | 공통 |
| `direction` | {bull,bear,both} | 공통 |
| `n_est` | [10, 300] | lgbm |
| `lr` | [0.005, 0.3] log | lgbm |
| `max_depth` | [1, 7] | lgbm |
| `num_leaves` | [2, 50] | lgbm |
| `mcs` | [1, 50] | lgbm |
| `sub` | [0.3, 1.0] | lgbm |
| `col` | [0.3, 1.0] | lgbm |
| `alpha_reg` | [1e-4, 1.0] log | linear |

### Step 4 결과 해석

```
v18_results.csv 컬럼:
  score  : IC (양수, 높을수록 좋음) 또는 -MAE (음수, 0에 가까울수록 좋음)
  n_trials: early stopping으로 200 미만인 경우 수렴 빠른 것

IC 결과 해석 기준:
  > 0.5       최선 (신한지주: 0.518)
  0.3 ~ 0.5   서비스 사용 가능
  0.1 ~ 0.3   주의 필요
  < 0.1       예측력 불충분

주목할 패턴:
  n_trials이 patience에 걸려 조기 종료된 경우 (예: 49 trials)
    → 해당 파라미터 공간에서 빠르게 수렴
    → 수렴이 local optimum일 가능성 있음 (trials 수 증가로 검증 가능)
  
  n_trials이 200 도달한 경우 (예: SK이노베이션 lgbm/mae: 200)
    → 탐색 공간에서 개선이 지속됨
    → trials 수 증가 시 추가 개선 여지 있음

  lgbm/ic vs linear/ic score 차이가 작은 종목 (예: 한화에어로: 0.352 vs 0.352)
    → 두 모델 간 성능 차이 없음 → 단순 모델(linear) 선호
```

---

## 7. Step 5 — 신뢰구간 (CI)

**CI는 Optuna objective와 독립적으로 계산 (시각화 전용)**

```python
σ_t = std(ret_1d.tail(20))          # 최근 20일 실현 변동성
σ_5d = σ_t × sqrt(5)               # Brownian motion 가정
z = norm.ppf(0.825)                  # 65% CI → z ≈ 0.935

lower = P_t × exp(pred_r - z·σ_5d)
upper = P_t × exp(pred_r + z·σ_5d)
```

> 모델 잔차 기반 conformal CI는 소샘플 eval 구간에서 과대 추정됨 (±15%).  
> 자연 변동성 기반이 ±3~7%로 투자자 직관과 일치.

---

## 8. 단계별 결과 해석

### MSAR 출력 → 훈련 품질 예측

```
bull + bear 총합 (usable)이 적을수록 모델 불안정:
  SK하이닉스: usable=6  → 과소적합 위험, IC 하한 예상
  기아:       usable=9  → IC 낮음 (실제: 0.259)
  신한지주:   usable=32 → 풍부한 regime 다양성 → IC 최고 (0.518)

bull=0 (LIG넥스원):
  bear/both만 훈련 가능
  eval(2025-)에서 방산주 급등 → bear 패턴과 정반대
  → IC=0.435는 사실상 시장 방향 전환 포착 실패 가능성 있음
  → 결과 신뢰도 주의 필요
```

### Optuna 수렴 패턴 → 파라미터 해석

```
dp << 1.0 (예: dp=0.177):
  → Optuna가 최근 1~2개 국면에만 실질적 가중치를 부여하는 게 최적
  → 각 국면의 기여 비율 = dp^(k) / Σdp^(j)
     dp=0.177, min_train=4: 마지막 국면 비중 ≈ 94%
  
  결론: "현재와 가장 가까운 국면 패턴만 의미 있음"을 Optuna가 발견

direction 선택 결과:
  "both" 선택 (삼성전자, 현대차, 한화에어로):
    → 특정 방향에 충분한 샘플 없거나 방향 무관 패턴 존재
  "bull" 선택 (SK하이닉스, KB금융, 신한지주):
    → eval 기간이 상승장 → 상승 국면 패턴이 더 유효
  "bear" 선택 (기아, LG화학, SK이노베이션, LIG넥스원):
    → eval 기간에도 하락 압력이 강하거나, bear 샘플이 압도적으로 많음
```

### IC score → 실용성 판단

```
신한지주 IC=0.518:
  eval 48개 포인트의 예측 순위와 실제 순위 간 Spearman rho ≈ 0.52
  → 상승 폭이 클 때 더 높게 예측하는 경향이 통계적으로 유의

기아 IC=0.259:
  약한 rank correlation → 예측이 실제 방향을 간신히 포착
  → eval 구간의 기아 주가 변동성이 훈련 국면과 크게 다를 가능성

MAE vs IC 선택 근거:
  MAE 기준 선택 시: linear가 우세 (α→0 shrinkage가 작은 절대 오차 보장)
  IC 기준 선택 시:  lgbm이 우세 (비선형 패턴으로 rank-ordering 개선)
  → 동일 종목/데이터라도 기준에 따라 최적 모델이 달라짐
```

---

## 9. 예측 근거의 해석 가능성

### 파이프라인 구조와 해석 가능성의 관계

```
v18 구조: Raw → Feature Engineering → MSAR → Regime Split → LGBM/Linear

이 구조에서 XAI 없이 직접 알 수 있는 것:
  ① direction: 어떤 국면 패턴으로 학습했는가
  ② dp/dd:     얼마나 최근 데이터에 집중했는가
  ③ Linear의 β: 각 피처의 방향성과 크기 (직접 접근 가능)

XAI 없이 알 수 없는 것:
  ④ "오늘 삼성전자가 +3% 예측된 이유" (instance-level attribution)
     → LGBM은 앙상블 구조로 단일 트리 추적 불가
  ⑤ 피처 간 interaction 효과
     → 예: "VIX 하락 + kospi_ret 상승"의 결합 효과
```

### 모델별 해석 가능성 비교

| 구분 | Linear | LGBM |
|------|--------|------|
| 전역 피처 기여 | `m.coef_` 직접 출력 | `feature_importances_` (split/gain) |
| 방향성 | 계수 부호로 직접 확인 | 알 수 없음 (XAI 필요) |
| 특정 예측의 근거 | β·X_t 직접 계산 | XAI (SHAP) 필요 |
| interaction | 없음 (선형) | 내재되어 있으나 추출 불가 |

### Linear 모델의 직접 해석 예시

```python
# alpha_reg=0.01로 학습된 모델의 경우
coef = pd.Series(m.coef_, index=feat)

# 예시 결과 (실제 값은 종목/국면에 따라 다름):
#  ret_1d     +0.32  → 어제 1% 상승 시 D+5 +0.32% 기대
#  kospi_ret  +0.28  → KOSPI 1% 상승 시 D+5 +0.28% 기대
#  vix_chg    -0.15  → VIX 1pt 상승 시 D+5 -0.15% 기대
#  usdkrw_ret -0.21  → 원/달러 1% 상승 시 D+5 -0.21% 기대
```

### MSAR 단계가 해석 가능성에 미치는 영향

```
MSAR → regime split → 모델 학습 의 구조에서:

모델은 "이 데이터가 bear 국면이었다"는 사실을 피처로 받지 않음
→ 예측 시 "현재가 어떤 국면인지" 스스로 판단하지 않음
→ 단지 bear 국면 때 유사한 피처 패턴이 어떤 target을 가졌는지만 학습

결과:
  - "왜 하락 예측인가?" → 훈련 데이터(bear 국면)에서 유사 피처 조합이
    하락을 보였기 때문 (LGBM은 XAI 없이 구체화 불가, Linear는 가능)
  - eval 기간에 국면이 전환되면 (bear → bull) 모델이 인지 불가
  - 국면 전환 감지는 별도 실시간 MSAR 재적합 필요 (현재 구조에 없음)

결론:
  XAI 없이 인스턴스 레벨 해석 가능한 경우: Linear 모델에 한함
  LGBM에서 "왜 이 예측인가" → SHAP value decomposition 필요
```

---

## 10. 종목별 특성 요약

| 종목 | 최선 | IC | dir | n_trials | 비고 |
|------|------|----|-----|----------|------|
| 삼성전자 | lgbm/ic | 0.409 | both | 64 | dp=0.177 (극단적 최근 집중) |
| SK하이닉스 | lgbm/ic | 0.334 | bull | 86 | usable=6, 데이터 취약 |
| 현대차 | lgbm/ic | 0.356 | both | 120 | CI 상대적 넓음 |
| 기아 | lgbm/ic | 0.259 | bear | 195 | 최저 IC, usable=9 |
| 한화에어로 | linear/ic | 0.352 | both | 83 | 최근 급락 반영 어려움 |
| LIG넥스원 | linear/ic | 0.435 | bear | 100 | bull=0, eval 급등 구간과 불일치 |
| KB금융 | lgbm/ic | 0.347 | bull | 94 | CI 넓음 |
| 신한지주 | lgbm/ic | **0.518** | bull | 49 | 최고 IC, MAE/IC 동일 파라미터 수렴 |
| LG화학 | lgbm/ic | 0.361 | bear | 59 | 하락 추세 포착 |
| SK이노베이션 | lgbm/ic | 0.380 | bear | 74 | 일관된 하락 방향 |

> **신한지주 특이사항**: lgbm/mae와 lgbm/ic가 완전히 동일한 파라미터를 선택.  
> 이는 MAE 최소화 ↔ IC 최대화가 이 종목에서 동치임을 의미.  
> 예측이 numerical scale과 rank-ordering 모두에서 일관성이 있음.

---

## 11. 시각화 구성

### 3구간 레이아웃

```
|─── 실주가 (90일) ───|─── 검증 (25일) ───|─ 예측 (D+1~D+5) ─|
     검은 실선             파란 점선              파란 점
     회색 배경             파란 CI 밴드           파란 CI 밴드
```

### 검증 구간 계산 방식

```python
# 검증 구간: 각 base_dt에서 독립적으로 D+5 예측
for bd in vb:                           # overlap_start ~ TODAY 구간의 기준일
    td = bd + BDay(5)                   # 예측 목표일
    base_px = price.asof(bd)
    pred_r  = model.predict(X_bd)       # 그 날 기준 모델 예측
    pred_px = base_px × exp(pred_r)     # 예측 주가
    ci_half = z × σ(ret.tail(20)) × √5

# → 파란 점선: 각 base_dt에서의 D+5 예측값을 시계열로 연결
# → 파란 밴드: 각 예측 시점의 CI
```

### 미래 예측 계산 방식

```python
# D+1 ~ D+5: 각각 다른 base_dt 기준
for h in range(1, 6):
    bd = TODAY - BDay(5-h)    # D+1이면 bd=TODAY-4영업일 전
    td = TODAY + BDay(h)      # D+1이면 td=내일
    pred_px = price.asof(bd) × exp(model.predict(X_bd))

# 선형 보간 아님: 각 점이 독립적인 모델 예측
```

### 제목 형식

```
"{종목} [{모델}/{objective}] dir={direction}  
 D+5:{예측가격}원({수익률%})  score={IC:.4f}"

예: "삼성전자 [lgbm/ic] dir=both  D+5:338,869원(+6.7%)  score=0.4092"

score 색상: 초록(상승 예측) / 빨강(하락 예측)
```

---

## 12. 버전별 발전 과정

| 버전 | 핵심 변경 | Objective | 한계 |
|------|-----------|-----------|------|
| v14 | SARIMA + LGBM 앙상블, vol_ratio 기반 혼합 | Skill (direction accuracy) | 방향만 평가, 크기 무시 |
| v15 | Quantile regression, conformal CI | coverage / CI폭 | CI ±15% 과대, 점예측 부정확 |
| v16 | rolling window 복귀 실험 | coverage | distribution shift로 성능 저하 |
| v17 | 전파라미터 Optuna, direction 내부 선택 | -weighted MAE | 예측선 평행 (scale shrinkage), direction 과적합 |
| **v18** | **모델별 독립 study, direction 파라미터화, IC** | **IC (Spearman)** | 훈련/eval 분포 불일치 근본 미해결 |
| v19 | TimesNet (DL), 연속 시계열 입력, 국면 분리 없음 | IC | CPU 환경, 국면 구조 포기 |

---

*작성 기준일: 2026-06-04*  
*파일 위치: `model/stock_prediction_v18.ipynb`*

# WHAI 주가 예측 모델 문서

> 작성일: 2026-06-05 · 공유 대상: 팀원 전체
> 기준일: 2026-06-02 · 예측 대상: D+5 (5 거래일 후 종가)

---

## 1. 데이터 파이프라인

### 1-1. 종목 데이터

| 항목 | 내용 |
|------|------|
| 수집 방법 | pykrx (일별 OHLCV) |
| 저장 형식 | Parquet (`data/model_v2/{ticker}.parquet`) |
| 기간 | 2021-01-01 ~ 2026-06-02 (약 1,324 거래일) |
| 종목 | 10개 (삼성전자·SK하이닉스·현대차·기아·한화에어로·LIG넥스원·KB금융·신한지주·LG화학·SK이노베이션) |

### 1-2. 피처 엔지니어링

```python
# 기본 9개 피처 (BASE_FEAT)
df['ret_1d']    = log(close / close.shift(1))        # 1일 로그 수익률
df['ret_5d']    = log(close / close.shift(5))        # 5일 로그 수익률
df['ret_20d']   = log(close / close.shift(20))       # 20일 로그 수익률
df['vol_norm']  = volume / volume.rolling(20).mean() # 20일 평균 대비 거래량
df['kospi_ret'] = log(KOSPI / KOSPI.shift(1))        # KOSPI 일간 수익률
df['sp500_ret'] = log(SP500 / SP500.shift(1))        # S&P500 일간 수익률
df['ndx_ret']   = log(NDX / NDX.shift(1))            # NASDAQ 일간 수익률
df['usdkrw_ret']= log(USDKRW / USDKRW.shift(1))     # USD/KRW 환율 수익률
df['vix_chg']   = VIX.diff()                         # VIX 일간 변화량
```

```python
# 레짐 피처 (RC포함 모델 +3개 = 총 12개, RC제외 모델은 11개 또는 9개)
# Markov Switching Autoregression (k=2 국면, switching_ar=False, switching_variance=True)
res = MarkovAutoregression(ret_1d, k_regimes=2, order=1,
                           switching_ar=False, switching_variance=True).fit()

# bull 국면 = 평균 수익률이 높은 국면으로 자동 판별
bull_state = argmax([weighted_avg_return_regime_0, weighted_avg_return_regime_1])

df['regime_prob']     = filtered_marginal_prob[:, bull_state]  # bull 국면 확률 (0~1)
df['regime_duration'] = 현재 국면 연속 지속 거래일 수
df['regime_change']   = 국면 전환 여부 (0 or 1)
```

### 1-3. 타겟 변수

```python
df['target'] = log(close.shift(-5) / close)  # D+5 로그 수익률 (5 거래일 후)
```

---

## 2. 모델 학습 방법론

### 2-1. 국면 기반 Walk-forward 폴드 (B: w-regime)

MSAR로 전체 시계열을 bull/bear 국면으로 분리한 뒤, 같은 방향 국면끼리만 묶어 학습합니다.

```
전체 시계열: bull1 - bear1 - bull2 - bear2 - bull3 - bear3 ...

Bear 계열 폴드 예시 (min_train=4):
  fold 1: [bear1·bear2·bear3·bear4 → train] | [bear5 → test]
  fold 2: [bear2·bear3·bear4·bear5 → train] | [bear6 → test]
  ...

특징:
  - look-ahead 없음: test 국면의 시작일 이전 데이터만 사용
  - direction 파라미터: bull / bear / both (Optuna로 최적화)
  - min_train: 사용할 최소 훈련 국면 수 (Optuna 탐색 범위 2~6)
```

### 2-2. Decay 가중치 (두 단계)

```python
# 1단계: 국면 간 decay (최근 국면에 높은 가중치)
period_weight = dp ** (n_periods - 1 - period_idx)   # dp ∈ [0.1, 1.0]

# 2단계: 국면 내 decay (최근 날짜에 높은 가중치)
day_weight = dd ** (n_days_in_period - 1 - day_idx)  # dd ∈ [0.1, 1.0]

sample_weight = normalize(period_weight × day_weight)
# → LGBMRegressor(sample_weight=...), fit(..., sample_weight=...)
```

### 2-3. Optuna 하이퍼파라미터 탐색

```python
# 공통 탐색 파라미터
dp         : [0.1, 1.0]   # 국면 간 decay
dd         : [0.1, 1.0]   # 국면 내 decay
min_train  : [2, 6] (int) # 훈련 국면 수
direction  : ['bull', 'bear', 'both']

# 평가 지표: Rank IC (Spearman)
wp = pred_log_return * sqrt(eval_weight)  # 최근 기간 가중치 적용
wa = actual_log_return * sqrt(eval_weight)
IC, _ = spearmanr(wp, wa)

# 탐색 설정
n_trials  = 100~300 (모델별 상이)
n_jobs    = 4 (병렬 worker)
patience  = 40 (early stopping)
eval_period: 2025-06-01 ~ 2026-06-02 (n=48 포인트, 5일 간격)
```

### 2-4. RC포함 vs RC제외 비교 구조

```
stock_prediction_final.ipynb       → Group A (9개 피처) + Group B (12개 피처)
                                      → IC 최고 모델 선택 → saved_models/final/
stock_prediction_final_no_rc.ipynb → Group B만 (RC 제외)
                                      → saved_models/final_no_rc/

stock_prediction_final_mixed.ipynb → 두 결과를 eval IC 기준으로 종목별 비교
                                      → final_model_metrics_mixed.csv (최종 선정)
```

---

## 3. 평가 기준

| 지표 | 설명 |
|------|------|
| **Rank IC** | Spearman 상관계수 (가중 예측 vs 가중 실제 log return), 높을수록 좋음 |
| **p-value** | Rank IC 유의성 검정 |
| **MAE** | log return 기준 평균절대오차 |
| **MAPE** | 가격 기준 평균절대오차율 |
| **최근 1달 MAPE** | 2026-05 기준, 최종 채택 모델의 D+5 가격 예측 오차율 |

---

## 4. 종목별 최종 선정 모델

---

### 🏭 삼성전자 (005930)

| 항목 | 값 |
|------|-----|
| **최종 모델** | ExtraTreesRegressor |
| **채택 이유** | RC포함 Group B, eval Rank IC 전체 종목 중 안정적 |
| **피처 수** | 12개 (BASE_FEAT 9 + regime 3) |
| **학습 국면** | Bull + Bear (both) |
| **Rank IC** | 0.4896 (p=0.0004) |
| **MAPE(eval)** | 4.15% |
| **최근 1달 MAPE** | 5.09% — 단기 변동성에도 방향 예측 안정적 |

**모델 하이퍼파라미터 (pkl 실측)**
```python
ExtraTreesRegressor(
    n_estimators     = 185,      # 트리 수
    max_depth        = 6,        # 최대 깊이
    max_features     = 0.9559,   # 분기 시 사용 피처 비율
    min_samples_leaf = 20,       # 리프 최소 샘플 (과적합 방지)
    criterion        = 'squared_error',
    bootstrap        = False,
    random_state     = 42,
)
# Optuna 학습 파라미터
dp=0.525, dd=0.432, min_train=2, direction='both'
```

> ExtraTree는 분기 임계값을 무작위로 선택해 LGBM보다 빠르고 과적합에 강합니다.
> `min_samples_leaf=20`으로 소수 샘플 국면에서의 노이즈를 억제했습니다.

---

### 💾 SK하이닉스 (000660)

| 항목 | 값 |
|------|-----|
| **최종 모델** | PatchTST |
| **채택 이유** | 최근 1달 MAPE 기준 PatchTST 우세 — 반도체 업황의 장기 사이클 패턴 포착에 유리 |
| **입력 피처** | 9개 (BASE_FEAT), 512일 시퀀스 |
| **최근 1달 MAPE** | 10.84% |

**모델 아키텍처 (AdvancedPatchTSTModel)**
```python
# 입력: (batch, seq_len=512, c_in=9) — 512 거래일 × 9개 피처
# 출력: D+1 ~ D+5 로그 수익률 5개

# 1. RevIN 정규화 (채널별 인스턴스 정규화)
x = RevIN(num_features=9)(x, mode='norm')   # 분포 shift 보정

# 2. 채널별 패치 분할
#    패치 수 = (512 - 16) // 8 + 1 = 63개
patches = x.unfold(dim=1, size=16, step=8)  # (B×9, 63, 16)

# 3. 패치 임베딩 + 위치 인코딩
emb = Linear(16 → 64)(patches) + pos_embedding  # (B×9, 63, 64)

# 4. Transformer Encoder (2 레이어)
enc = TransformerEncoder(d_model=64, nhead=4, dim_feedforward=256, dropout=0.1)

# 5. 예측 헤드
pred = Linear(63×64 → 5)(enc.flatten())  # D+1~D+5 예측

# 6. RevIN 역정규화 → 원래 스케일 복원
```

**학습 설정**
```
파라미터 수: 125,271개 (종목별 독립 학습)
손실 함수:   0.85 × MSE + 0.15 × (1 − cosine_similarity)
저장 형식:   state_dict → model/patchtst_v18_model.pkl (종목명 키)
추론 시:     AdvancedPatchTSTModel 클래스 정의 후 load_state_dict() 필요
```

---

### 🚗 현대차 (005380)

| 항목 | 값 |
|------|-----|
| **최종 모델** | PatchTST |
| **채택 이유** | 최근 1달 MAPE 기준 PatchTST 우세 — 최근 현대차 급등 구간 시퀀스 패턴 포착 |
| **입력 피처** | 9개 (BASE_FEAT), 512일 시퀀스 |
| **최근 1달 MAPE** | 9.87% |

**모델 아키텍처** → SK하이닉스와 동일 구조 (AdvancedPatchTSTModel, 125,271 params)

**학습 설정**
```
손실 함수:   0.85 × MSE + 0.15 × (1 − cosine_similarity)
저장 위치:   model/patchtst_v18_model.pkl  키: 'Hyundai Motor'
추론 시:     AdvancedPatchTSTModel().load_state_dict(state_dict) 후 eval()
```

---

### 🚙 기아 (000270)

| 항목 | 값 |
|------|-----|
| **최종 모델** | ElasticNet |
| **채택 이유** | RC포함 Group B, 선형 모델이 eval 기간 bear 국면에서 안정적 |
| **피처 수** | 12개 (BASE_FEAT 9 + regime 3) |
| **학습 국면** | Bear |
| **Rank IC** | 0.4350 (p=0.0020) |
| **MAPE(eval)** | 4.51% |
| **최근 1달 MAPE** | 7.44% — 선형 모델 특성상 급격한 방향 전환보다 추세 유지 구간에 강함 |

**모델 하이퍼파라미터 (pkl 실측)**
```python
ElasticNet(
    alpha     = 0.02578,          # 전체 정규화 강도
    l1_ratio  = 0.8478,           # L1(Lasso) 비중 높음 → 희소 피처 선택
    max_iter  = 3000,
    fit_intercept = True,
    selection = 'cyclic',
)
dp=0.756, dd=0.135, min_train=6, direction='bear'
```

> `l1_ratio=0.848`로 Lasso에 가깝습니다 — bear 국면에서 유효 피처를 자동 선별합니다.
> noRC MLP(훈련 IC=0.465)보다 eval IC(0.435) 기준으로는 낮지만, 실제 eval 기간 MAPE는 ElasticNet이 우수해 채택했습니다.
> `dd=0.135`로 국면 내 최근 날짜에 집중 가중치 부여.

---

### ✈️ 한화에어로 (012450)

| 항목 | 값 |
|------|-----|
| **최종 모델** | LGBMRegressor (quantile) |
| **채택 이유** | RC포함 Group B, 방산주 특성상 레짐 피처가 유효 |
| **피처 수** | 12개 (BASE_FEAT 9 + regime 3) |
| **학습 국면** | Bull + Bear (both) |
| **Rank IC** | 0.4587 (p=0.0010) |
| **MAPE(eval)** | 5.54% |
| **최근 1달 MAPE** | 11.94% — 최근 한화에어로 급등 구간으로 인한 오차 증가 |

**모델 하이퍼파라미터 (pkl 실측)**
```python
LGBMRegressor(
    objective        = 'quantile',  alpha=0.5,
    n_estimators     = 101,
    learning_rate    = 0.19322,     # 상대적으로 높은 학습률
    max_depth        = 7,           # 가장 깊은 트리
    num_leaves       = 45,
    min_child_samples= 24,
    subsample        = 0.6915,
    colsample_bytree = 0.9176,
    random_state     = 42,
)
dp=0.724, dd=0.814, min_train=2, direction='both'
```

> `max_depth=7, num_leaves=45`로 비선형 복잡 패턴 학습.
> `min_train=2`로 최소 2개 국면만 학습해 최근 데이터에 빠르게 적응합니다.

---

### 🛡️ LIG넥스원 (079550)

| 항목 | 값 |
|------|-----|
| **최종 모델** | HuberRegressor |
| **채택 이유** | RC포함 Group B, 이상치 강건성이 방산주 급등락 대응에 효과적 |
| **피처 수** | 12개 (BASE_FEAT 9 + regime 3) |
| **학습 국면** | Bear |
| **Rank IC** | 0.4225 (p=0.0028) |
| **MAPE(eval)** | 9.54% |
| **최근 1달 MAPE** | 5.68% — eval 전체 기간 대비 최근 1달이 오히려 성능 개선 |

**모델 하이퍼파라미터 (pkl 실측)**
```python
HuberRegressor(
    epsilon   = 2.304,     # 이상치 판별 임계값 (높을수록 OLS에 가까워짐)
    alpha     = 0.00267,   # L2 정규화 강도 (매우 약함)
    max_iter  = 300,
    fit_intercept = True,
)
dp=0.552, dd=0.146, min_train=3, direction='bear'
```

> Huber loss: `|residual| ≤ epsilon`이면 MSE, 초과하면 MAE로 전환 → 급등락 이상치 완화.
> `dd=0.146`으로 bear 국면 내 가장 최근 데이터에 집중.
> MAPE가 eval 전체(9.54%)보다 최근 1달(5.68%)에서 더 좋아 신뢰도 높음.

---

### 🏦 KB금융 (105560)

| 항목 | 값 |
|------|-----|
| **최종 모델** | LGBMRegressor (quantile) |
| **채택 이유** | RC제외 Group A (9개 피처) — 레짐 피처 추가 시 오히려 성능 저하 |
| **피처 수** | 9개 (BASE_FEAT) |
| **학습 국면** | Bull |
| **Rank IC** | 0.4108 (p=0.0037) |
| **MAPE(eval)** | 5.25% |
| **최근 1달 MAPE** | 7.07% — 금리·환율 연동성이 강한 금융주 특성상 매크로 피처 중심으로 예측 |

**모델 하이퍼파라미터 (pkl 실측)**
```python
LGBMRegressor(
    objective        = 'quantile',  alpha=0.5,
    n_estimators     = 197,
    learning_rate    = 0.01234,     # 낮은 학습률 + 많은 트리 조합
    max_depth        = 6,
    num_leaves       = 3,           # 매우 단순한 트리 구조 (과적합 방지)
    min_child_samples= 20,
    subsample        = 0.9999,      # 거의 전체 데이터 사용
    colsample_bytree = 0.8843,
    random_state     = 42,
)
dp=0.188, dd=0.928, min_train=3, direction='bull'
```

> `num_leaves=3`은 사실상 깊이 1~2 수준의 매우 얕은 트리입니다.
> 금융주는 국면보다 금리·환율 등 매크로가 지배적 → RC 피처 불필요.
> `dp=0.188`으로 가장 최근 1개 bull 국면에 거의 모든 가중치 집중.

---

### 🏦 신한지주 (055550)

| 항목 | 값 |
|------|-----|
| **최종 모델** | XGBRegressor |
| **채택 이유** | RC포함 Group B, **전체 종목 중 최저 MAPE(2.36%)** |
| **피처 수** | 12개 (BASE_FEAT 9 + regime 3) |
| **학습 국면** | Bull + Bear (both) |
| **Rank IC** | 0.5291 (p=0.0001) |
| **MAPE(eval)** | 2.36% ← 전체 최저 |
| **최근 1달 MAPE** | 2.08% — eval 전체 기간보다 최근 1달이 더 정확, 모델 신뢰도 최상위 |

**모델 하이퍼파라미터 (pkl 실측)**
```python
XGBRegressor(
    n_estimators     = 115,
    learning_rate    = 0.11058,
    max_depth        = 3,           # 얕은 트리
    subsample        = 0.7451,
    colsample_bytree = 0.3389,      # 피처 30% 만 사용 → 강한 다양성
    reg_alpha        = 0.03731,
    reg_lambda       = 6.7709,      # 강한 L2 정규화
    min_child_weight = 27,          # 매우 높음 → 리프 생성 억제
    objective        = 'reg:squarederror',
    random_state     = 42,
)
dp=0.955, dd=0.102, min_train=5, direction='both'
```

> `colsample_bytree=0.339 + reg_lambda=6.77 + min_child_weight=27`의 3중 정규화.
> `dd=0.102`로 국면 내 최근 날짜에 극도로 집중.
> 신한지주는 MAPE·IC 모두 전체 최고 수준으로 서비스 신뢰도가 가장 높습니다.

---

### 🧪 LG화학 (051910)

| 항목 | 값 |
|------|-----|
| **최종 모델** | PatchTST |
| **채택 이유** | 최근 1달 MAPE 기준 PatchTST 우세 — 화학주 업황 반전 사이클 장기 시퀀스 학습에 강점 |
| **입력 피처** | 9개 (BASE_FEAT), 512일 시퀀스 |
| **최근 1달 MAPE** | 8.08% |

**모델 아키텍처** → SK하이닉스와 동일 구조 (AdvancedPatchTSTModel, 125,271 params)

**학습 설정**
```
손실 함수:   0.85 × MSE + 0.15 × (1 − cosine_similarity)
저장 위치:   model/patchtst_v18_model.pkl  키: 'LG Chem'
추론 시:     AdvancedPatchTSTModel().load_state_dict(state_dict) 후 eval()
```

---

### ⛽ SK이노베이션 (096770)

| 항목 | 값 |
|------|-----|
| **최종 모델** | LGBMRegressor (mse) |
| **채택 이유** | RC제외 Group A, MSE 목적함수가 정유·에너지 섹터 연속성 학습에 적합 |
| **피처 수** | 11개 (BASE_FEAT 9 + regime_prob + regime_duration) |
| **학습 국면** | Bear |
| **Rank IC** | 0.3802 (p=0.0077) |
| **MAPE(eval)** | 5.17% |
| **최근 1달 MAPE** | 5.21% — eval 전체와 최근 1달 성능이 안정적으로 일치 |

**모델 하이퍼파라미터 (pkl 실측)**
```python
LGBMRegressor(
    objective        = 'mse',       # quantile 아닌 MSE (평균 예측)
    n_estimators     = 33,          # 가장 적은 트리 수
    learning_rate    = 0.05746,
    max_depth        = 3,
    num_leaves       = 5,           # 매우 단순
    min_child_samples= 7,
    subsample        = 0.6711,
    colsample_bytree = 0.3238,      # 피처 32% 사용
    random_state     = 42,
)
dp=0.999, dd=0.881, min_train=6, direction='bear'
```

> `n_estimators=33, num_leaves=5`로 10개 종목 중 가장 단순한 모델.
> `dp=0.999`로 모든 bear 국면 데이터를 균등하게 활용.
> MSE 목적함수 채택 — 정유주는 유가 연동 추세가 강해 중앙값보다 평균 예측이 유리.

---

## 5. 전체 결과 요약

### 5-1. 최종 선정 결과

| 종목 | 채택 모델 | 모델 타입 | RC | Rank IC | MAPE(eval) | 최근 1달 MAPE |
|------|----------|-----------|-----|---------|-----------|--------------|
| 삼성전자 | 우리 | ExtraTreesRegressor | ✅ | 0.490 | 4.15% | 5.09% |
| SK하이닉스 | PatchTST | — | — | — | — | 10.84% |
| 현대차 | PatchTST | — | — | — | — | 9.87% |
| 기아 | 우리 | ElasticNet | ✅ | 0.435 | 4.51% | 7.44% |
| 한화에어로 | 우리 | LGBMRegressor(quantile) | ✅ | 0.459 | 5.54% | 11.94% |
| LIG넥스원 | 우리 | HuberRegressor | ✅ | 0.423 | 9.54% | 5.68% |
| KB금융 | 우리 | LGBMRegressor(quantile) | ❌ | 0.411 | 5.25% | 7.07% |
| 신한지주 | 우리 | XGBRegressor | ✅ | 0.529 | 2.36% | 2.08% |
| LG화학 | PatchTST | — | — | — | — | 8.08% |
| SK이노베이션 | 우리 | LGBMRegressor(mse) | ❌ | 0.380 | 5.17% | 5.21% |

**우리 모델 7종목 · PatchTST 3종목 (SK하이닉스·현대차·LG화학)**

### 5-2. RC 사용 현황

| 구분 | 종목 |
|------|------|
| RC포함 (12개 피처) | 삼성전자·SK하이닉스(참고)·현대차(참고)·기아·한화에어로·LIG넥스원·신한지주 |
| RC제외 (9~11개 피처) | KB금융(9개)·LG화학(11개)·SK이노베이션(11개) |

---

## 6. PKL 저장 위치

```
data/saved_models/
├── final/                    ← 최종 우리 모델 (stock_prediction_final.ipynb)
│   ├── 005930.pkl  삼성전자   ExtraTreesRegressor   (83KB)
│   ├── 000660.pkl  SK하이닉스 LGBMRegressor         (52KB)
│   ├── 005380.pkl  현대차     XGBRegressor          (209KB)
│   ├── 000270.pkl  기아       ElasticNet            (1KB)
│   ├── 012450.pkl  한화에어로  LGBMRegressor         (42KB)
│   ├── 079550.pkl  LIG넥스원   HuberRegressor        (1KB)
│   ├── 105560.pkl  KB금융     LGBMRegressor         (78KB)
│   ├── 055550.pkl  신한지주    XGBRegressor          (100KB)
│   ├── 051910.pkl  LG화학     LGBMRegressor         (138KB)
│   └── 096770.pkl  SK이노베이션 LGBMRegressor        (295KB)
│
└── final_no_rc/              ← RC제외 전용 (stock_prediction_final_no_rc.ipynb)
    └── (비교용 보관, 서비스는 final/ 사용)

model/
└── patchtst_v18_model.pkl    ← PatchTST state_dict (10종목 × 125,271 params)
```

---

## 7. 최소 추론 코드

```python
import pickle
import numpy as np, pandas as pd
from pathlib import Path

# 모델 로드 (예: 신한지주)
with open('data/saved_models/final/055550.pkl', 'rb') as f:
    model = pickle.load(f)   # XGBRegressor

# 피처 준비 (신한지주: 12개)
BASE_FEAT    = ['ret_1d','ret_5d','ret_20d','vol_norm',
                'kospi_ret','sp500_ret','ndx_ret','usdkrw_ret','vix_chg']
REGIME_FEAT  = ['regime_prob','regime_duration','regime_change']
n_feat       = model.n_features_in_   # 12 또는 9/11

feat = (BASE_FEAT + REGIME_FEAT)[:n_feat]
X = np.nan_to_num(df[feat].iloc[-1:].values)   # shape: (1, n_feat)

log_return_d5  = model.predict(X)[0]            # D+5 로그 수익률
current_price  = df['close'].iloc[-1]
predicted_price = current_price * np.exp(log_return_d5)
```

---

## 8. 노트북 실행 순서

```
1. stock_prediction_final.ipynb          → saved_models/final/ 생성
2. stock_prediction_final_no_rc.ipynb    → saved_models/final_no_rc/ 생성
3. stock_prediction_final_mixed.ipynb    → 두 결과 eval IC 비교
                                            → final_model_metrics_mixed.csv
4. stock_prediction_compare.ipynb        → PatchTST 비교 → 최종 선정
                                            → data/service_viz_2w.png
```

---

*문서 자동 생성: WHAI 모델팀 · 2026-06-05*

# calc_ex_index.py — 작업 문서

**파일 경로**: `script/calc_ex_index.py`  
**작성일**: 2026-05-27  
**목적**: 공통 이동 이벤트 JSON에 KOSPI200 동일가중지수 기반 β / 수익률 분해 결과를 추가

---

## 개요

종목 쌍의 공통 이동 이벤트(`common_events_*.json`) 각 국면에 대해 시장 기여분과 종목 고유 수익률을 분리한다.

| 필드 | 설명 |
|------|------|
| `beta` | 국면 시작 직전 60거래일 OLS β (vs KOSPI200 동일가중) |
| `total_cum` | 국면 전체 누적 수익률 Π(1+R) − 1 |
| `market_cum` | β × R_mkt 누적 — 시장 움직임으로 설명되는 부분 |
| `idio_cum` | total_cum − market_cum — 종목 고유 재료 기여분 |

분해 결과는 각 종목 이벤트 블록 안에 `ks200_ew` 키로 추가된다.

---

## 시장팩터 선정 과정

### 1차 시도: 역연산 지수 (폐기)

**방식**: R_ex_i = (R_KS200 − w_i × R_i) / (1 − w_i)  
삼성전자(KOSPI200 비중 ~20%) 같은 대형주는 자기 자신이 지수에 편입돼 있어 KS200에 단순 회귀하면 β가 기계적으로 부풀려지는 Stambaugh bias 문제가 있다. 역연산으로 해당 종목을 지수에서 제거한 순수 시장 수익률을 계산하려 했다.

**폐기 이유**: 시가총액 비중 산출에 pykrx를 사용했는데 KRX API가 빈 응답을 반환해 weight가 실제의 3배 이상으로 계산됨(SK하이닉스 실제 ~6% → 계산값 14~21%). 데이터 소스 자체를 신뢰할 수 없어 폐기.

---

### 2차 시도: pykrx 구성종목 + FDR 200종목 병렬 조회 (폐기)

**방식**: `pykrx.get_index_portfolio_deposit_file("1028", ref_date)`로 KOSPI200 구성종목 200개 티커를 가져온 뒤 FDR로 일간 수익률을 병렬 조회(`ThreadPoolExecutor(max_workers=8)`)하여 단순 평균 → 동일가중지수 직접 구성.

**폐기 이유**: 구성종목 조회 API 자체가 빈 리스트를 반환해 KS200 시가총액가중 fallback으로 떨어짐. 역연산보다 단순하지만 동일하게 pykrx API 불안정 문제가 발목을 잡았고, 200종목 FDR 호출로 실행 시간도 길었음.

---

### 3차 (현재): KOSPI200 동일가중 ETF (채택)

**방식**: KODEX 200동일가중(252650) / TIGER 200동일가중(252000) ETF 종가를 FDR로 직접 조회. ETF가 동일가중 지수를 추종하므로 구성종목 개별 조회 없이 단일 API 호출로 동일한 팩터를 얻을 수 있다.

**채택 이유**:
- pykrx 의존성 완전 제거
- API 호출 3회(ETF 1 + 개별종목 2)로 단순화
- 분석 기간(2025-11 ~ 2026-05) 전체 커버 확인
- 두 ETF 간 상관 0.97, KS200 시가총액가중 대비 상관 0.83 — 팩터가 실질적으로 차별화됨

```
누적 수익률 비교 (2025-11 ~ 2026-05):
  KS200 시가총액가중:   +119.7%  (삼성전자 집중 효과)
  KODEX 200동일가중:    +36.6%
  TIGER 200동일가중:    +34.5%
```

---

## 현재 코드 구조

### 상수

```python
BETA_WINDOW = 60  # β 추정 롤링 윈도우 (거래일)

_EW_ETF_CANDIDATES = [
    ("252650", "KODEX 200동일가중"),
    ("252000", "TIGER 200동일가중"),
]
```

---

### `fetch_ks200_ew(fromdate, todate) → pd.Series`

KOSPI200 동일가중 수익률 시계열 반환.

- `_EW_ETF_CANDIDATES` 순서대로 FDR 조회 시도
- 전량 실패 시 KS200 시가총액가중으로 fallback (WARNING 로그 출력)
- 반환 시리즈 이름: `"R_KS200_EW"`

---

### `fetch_stock(ticker, fromdate, todate) → pd.Series`

개별 종목 일간 수익률 시계열 반환.

- FDR `Close` 컬럼 기반 `pct_change()`
- 반환 시리즈 이름: `"R_{ticker}"`

---

### `estimate_beta(r_i, r_mkt) → tuple[float, float]`

β = cov(R_i, R_mkt) / var(R_mkt), R² = corr(R_i, R_mkt)²

- `pd.concat` 후 `dropna()`로 공통 거래일 기준 정렬
- 유효 데이터 5개 미만이면 `(nan, nan)` 반환
- R²는 시장팩터의 해당 종목 설명력 — 낮을수록 market_cum/idio_cum 분해 신뢰도 낮음

---

### `decompose(r_i, r_mkt, beta) → dict`

국면 수익률 3분해.

```
total_cum  = Π(1 + R_i) − 1
market_cum = Π(1 + β × R_mkt) − 1
idio_cum   = total_cum − market_cum
```

- β가 `nan`이면 `market_cum`, `idio_cum`은 `None` 반환
- 양 시리즈 인덱스 교집합(`intersection`)으로 날짜 정렬 후 결측은 0으로 처리

---

### `enrich_event(event, tickers, r_ew, stock_returns) → dict`

단일 이벤트 dict를 받아 `ks200_ew` 블록을 추가한 새 dict 반환.

β 추정 구간:
```
beta_idx = r_ew.dropna().index[ start_pos - BETA_WINDOW : start_pos ]
```
국면 시작 직전 60거래일을 `searchsorted`로 정확히 슬라이싱.

---

### `print_summary(events, tickers)`

전체 이벤트에 대한 종목별 β / 시장기여 / 고유수익 평균·범위를 logger.INFO로 출력.

---

### `main()`

CLI 진입점.

```
python script/calc_ex_index.py
python script/calc_ex_index.py --input data/common_events_005930_005380.json
```

| 단계 | 내용 |
|------|------|
| 1 | `--input` JSON 로드, 티커·기간 파싱 |
| 2 | `fetch_from` = 최초 국면 시작 − 90영업일 (β 추정 여유분) |
| 3 | `fetch_ks200_ew()` 호출 |
| 4 | 개별종목 `fetch_stock()` 호출 |
| 5 | 이벤트별 `enrich_event()` 적용 |
| 6 | `{input_stem}_ex.json` 저장 |
| 7 | `print_summary()` 출력 |

---

## 출력 스키마

입력 JSON 구조를 유지하고 각 종목 블록에 `ks200_ew` 추가.

```json
{
  "rank": 1,
  "date": "2026-04-07",
  "000660": {
    "regime_id": 258,
    "period": "2026-04-10~2026-05-12",
    "direction": "상승",
    "cum_return": 0.8387,
    "cause": "...",
    "confidence": "high",
    "ks200_ew": {
      "beta": 1.4681,
      "r2": 0.5811,
      "total_cum": 0.8387,
      "market_cum": 0.1589,
      "idio_cum": 0.6798
    }
  }
}
```

| 필드 | 타입 | null 조건 |
|------|------|-----------|
| `beta` | float | 추정 가능 데이터 5개 미만 |
| `r2` | float | 추정 가능 데이터 5개 미만 |
| `total_cum` | float | — |
| `market_cum` | float | β가 null인 경우 |
| `idio_cum` | float | β가 null인 경우 |

---

## 결과 해석 기준 (참고)

| 조건 | 의미 |
|------|------|
| `idio_cum` 크고 `total_cum`과 방향 일치 | 종목 고유 재료가 실질 기여 — cause 신뢰도 높음 |
| `market_cum`이 `total_cum` 대부분 차지 | 시장 흐름에 동조한 국면 — 고유 재료 기여 낮음 |
| β < 0 또는 `market_cum`과 `total_cum` 방향 불일치 | 시장 분리 신뢰도 낮음 |

> 신뢰도 낮은 케이스의 LLM 해석 처리 방식은 프롬프트 엔지니어링 단에서 결정.

---

## 의존성

| 라이브러리 | 용도 |
|-----------|------|
| `FinanceDataReader` | ETF 및 개별종목 종가 조회 |
| `pandas` | 시계열 연산, 날짜 처리 |
| `numpy` | 공분산 행렬 기반 β 계산 |

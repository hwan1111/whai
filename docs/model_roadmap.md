# 주가 예측 모델 향후 작업 계획

## 현재 상태 요약

| 항목 | 결과 |
|---|---|
| 최고 성능 모델 | SARIMA per-ticker (LG화학 Skill +0.128, SK이노베이션 +0.128) |
| LightGBM | TAB 35개 피처 노이즈 확인, SARIMA에 패배 |
| CI 방식 | 고정 커버리지→폭 도출 방식의 한계 확인 |
| 멘토 확인 | 롤링 윈도우 타당, 8:2 비율 수정 필요, 장기 horizon 탐색 권장 |

---

## Phase 1. 공통 기반 정리 (DL 무관)

### 1-1. Fold 구조 수정
```
현재: 9-fold (F5/F6 세분화 → 비율 붕괴)
수정: 6-fold, 2년 롤링, 6개월 테스트 (8:2 유지)

F1: Train 2021-01~2023-06  Test 2023-07~2023-12
F2: Train 2022-01~2023-12  Test 2024-01~2024-06
F3: Train 2022-07~2024-06  Test 2024-07~2024-12
F4: Train 2023-01~2024-12  Test 2025-01~2025-06
F5: Train 2023-07~2025-06  Test 2025-07~2025-12
F6: Train 2024-01~2025-12  Test 2026-01~2026-05
```

### 1-2. CI 방식 전환
```
현재: 커버리지 목표(90%) → 폭 도출 (의미 모호)
수정: 폭 고정 → 커버리지 측정

"±3% 밴드: 실주가 포함 비율 X%"
"±5% 밴드: 실주가 포함 비율 Y%"
"±10% 밴드: 실주가 포함 비율 Z%"
```

### 1-3. LightGBM 피처 필터링
```
현재: TAB 35개 (노이즈 확인됨)
방법: fold별 Feature Importance 집계 → 하위 50% 제거
목표: Hybrid(SARIMA + filtered LightGBM)가 SARIMA 단독을 이기는지 확인
```

### 1-4. 장기 Horizon 탐색
```
D+20 (1개월): 섹터/거시 피처 신호 유효 구간 가능성
D+60 (3개월): PER/PBR 밸류에이션 신호 구간
평가 기준: AlwaysUp Skill > 0.07 (통계적 유의 최소선)
```

---

## Phase 2. 분기점 — DL 도입 여부 결정

```
Phase 1 완료 후 판단 기준:

Hybrid(SARIMA + filtered LightGBM) Skill ≥ 0.07
  → Branch A (ML 완성)

Hybrid Skill < 0.07, 장기 horizon도 개선 없음
  → Branch B (DL 도입)

두 조건 모두 만족
  → Branch A 완성 후 Branch B 병행
```

---

## Branch A. DL 미도입 — ML 기반 서비스 완성

### A-1. 모델 확정
```
고성능 종목 (Skill ≥ 0.07): SARIMA 단독 또는 Hybrid
저성능 종목 (Skill < 0.07): CI 밴드만 제공 (방향 예측 없음)
```

### A-2. 서비스 설계
```
제공 정보:
  - 예측 방향 (유효 종목만)
  - 고정 폭 CI 밴드 (±3/5/10% 커버리지)
  - 종목별 불확실성 지표 (밴드 폭 비교)

제공 안 함:
  - 정확한 예측 가격선 (랜덤워크 한계 명시)
```

### A-3. Airflow 파이프라인 연동
```
매일 장 마감 후:
  1. 신규 OHLCV + 거시경제 수집
  2. SARIMA 모델 rolling update
  3. D+5 예측 + CI 계산
  4. DB 적재 → 프론트 렌더링
```

---

## Branch B. DL 도입

### B-0. 전제 조건
```
1. SARIMA 단독 베이스라인 확정 (Skill 기록)
2. Phase 1 피처 필터링 완료
3. "Zeng et al. 2023" 결론 인지
   → 단순 선형 모델이 Transformer를 이기는 경우 多
   → 복잡도 증가 ≠ 성능 향상 보장
```

### B-1. 도입 모델 후보
```
우선순위:
  1순위: N-BEATS / N-HiTS
         (Transformer 아닌 순수 DL, 해석 가능, 빠름)
  2순위: Temporal Fusion Transformer (TFT)
         (멀티호라이즌, 피처 활용, 해석 가능)
  3순위: PatchTST
         (Transformer이지만 패치 단위로 순서 보존)

비추천:
  Informer / Autoformer: Zeng et al.에서 DLinear에 패배 확인
```

### B-2. 평가 프로토콜
```
v6 노트북:
  SARIMA vs N-BEATS vs TFT vs Hybrid(DL + SARIMA)
  동일 fold (6-fold, 8:2), 동일 종목
  기준: Skill > SARIMA 단독이어야 도입 의미 있음
```

### B-3. 결과별 분기
```
DL > SARIMA (Skill 기준):
  → SARIMA + DL Hybrid 최종 모델
  → Airflow에 DL 재학습 파이프라인 추가

DL ≤ SARIMA:
  → Zeng et al. 결론과 일치
  → Branch A로 회귀, DL 추가 탐색 보류
```

---

## 우선순위 요약

```
즉시 (Phase 1):
  □ Fold 6개로 정리 (8:2)
  □ CI 방식 전환 (고정 폭 → 커버리지 측정)
  □ 피처 필터링 (LightGBM Feature Importance)
  □ D+20 horizon 테스트

분기점 이후:
  □ Branch A: 서비스 설계 + Airflow 연동
  □ Branch B: N-BEATS / TFT 실험 (v6)
```

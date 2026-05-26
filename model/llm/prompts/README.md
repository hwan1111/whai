# 프롬프트 관리 시스템

YAML 기반 프롬프트 템플릿 저장소입니다. 재사용 가능한 LLM 프롬프트를 관리하고, MLflow에 자동으로 로깅합니다.

## 구조

```
prompts/
├── README.md                      # 이 파일
├── news_summarization.yaml        # 뉴스 요약 프롬프트
└── [기타 프롬프트들]
```

## YAML 프롬프트 포맷

### 필수 필드

```yaml
name: prompt_name              # 프롬프트 식별자
version: "1.0.0"               # 버전 (semantic versioning)
description: |                 # 프롬프트 설명
  프롬프트가 무엇을 하는지 설명

template: |                    # 실제 프롬프트 템플릿
  {변수}를 사용하여 파라미터 주입
```

### 선택적 필드

```yaml
domain: finance                 # 도메인 (금융, 뉴스 등)
use_case: news_summary          # 사용 사례

metadata:                       # 메타데이터
  created_date: "2026-05-19"
  author: "team"
  tags:
    - news
    - summarization

parameters:                     # 템플릿 파라미터 정의
  article:
    type: string
    description: "요약할 뉴스 기사"
    required: true
  style:
    type: string
    description: "작성 스타일"
    required: false

model_config:                   # LLM 설정
  temperature: 0.5
  max_tokens: 200
  top_p: 0.9

examples:                       # 사용 예제
  - input:
      article: "..."
    output: "..."
```

## 사용 방법

### 1. 프롬프트 로드 및 렌더링

```python
from src.llm_utils import PromptManager

pm = PromptManager()

# 프롬프트 렌더링 (파라미터 주입)
rendered_prompt = pm.render_prompt(
    "news_summarization",
    article="Apple Inc. announced..."
)
```

### 2. LLM 호출

```python
from src.llm_utils import GatewayClient

client = GatewayClient()

# 렌더링된 프롬프트 사용
response = client.call(
    text=rendered_prompt,
    temperature=0.5,
    max_tokens=200
)
```

### 3. MLflow 자동 로깅

```python
# 프롬프트 사용 정보를 MLflow에 자동 기록
pm.log_to_mlflow(
    "news_summarization",
    rendered_prompt,
    model_name="summarlize-llm"
)
```

### 4. 프롬프트 정보 조회

```python
# 프롬프트 메타데이터 조회
info = pm.get_prompt_info("news_summarization")
print(info["version"])  # "1.0.0"

# 모델 설정 조회
config = pm.get_model_config("news_summarization")
print(config["temperature"])  # 0.5

# 사용 가능한 모든 프롬프트 목록
prompts = pm.list_prompts()  # ["news_summarization", ...]
```

## 새로운 프롬프트 추가하기

1. `prompts/` 디렉토리에 새 YAML 파일 생성
2. 필수 필드 작성 (name, version, description, template)
3. 파라미터, 모델 설정, 예제 추가 (선택사항)
4. PromptManager로 자동 로드됨

### 예제: 감정 분석 프롬프트

```yaml
name: sentiment_analysis
version: "1.0.0"
description: |
  금융 텍스트의 감정을 분석합니다.

domain: finance
use_case: sentiment_analysis

template: |
  다음 금융 텍스트의 감정을 분석해주세요.
  결과는 긍정/중립/부정 중 하나로 분류하세요.

  텍스트:
  {text}

  감정:

parameters:
  text:
    type: string
    description: "분석할 금융 텍스트"
    required: true

model_config:
  temperature: 0.3
  max_tokens: 50
```

## 버전 관리

프롬프트를 수정할 때는 **버전을 증가**시켜주세요:
- `1.0.0` → `1.1.0` : 마이너 수정 (옵션 변경 등)
- `1.0.0` → `2.0.0` : 메이저 변경 (구조 변경 등)

MLflow 로깅에 버전이 포함되므로, 실험 결과를 추적하기 쉬워집니다.

## 테스트

프롬프트 관리 시스템 테스트:

```bash
python script/test_prompt_manager.py
```

## 베스트 프랙티스

1. **명확한 설명**: 프롬프트가 무엇을 하는지 명확히 기술
2. **예제 포함**: 입출력 예제를 포함하여 의도 명확화
3. **파라미터 정의**: 모든 템플릿 변수를 `parameters`에 정의
4. **메타데이터**: 생성일, 작성자, 태그 등 포함
5. **버전 관리**: Semantic versioning 준수
6. **테스트**: 새로운 프롬프트는 테스트 스크립트에서 검증

## 다음 단계

- [ ] 추가 프롬프트 템플릿 작성 (감정 분석, 위험도 평가 등)
- [ ] 프롬프트 A/B 테스트 시스템 구축
- [ ] 프롬프트 최적화 파이프라인

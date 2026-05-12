"""
뉴스 3줄 요약 모델 비교 실험 (OpenRouter)
- Gemini 3.1 Flash-Lite vs Flash vs Claude Haiku
- OpenRouter API를 통한 통합 관리
- 토큰 비용, 품질 측정
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from datetime import datetime

import dotenv
import requests

# 환경 변수 로드
dotenv.load_dotenv(".env.local")

# 프롬프트 정의
SUMMARY_PROMPT = """다음 뉴스 기사를 읽고, 아래 3가지 관점에서 정확히 3줄로 요약하세요.
각 줄은 한 가지 관점만 포함해야 합니다.

1번 줄: 경영 전략/조직 변화
2번 줄: 재무/사업 영향
3번 줄: 시장/산업 임팩트

[기사 정보]
제목: {title}
발행일: {pub_date}

[기사 본문]
{body}

[출력 형식]
1.
2.
3. 
"""


def load_sample_news(data_dir: str, num_samples: int = 20) -> list[dict[str, Any]]:
    """뉴스 샘플 로드"""
    news_dir = Path(data_dir) / "News_삼성전자_005930"
    news_files = sorted(news_dir.glob("*.json"))[:num_samples]

    articles = []
    for file_path in news_files:
        with open(file_path, "r", encoding="utf-8") as f:
            article = json.load(f)
            articles.append(article)

    print(f"✓ {len(articles)}개 뉴스 로드됨")
    return articles


def summarize_with_openrouter(
    article: dict[str, Any],
    model_name: str,
) -> dict[str, Any]:
    """OpenRouter API를 통해 요약"""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return {"error": "OPENROUTER_API_KEY not set in .env.local"}

    prompt = SUMMARY_PROMPT.format(
        title=article.get("title", ""),
        pub_date=article.get("pub_date", ""),
        body=article.get("fulltext", "")[:4000]  # 토큰 절약
    )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://github.com/whai",
        "X-Title": "News Summary Experiment",
    }

    payload = {
        "model": model_name,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 500,
    }

    try:
        start_time = time.time()

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()

        elapsed = time.time() - start_time
        result = response.json()

        # OpenRouter 응답 파싱
        if "error" in result:
            return {
                "model": model_name,
                "error": result["error"].get("message", "Unknown error"),
            }

        return {
            "model": model_name,
            "summary": result["choices"][0]["message"]["content"],
            "input_tokens": result["usage"]["prompt_tokens"],
            "output_tokens": result["usage"]["completion_tokens"],
            "elapsed_sec": elapsed,
            "error": None,
        }
    except requests.exceptions.RequestException as e:
        return {
            "model": model_name,
            "error": f"API error: {str(e)}",
        }
    except (KeyError, IndexError) as e:
        return {
            "model": model_name,
            "error": f"Response parsing error: {str(e)}",
        }


def run_experiment(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """최적 모델로 요약 생성 (openai/gpt-oss-120b:free)"""
    results = []

    # 최적 모델만 사용
    model = "openai/gpt-oss-120b:free"

    for idx, article in enumerate(articles):
        pct = ((idx + 1) / len(articles)) * 100
        print(f"\n[{idx+1:3d}/{len(articles)}] {pct:5.1f}% | {article.get('title', '제목 없음')[:60]}...", end=" ")

        article_results = {
            "article_id": f"{article.get('pub_date')}__{article.get('ticker')}",
            "title": article.get("title"),
            "pub_date": article.get("pub_date"),
            "model": model,
        }

        result = summarize_with_openrouter(article, model)

        if result.get("error"):
            print(f"❌ {result['error']}")
            article_results["error"] = result["error"]
        else:
            print(f"✓ ({result['input_tokens']} + {result['output_tokens']} tokens)")
            article_results.update(result)

        results.append(article_results)

    return results


def calculate_costs(results: list[dict[str, Any]]) -> None:
    """비용 계산 및 통계 (OpenRouter Free - openai/gpt-oss-120b)"""
    print("\n" + "=" * 80)
    print("📊 처리 통계 분석")
    print("=" * 80)

    successful = sum(1 for r in results if not r.get("error"))
    failed = len(results) - successful

    total_input_tokens = sum(r.get("input_tokens", 0) for r in results if not r.get("error"))
    total_output_tokens = sum(r.get("output_tokens", 0) for r in results if not r.get("error"))
    total_elapsed = sum(r.get("elapsed_sec", 0) for r in results if not r.get("error"))

    print(f"\n총 기사: {len(results)}")
    print(f"성공: {successful} ({successful/len(results)*100:.1f}%)")
    print(f"실패: {failed} ({failed/len(results)*100:.1f}%)")

    print(f"\n입력 토큰: {total_input_tokens:,}")
    print(f"출력 토큰: {total_output_tokens:,}")
    print(f"총 토큰: {total_input_tokens + total_output_tokens:,}")

    if total_elapsed > 0:
        print(f"\n처리 시간: {total_elapsed:.1f}초 ({total_elapsed/60:.1f}분)")
        if successful > 0:
            avg_time = total_elapsed / successful
            print(f"평균 속도: {avg_time:.1f}초/기사")
            estimated_full = (total_input_tokens + total_output_tokens) / (total_input_tokens + total_output_tokens) * total_elapsed
            print(f"예상 시간 (8,000개): {estimated_full * 8000 / len(results) / 60:.0f}분")

    print(f"\n모델: openai/gpt-oss-120b:free")
    print(f"비용: FREE (오픈소스 모델)")
    print("=" * 80)


def save_results(results: list[dict[str, Any]], output_path: str) -> None:
    """결과 저장"""
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n✓ 결과 저장됨: {output_path}")


def main() -> None:
    """메인 실행"""
    print("🧪 뉴스 요약 모델 비교 실험 (PoC)")
    print("=" * 80)

    # 데이터 로드
    data_dir = "./data"
    articles = load_sample_news(data_dir, num_samples=20)

    # 실험 실행
    print("\n🚀 실험 진행 중...")
    results = run_experiment(articles)

    # 비용 분석
    calculate_costs(results)

    # 결과 저장
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = f"./data/results_experiment_{timestamp}.json"
    save_results(results, output_path)

    print("\n✅ 실험 완료!")
    print(f"📁 상세 결과: {output_path}")


if __name__ == "__main__":
    main()

"""
뉴스 3줄 요약 생성 파이프라인 (OpenRouter)
- 모델: openai/gpt-oss-120b:free (최적)
- 용도: 필터링된 뉴스 데이터 대량 요약
- 특징: 배치 처리, 진행률 추적, 에러 핸들링
"""

import json
import os
import time
from pathlib import Path
from typing import Any
from datetime import datetime

import dotenv
import requests

# 환경 변수 로드
dotenv.load_dotenv(".env.local")

# ============================================================================
# 설정
# ============================================================================

LLM_MODEL = "openai/gpt-oss-120b:free"

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
3. """


# ============================================================================
# 핵심 함수
# ============================================================================

def summarize_article(article: dict[str, Any]) -> dict[str, Any]:
    """OpenRouter API를 통해 뉴스 요약 생성"""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return {"error": "OPENROUTER_API_KEY not set in .env.local"}

    prompt = SUMMARY_PROMPT.format(
        title=article.get("title", ""),
        pub_date=article.get("pub_date", ""),
        body=article.get("fulltext", "")[:4000],  # 토큰 절약
    )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://github.com/whai",
        "X-Title": "News Summary Pipeline",
    }

    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 500,
    }

    try:
        start_time = time.time()

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30,
        )
        response.raise_for_status()

        elapsed = time.time() - start_time
        result = response.json()

        if "error" in result:
            return {
                "article_id": article.get("pub_date", "unknown"),
                "error": result["error"].get("message", "Unknown error"),
            }

        return {
            "article_id": f"{article.get('pub_date')}__{article.get('ticker', 'UNKNOWN')}",
            "title": article.get("title", ""),
            "pub_date": article.get("pub_date", ""),
            "summary": result["choices"][0]["message"]["content"],
            "input_tokens": result["usage"]["prompt_tokens"],
            "output_tokens": result["usage"]["completion_tokens"],
            "elapsed_sec": elapsed,
            "error": None,
        }
    except requests.exceptions.Timeout:
        return {"error": f"Timeout after 30s"}
    except requests.exceptions.RequestException as e:
        return {"error": f"API error: {str(e)}"}
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        return {"error": f"Response parsing error: {str(e)}"}


def process_news_batch(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """뉴스 배치 처리 (진행률 표시 포함)"""
    results = []
    total = len(articles)
    errors = 0

    print(f"\n🚀 {total}개 뉴스 요약 시작...")
    print("=" * 80)

    for idx, article in enumerate(articles, 1):
        # 진행률 표시
        pct = (idx / total) * 100
        print(
            f"[{idx:5d}/{total}] {pct:5.1f}% | {article.get('title', '제목 없음')[:50]}...",
            end=" ",
            flush=True,
        )

        # 요약 생성
        result = summarize_article(article)

        if result.get("error"):
            print(f"❌ {result['error'][:40]}")
            errors += 1
        else:
            elapsed = result.get("elapsed_sec", 0)
            input_tokens = result.get("input_tokens", 0)
            output_tokens = result.get("output_tokens", 0)
            print(f"✓ ({input_tokens} + {output_tokens} tokens, {elapsed:.1f}s)")

        results.append(result)

        # 요청 제한 회피 (필요시)
        if idx % 10 == 0:
            time.sleep(1)

    print("=" * 80)
    print(f"✅ 완료! 성공: {total - errors}, 실패: {errors}")

    return results


def save_results(results: list[dict[str, Any]], output_path: str) -> None:
    """결과 저장"""
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n✓ 결과 저장됨: {output_path}")


def calculate_stats(results: list[dict[str, Any]]) -> None:
    """통계 계산 및 출력"""
    total = len(results)
    successful = sum(1 for r in results if not r.get("error"))
    failed = total - successful

    total_input_tokens = sum(r.get("input_tokens", 0) for r in results if not r.get("error"))
    total_output_tokens = sum(r.get("output_tokens", 0) for r in results if not r.get("error"))
    total_elapsed = sum(r.get("elapsed_sec", 0) for r in results if not r.get("error"))

    # 비용 계산 (OpenRoute Free는 실제로는 무료지만, 향후 참고용)
    # openai/gpt-oss는 무료 모델

    print("\n" + "=" * 80)
    print("📊 처리 통계")
    print("=" * 80)
    print(f"총 기사: {total}")
    print(f"성공: {successful} ({successful/total*100:.1f}%)")
    print(f"실패: {failed} ({failed/total*100:.1f}%)")
    print(f"\n입력 토큰: {total_input_tokens:,}")
    print(f"출력 토큰: {total_output_tokens:,}")
    print(f"총 토큰: {total_input_tokens + total_output_tokens:,}")
    print(f"처리 시간: {total_elapsed:.1f}초 ({total_elapsed/60:.1f}분)")
    print(f"평균 속도: {total_elapsed/successful:.1f}초/기사" if successful > 0 else "N/A")
    print(f"모델: {LLM_MODEL}")
    print(f"비용: FREE (오픈소스 모델)")
    print("=" * 80)


def load_news(data_dir: str, num_articles: int | None = None) -> list[dict[str, Any]]:
    """뉴스 데이터 로드"""
    news_dir = Path(data_dir) / "News_삼성전자_005930"
    news_files = sorted(news_dir.glob("*.json"))

    if num_articles:
        news_files = news_files[:num_articles]

    articles = []
    for file_path in news_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                article = json.load(f)
                articles.append(article)
        except json.JSONDecodeError:
            print(f"⚠️  JSON 파싱 실패: {file_path}")
            continue

    print(f"✓ {len(articles)}개 뉴스 로드됨")
    return articles


# ============================================================================
# 메인
# ============================================================================

def main() -> None:
    """메인 실행"""
    print("📰 뉴스 3줄 요약 생성 파이프라인")
    print("=" * 80)

    # 설정: 테스트할 기사 수 (None = 전체)
    NUM_ARTICLES = 20  # 변경: None = 전체, 20 = 20개만 테스트

    # 데이터 로드
    data_dir = "./data"
    articles = load_news(data_dir, num_articles=NUM_ARTICLES)

    # 배치 처리
    results = process_news_batch(articles)

    # 통계
    calculate_stats(results)

    # 저장
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = f"./script/results_summary_{timestamp}.json"
    save_results(results, output_path)

    print(f"\n🎯 다음 단계:")
    print(f"   1. 결과 검토: {output_path}")
    print(f"   2. 품질 확인 후 필터링된 전체 8,000개 처리")
    print(f"   3. 데이터베이스에 저장")


if __name__ == "__main__":
    main()

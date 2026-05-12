"""
뉴스 3줄 요약 생성 + MLflow 추적
- 기존 news_summary_experiment.py의 로직 재사용
- MLflow로 메트릭/artifact 기록
- 모듈화된 tracking.py 사용
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

# MLflow 추적 모듈
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.llm.tracking import create_tracker

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

def summarize_with_openrouter(article: dict[str, Any], model_name: str) -> dict[str, Any]:
    """OpenRouter API를 통해 요약"""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return {"error": "OPENROUTER_API_KEY not set in .env.local"}

    prompt = SUMMARY_PROMPT.format(
        title=article.get("title", ""),
        pub_date=article.get("pub_date", ""),
        body=article.get("fulltext", "")[:4000],
    )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://github.com/whai",
        "X-Title": "News Summary Tracked",
    }

    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
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

        if "error" in result:
            return {
                "article_id": article.get("pub_date", "unknown"),
                "error": result["error"].get("message", "Unknown error"),
            }

        return {
            "article_id": f"{article.get('pub_date')}__{article.get('ticker', 'UNKNOWN')}",
            "title": article.get("title", ""),
            "pub_date": article.get("pub_date", ""),
            "model": model_name,
            "summary": result["choices"][0]["message"]["content"],
            "input_tokens": result["usage"]["prompt_tokens"],
            "output_tokens": result["usage"]["completion_tokens"],
            "elapsed_sec": elapsed,
            "error": None,
        }
    except requests.exceptions.RequestException as e:
        return {"error": f"API error: {str(e)}"}
    except (KeyError, IndexError) as e:
        return {"error": f"Response parsing error: {str(e)}"}


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


def run_experiment(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """최적 모델로 요약 생성"""
    results = []

    for idx, article in enumerate(articles):
        pct = ((idx + 1) / len(articles)) * 100
        print(
            f"[{idx+1:3d}/{len(articles)}] {pct:5.1f}% | {article.get('title', '제목 없음')[:50]}...",
            end=" ",
            flush=True,
        )

        article_results = {
            "article_id": f"{article.get('pub_date')}__{article.get('ticker')}",
            "title": article.get("title"),
            "pub_date": article.get("pub_date"),
            "model": LLM_MODEL,
        }

        result = summarize_with_openrouter(article, LLM_MODEL)

        if result.get("error"):
            print(f"❌ {result['error']}")
            article_results["error"] = result["error"]
        else:
            print(f"✓ ({result['input_tokens']} + {result['output_tokens']} tokens)")
            article_results.update(result)

        results.append(article_results)

    return results


def calculate_stats(results: list[dict[str, Any]]) -> dict[str, float]:
    """통계 계산"""
    successful = sum(1 for r in results if not r.get("error"))
    failed = len(results) - successful

    total_input_tokens = sum(r.get("input_tokens", 0) for r in results if not r.get("error"))
    total_output_tokens = sum(r.get("output_tokens", 0) for r in results if not r.get("error"))
    total_elapsed = sum(r.get("elapsed_sec", 0) for r in results if not r.get("error"))

    stats = {
        "total_articles": len(results),
        "successful": successful,
        "failed": failed,
        "success_rate": (successful / len(results) * 100) if results else 0,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_tokens": total_input_tokens + total_output_tokens,
        "total_elapsed_sec": total_elapsed,
        "avg_elapsed_sec": (total_elapsed / successful) if successful > 0 else 0,
    }

    return stats


def print_stats(stats: dict[str, float]) -> None:
    """통계 출력"""
    print("\n" + "=" * 80)
    print("📊 처리 통계")
    print("=" * 80)
    print(f"총 기사: {stats['total_articles']}")
    print(f"성공: {stats['successful']} ({stats['success_rate']:.1f}%)")
    print(f"실패: {stats['failed']}")
    print(f"\n입력 토큰: {stats['total_input_tokens']:,}")
    print(f"출력 토큰: {stats['total_output_tokens']:,}")
    print(f"총 토큰: {stats['total_tokens']:,}")
    print(f"\n처리 시간: {stats['total_elapsed_sec']:.1f}초 ({stats['total_elapsed_sec']/60:.1f}분)")
    print(f"평균 속도: {stats['avg_elapsed_sec']:.1f}초/기사")
    print(f"모델: {LLM_MODEL}")
    print(f"비용: FREE (오픈소스 모델)")
    print("=" * 80)


def save_results(results: list[dict[str, Any]], output_path: str) -> None:
    """결과 저장"""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"✓ 결과 저장됨: {output_path}")


# ============================================================================
# 메인 (MLflow 추적 포함)
# ============================================================================

def main() -> None:
    """메인 실행"""
    print("📰 뉴스 3줄 요약 생성 + MLflow 추적")
    print("=" * 80)

    # MLflow 추적 초기화 (없으면 None)
    tracker = create_tracker()

    # 데이터 로드
    data_dir = "./data"
    articles = load_sample_news(data_dir, num_samples=20)

    # MLflow Run 시작
    run_name = f"openai-gpt-oss-{len(articles)}articles-{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if tracker:
        tracker.start_run(
            run_name=run_name,
            params={
                "model": LLM_MODEL,
                "num_articles": len(articles),
                "data_source": "News_삼성전자_005930",
                "max_tokens": 500,
            },
        )

    # 실험 실행
    print("\n🚀 실험 진행 중...")
    results = run_experiment(articles)

    # 통계 계산
    stats = calculate_stats(results)

    # 통계 출력
    print_stats(stats)

    # MLflow에 메트릭 기록
    if tracker:
        tracker.log_metrics({
            "total_articles": stats["total_articles"],
            "success_rate": stats["success_rate"],
            "total_input_tokens": stats["total_input_tokens"],
            "total_output_tokens": stats["total_output_tokens"],
            "total_tokens": stats["total_tokens"],
            "total_elapsed_sec": stats["total_elapsed_sec"],
            "avg_elapsed_sec": stats["avg_elapsed_sec"],
        })

    # 결과 저장
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = f"./script/results_tracked_{timestamp}.json"
    save_results(results, output_path)

    # MLflow에 artifacts 저장
    if tracker:
        tracker.log_artifact_json(results, f"results_{timestamp}.json")
        # 샘플 요약 저장
        sample_summaries = [
            {"title": r.get("title"), "summary": r.get("summary")}
            for r in results
            if r.get("summary")
        ]
        tracker.log_samples(sample_summaries)
        tracker.end_run()

    # 마무리
    print("\n✅ 완료!")
    if tracker:
        print(f"📊 MLflow UI: {tracker.get_ui_url()}")
        print(f"   Run name: {run_name}")
    print(f"📁 결과: {output_path}")


if __name__ == "__main__":
    main()

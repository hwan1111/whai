#!/usr/bin/env python3
"""
실제 뉴스 데이터 평가 파이프라인

로컬 뉴스 데이터를 로드 → 요약 생성 → 평가 → MLflow 기록
"""

import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging
import json
import os
from typing import List, Dict, Optional
import mlflow
from dotenv import load_dotenv

from src.data.news_loader import NewsDataLoader
from src.llm_utils import (
    PromptManager,
    GatewayClient,
    NewsEvaluator,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# .env.local 로드
_env_file = Path(__file__).parent.parent / ".env.local"
if _env_file.exists():
    load_dotenv(_env_file, override=True)


def load_reference_summaries(
    reference_file: Optional[Path] = None,
) -> Dict[str, str]:
    """
    참조 요약(정답) 로드

    Args:
        reference_file: 참조 요약 파일 (JSON)

    Returns:
        {news_id: reference_summary} 딕셔너리
    """
    if reference_file and reference_file.exists():
        try:
            with open(reference_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"⚠️ 참조 요약 파일 로드 실패: {str(e)}")

    return {}


def create_evaluation_data(
    news_list: List[Dict],
    summaries: List[str],
    reference_summaries: Dict[str, str],
) -> List[Dict]:
    """
    평가용 데이터 생성

    Args:
        news_list: 뉴스 데이터
        summaries: 생성된 요약
        reference_summaries: 참조 요약

    Returns:
        평가용 데이터
    """
    eval_data = []

    for i, (news, summary) in enumerate(zip(news_list, summaries)):
        news_id = f"{news['ticker']}_{news['pub_date']}_{i}"
        reference = reference_summaries.get(news_id, "")

        if not reference:
            # 참조 요약이 없으면 사용자 입력 요청
            logger.warning(f"\n⚠️ {news_id}의 참조 요약이 없습니다")
            logger.info(f"제목: {news['title']}")
            logger.info(f"생성된 요약:\n{summary}\n")

            user_input = input("참조 요약을 입력해주세요 (또는 Enter로 건너뛰기): ").strip()
            if not user_input:
                logger.info("건너뜁니다")
                continue
            reference = user_input

        eval_data.append({
            "id": news_id,
            "article": news["fulltext"],
            "reference_summary": reference,
            "generated_summary": summary,
            "metadata": {
                "ticker": news["ticker"],
                "company_name": news.get("company_name", ""),
                "title": news["title"],
                "pub_date": news["pub_date"],
                "source": news.get("source", ""),
            },
        })

    return eval_data


def run_evaluation_pipeline(
    ticker: str,
    start_date: str,
    end_date: str,
    reference_file: Optional[Path] = None,
    mlflow_experiment: str = "news_summarize_llm",
    use_bert_score: bool = False,
) -> bool:
    """
    뉴스 데이터 평가 파이프라인 실행

    Args:
        ticker: 티커 (예: 005930)
        start_date: 시작 날짜 (YYYY-MM-DD)
        end_date: 종료 날짜 (YYYY-MM-DD)
        reference_file: 참조 요약 파일
        mlflow_experiment: MLflow 실험 이름
        use_bert_score: BERTScore 사용 여부

    Returns:
        성공 여부
    """
    logger.info("=" * 60)
    logger.info("뉴스 데이터 평가 파이프라인 시작")
    logger.info("=" * 60)

    # MLflow 설정
    logger.info("\n[0/5] MLflow 연결 설정 중...")
    mlflow_uri = os.getenv("MLFLOW_TRACKING_URI", "")
    mlflow_username = os.getenv("MLFLOW_TRACKING_USERNAME", "")
    mlflow_password = os.getenv("MLFLOW_TRACKING_PASSWORD", "")

    if not mlflow_uri:
        logger.error("❌ MLFLOW_TRACKING_URI이 설정되지 않았습니다")
        return False

    mlflow.set_tracking_uri(mlflow_uri)

    # 인증 설정
    if mlflow_username and mlflow_password:
        os.environ["MLFLOW_TRACKING_USERNAME"] = mlflow_username
        os.environ["MLFLOW_TRACKING_PASSWORD"] = mlflow_password
        logger.info(f"✓ MLflow 인증 설정 완료")

    logger.info(f"✓ MLflow URI: {mlflow_uri}")

    # MLflow experiment 설정
    mlflow.set_experiment(mlflow_experiment)
    run_name = f"{ticker}_{start_date}~{end_date}"

    # 전체 파이프라인을 MLflow run 내부에서 실행
    try:
        with mlflow.start_run(run_name=run_name) as run:
            logger.info(f"✓ MLflow Run 시작: {run.info.run_id}")

            # 1. 뉴스 데이터 로드
            logger.info(f"\n[1/5] 뉴스 데이터 로드 중... ({ticker}, {start_date}~{end_date})")
            loader = NewsDataLoader()
            news_list = loader.load_news(
                ticker=ticker,
                start_date=start_date,
                end_date=end_date,
            )

            if not news_list:
                logger.error(f"❌ 뉴스를 찾을 수 없습니다")
                return False

            logger.info(f"✓ {len(news_list)}개 뉴스 로드 완료")

            # 2. 요약 생성 (MLflow가 OpenAI 호출 추적)
            logger.info(f"\n[2/5] 요약 생성 중...")
            pm = PromptManager()
            client = GatewayClient(validate_connection=False)

            summaries = []
            for i, news in enumerate(news_list, 1):
                try:
                    title, fulltext = loader.get_article_text(news)
                    logger.info(f"  [{i}/{len(news_list)}] {title[:50]}... 요약 중")

                    rendered_prompt = pm.render_prompt(
                        "news_summarization",
                        article=fulltext,
                    )
                    model_config = pm.get_model_config("news_summarization")

                    summary = client.call(
                        text=rendered_prompt,
                        temperature=model_config.get("temperature", 0.5),
                        max_tokens=model_config.get("max_tokens", 200),
                    )

                    summaries.append(summary)
                    logger.debug(f"    요약: {summary[:80]}...")

                except Exception as e:
                    logger.error(f"  ❌ {title} 요약 실패: {str(e)}")
                    summaries.append("")

            logger.info(f"✓ {len(summaries)}개 요약 생성 완료")

            # 3. 평가 데이터 준비
            logger.info(f"\n[3/5] 평가 데이터 준비 중...")
            reference_summaries = load_reference_summaries(reference_file)
            eval_data = create_evaluation_data(
                news_list,
                summaries,
                reference_summaries,
            )

            if not eval_data:
                logger.error("❌ 평가할 데이터가 없습니다")
                return False

            logger.info(f"✓ {len(eval_data)}개 평가 항목 준비 완료")

            # 4. 기본 평가 엔진으로 평가 (상세 통계용)
            logger.info(f"\n[4/5] 평가 실행 중...")
            evaluator = NewsEvaluator(use_bert_score=use_bert_score)

            results = evaluator.evaluate_batch(
                eval_data,
                log_to_mlflow=True,
                run_name=None,  # 이미 run이 활성화되어 있음
            )

            if not results:
                logger.error("❌ 평가 결과가 없습니다")
                return False

            summary = evaluator.get_evaluation_summary(results)

            # 5. 결과 저장 및 MLflow 메타데이터 로깅
            logger.info(f"\n[5/5] 결과 저장 중...")

            mlflow.log_param("ticker", ticker)
            mlflow.log_param("start_date", start_date)
            mlflow.log_param("end_date", end_date)
            mlflow.log_param("news_count", len(news_list))
            mlflow.log_param("evaluation_count", len(results))

            logger.info(f"✓ 평가 완료 및 MLflow 기록")

            # 최종 결과
            logger.info("\n" + "=" * 60)
            logger.info("✅ 뉴스 데이터 평가 완료!")
            logger.info("=" * 60)
            logger.info(f"\n평가 통계:")
            for key, value in summary.items():
                if isinstance(value, float):
                    logger.info(f"  {key}: {value:.4f}")
                else:
                    logger.info(f"  {key}: {value}")

            logger.info(f"\nMLflow 확인:")
            logger.info(f"  실험: {mlflow_experiment}")
            logger.info(f"  Run ID: {run.info.run_id}")

        # ========== Run 종료 후 Experiment 레벨 평가 ==========
        # MLflow Quality를 위한 predict_fn 정의
        summaries_dict = {item["id"]: item["generated_summary"] for item in eval_data}

        def predict_fn(id, article):
            """이미 생성한 요약을 반환하는 함수"""
            return summaries_dict.get(id, "")

        # MLflow Quality 형식으로 데이터 변환
        mlflow_eval_data = []
        for item in eval_data:
            mlflow_eval_data.append({
                "inputs": {
                    "id": item["id"],
                    "article": item["article"],
                },
                "expectations": {
                    "reference_summary": item["reference_summary"],
                },
            })

        # Experiment 레벨에서 MLflow Quality 평가 실행
        logger.info(f"\n📊 Experiment Quality 평가 중...")
        try:
            from src.llm_utils.mlflow_scorers import (
                rouge_scorer,
                bert_score_scorer,
                summary_similarity_score,
            )

            # BERTScore를 사용하는지에 따라 스코어러 선택
            if use_bert_score:
                scorers = [rouge_scorer, bert_score_scorer, summary_similarity_score]
            else:
                scorers = [rouge_scorer]

            mlflow.genai.evaluate(
                data=mlflow_eval_data,
                predict_fn=predict_fn,
                scorers=scorers,
            )
            logger.info(f"✓ Experiment Quality 평가 완료 (Overview에 표시됨)")
        except Exception as e:
            logger.warning(f"⚠️ Experiment Quality 평가 실패: {str(e)}")

        return True

    except Exception as e:
        logger.error(f"❌ 파이프라인 실패: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """메인 함수"""
    import argparse

    parser = argparse.ArgumentParser(
        description="실제 뉴스 데이터 평가 파이프라인"
    )
    parser.add_argument(
        "--ticker",
        type=str,
        default="005930",
        help="티커 (기본값: 005930)",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default="2026-05-01",
        help="시작 날짜 (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default="2026-05-07",
        help="종료 날짜 (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--reference",
        type=Path,
        help="참조 요약 파일 (JSON)",
    )
    parser.add_argument(
        "--experiment",
        type=str,
        default="news_summarize_llm",
        help="MLflow 실험 이름",
    )
    parser.add_argument(
        "--use-bert",
        action="store_true",
        help="BERTScore 활성화",
    )

    args = parser.parse_args()

    success = run_evaluation_pipeline(
        ticker=args.ticker,
        start_date=args.start_date,
        end_date=args.end_date,
        reference_file=args.reference,
        mlflow_experiment=args.experiment,
        use_bert_score=args.use_bert,
    )

    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

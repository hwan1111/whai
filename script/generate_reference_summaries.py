#!/usr/bin/env python3
"""
고성능 LLM으로 레퍼런스 요약 생성 (Phase 2-1)

필터링된 뉴스 데이터를 S3에서 로드하고, 고성능 LLM으로 요약을 생성합니다.
생성된 요약은 평가용 레퍼런스 데이터로 사용됩니다.

결과 저장:
  - 로컬: data/reference_summaries/ (--output-dir 옵션으로 변경 가능)
  - S3: s3://fisa-news-archive/reference/{ticker}/reference_{start_date}_{end_date}.json

사용법:
  # 기본 (로컬 + S3 저장)
  python script/generate_reference_summaries.py --ticker 005930 --start-date 2020-05-01 --end-date 2020-05-31

  # 로컬에만 저장
  python script/generate_reference_summaries.py --ticker 005930 --start-date 2020-05-01 --end-date 2020-05-31 --no-s3

  # MLflow 실험 추적
  python script/generate_reference_summaries.py --ticker 005930 --start-date 2020-05-01 --end-date 2020-05-31 --experiment "news_summarization"
"""

import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import boto3
import mlflow
from botocore.exceptions import ClientError
from dotenv import load_dotenv

# 프로젝트 루트를 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.data.s3_news_loader import S3NewsDataLoader
from src.llm_utils.summarizer import MidPerformanceSummarizer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# .env.local 로드
_env_file = project_root / ".env.local"
if _env_file.exists():
    load_dotenv(_env_file, override=True)


def generate_reference_summaries(
    ticker: str,
    start_date: str,
    end_date: str,
    sample_size: int = 20,
    mlflow_experiment: Optional[str] = None,
    output_dir: Optional[str] = None,
    upload_to_s3: bool = True,
) -> dict:
    """
    고성능 LLM으로 레퍼런스 요약 생성

    Args:
        ticker: 종목코드 (예: 000660)
        start_date: 시작 날짜 (YYYY-MM-DD)
        end_date: 종료 날짜 (YYYY-MM-DD)
        sample_size: 각 날짜별 샘플 수 (기본값: 20)
        mlflow_experiment: MLflow 실험 이름 (선택)
        output_dir: 결과 저장 디렉토리 (선택)
        upload_to_s3: S3에 업로드 여부 (기본값: True)

    Returns:
        {
            "ticker": "000660",
            "date": "2020-01-01",
            "summaries": [
                {
                    "news_id": "000660_2020-01-01_0",
                    "original_news": "원본 기사...",
                    "reference_summary": "레퍼런스 요약...",
                    "status": "success"
                }
            ]
        }
    """
    logger.info("=" * 80)
    logger.info("고성능 LLM으로 레퍼런스 요약 생성 시작")
    logger.info("=" * 80)

    # S3 로더 초기화
    logger.info("\n[Step 1] S3 뉴스 로더 초기화")
    try:
        loader = S3NewsDataLoader(
            bucket=os.getenv("AWS_S3_BUCKET", "fisa-news-archive"),
            region=os.getenv("AWS_DEFAULT_REGION", "ap-northeast-2"),
            prefix="raw",
        )
        logger.info("✓ S3 로더 초기화 완료")
    except Exception as e:
        logger.error(f"❌ S3 로더 초기화 실패: {str(e)}")
        return {}

    # Summarizer 초기화
    logger.info("\n[Step 2] 고성능 Summarizer 초기화")
    try:
        # MLflow Prompt Management에서 온도, 토큰 등의 설정 관리
        summarizer = MidPerformanceSummarizer(
            prompt_uri=os.getenv("MLFLOW_PROMPT_URI_REFERENCE", None)
        )
        logger.info("✓ MidPerformanceSummarizer 초기화 완료")
    except Exception as e:
        logger.error(f"❌ Summarizer 초기화 실패: {str(e)}")
        return {}

    # MLflow 설정 (선택사항)
    mlflow_run = None
    if mlflow_experiment:
        try:
            mlflow_uri = os.getenv("MLFLOW_TRACKING_URI", "")
            if mlflow_uri:
                mlflow.set_tracking_uri(mlflow_uri)
                mlflow.set_experiment(mlflow_experiment)
                mlflow_run = mlflow.start_run(
                    run_name=f"{ticker}_{start_date}~{end_date}"
                )
                mlflow.log_param("ticker", ticker)
                mlflow.log_param("date_range", f"{start_date}~{end_date}")
                mlflow.log_param("sample_size", sample_size)
                logger.info(f"✓ MLflow Run 시작: {mlflow_run.info.run_id}")
        except Exception as e:
            logger.warning(f"⚠️ MLflow 설정 실패: {str(e)}")

    # S3에서 뉴스 데이터 로드
    logger.info(f"\n[Step 3] S3에서 뉴스 데이터 로드 ({ticker}, {start_date}~{end_date})")
    try:
        news_list = loader.load_news(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
        )

        if not news_list:
            logger.warning(f"⚠️ 해당 기간의 뉴스 데이터가 없습니다")
            if mlflow_run:
                mlflow.end_run(status="FAILED")
            return {}

        logger.info(f"✓ {len(news_list)}개 뉴스 로드 완료")

        # 샘플링 (sample_size만큼)
        if len(news_list) > sample_size:
            import random
            sampled_news = random.sample(news_list, sample_size)
            logger.info(
                f"✓ {len(news_list)}개 중 {sample_size}개 샘플링"
            )
        else:
            sampled_news = news_list
            logger.info(f"✓ 샘플링: 전체 {len(sampled_news)}개 사용")

    except Exception as e:
        logger.error(f"❌ 뉴스 로드 실패: {str(e)}")
        if mlflow_run:
            mlflow.end_run(status="FAILED")
        return {}

    # 요약 생성
    logger.info(f"\n[Step 4] 요약 생성 ({len(sampled_news)}개)")
    summaries = []

    date_index_map = {}  # 날짜별 인덱스 추적

    for idx, news in enumerate(sampled_news, 1):
        try:
            title = news.get("title", "")
            fulltext = news.get("fulltext", "")
            pub_date = news.get("pub_date", start_date)

            # 뉴스 ID 생성
            if pub_date not in date_index_map:
                date_index_map[pub_date] = 0
            else:
                date_index_map[pub_date] += 1

            news_id = f"{ticker}_{pub_date}_{date_index_map[pub_date]}"

            logger.info(f"  [{idx}/{len(sampled_news)}] {title[:60]}... 요약 생성 중")

            # 요약 생성
            summary = summarizer.summarize(fulltext)

            summaries.append({
                "news_id": news_id,
                "title": title,
                "original_news": fulltext[:500] + "..." if len(fulltext) > 500 else fulltext,
                "reference_summary": summary,
                "status": "success",
            })

            logger.debug(f"  ✓ {news_id}: {summary[:80]}...")

        except Exception as e:
            logger.error(f"  ❌ [{idx}] 요약 생성 실패: {str(e)}")
            summaries.append({
                "news_id": f"{ticker}_{news.get('pub_date', start_date)}_{idx}",
                "title": news.get("title", ""),
                "original_news": news.get("fulltext", "")[:500],
                "reference_summary": "",
                "status": "failed",
                "error": str(e),
            })

    # 결과 정리
    logger.info(f"\n[Step 5] 결과 저장")
    success_count = len([s for s in summaries if s["status"] == "success"])
    logger.info(f"✓ 요약 생성 완료: {success_count}/{len(summaries)} 성공")

    result = {
        "ticker": ticker,
        "date_range": f"{start_date}~{end_date}",
        "created_at": datetime.now().isoformat(),
        "total_count": len(summaries),
        "success_count": success_count,
        "summaries": summaries,
    }

    # 로컬 파일로 저장 (선택사항)
    if output_dir:
        output_path = Path(output_dir) / f"reference_{ticker}_{start_date.replace('-', '')}.json"
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            logger.info(f"✓ 로컬 저장: {output_path}")
        except Exception as e:
            logger.warning(f"⚠️ 로컬 파일 저장 실패: {str(e)}")

    # S3에 업로드 (선택사항)
    if upload_to_s3:
        try:
            s3_client = boto3.client(
                "s3",
                region_name=os.getenv("AWS_DEFAULT_REGION", "ap-northeast-2"),
            )

            bucket_name = os.getenv("AWS_S3_BUCKET", "fisa-news-archive")
            s3_key = f"reference/{ticker}/reference_{start_date.replace('-', '')}_{end_date.replace('-', '')}.json"

            # JSON을 바이트로 변환
            json_body = json.dumps(result, ensure_ascii=False, indent=2)

            # S3에 업로드
            s3_client.put_object(
                Bucket=bucket_name,
                Key=s3_key,
                Body=json_body.encode("utf-8"),
                ContentType="application/json",
            )
            logger.info(f"✓ S3 업로드 완료: s3://{bucket_name}/{s3_key}")
        except ClientError as e:
            logger.error(f"❌ S3 업로드 실패: {str(e)}")
        except Exception as e:
            logger.error(f"❌ S3 업로드 중 오류 발생: {str(e)}")

    # MLflow 메트릭 기록
    if mlflow_run:
        try:
            mlflow.log_metric("total_summaries", len(summaries))
            mlflow.log_metric("successful_summaries", success_count)
            mlflow.log_metric("success_rate", success_count / len(summaries) if summaries else 0)
            mlflow.end_run(status="FINISHED")
            logger.info("✓ MLflow 메트릭 기록 완료")
        except Exception as e:
            logger.warning(f"⚠️ MLflow 메트릭 기록 실패: {str(e)}")

    logger.info("\n" + "=" * 80)
    logger.info("✅ 레퍼런스 요약 생성 완료!")
    logger.info("=" * 80)

    return result


def main():
    """메인 함수"""
    import argparse

    parser = argparse.ArgumentParser(
        description="고성능 LLM으로 레퍼런스 요약 생성"
    )
    parser.add_argument(
        "--ticker",
        type=str,
        default="000660",
        help="종목코드 (기본값: 000660)",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default="2020-05-01",
        help="시작 날짜 (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default="2020-05-01",
        help="종료 날짜 (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=20,
        help="일일 샘플 수 (기본값: 20)",
    )
    parser.add_argument(
        "--experiment",
        type=str,
        default=None,
        help="MLflow 실험 이름 (선택)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/reference_summaries",
        help="결과 저장 디렉토리 (로컬)",
    )
    parser.add_argument(
        "--upload-to-s3",
        action="store_true",
        default=True,
        help="S3에 업로드 여부 (기본값: True)",
    )
    parser.add_argument(
        "--no-s3",
        action="store_true",
        help="S3 업로드 비활성화",
    )

    args = parser.parse_args()

    # --no-s3 플래그가 있으면 S3 업로드 비활성화
    upload_to_s3 = not args.no_s3

    result = generate_reference_summaries(
        ticker=args.ticker,
        start_date=args.start_date,
        end_date=args.end_date,
        sample_size=args.sample_size,
        mlflow_experiment=args.experiment,
        output_dir=args.output_dir,
        upload_to_s3=upload_to_s3,
    )

    return 0 if result else 1


if __name__ == "__main__":
    sys.exit(main())

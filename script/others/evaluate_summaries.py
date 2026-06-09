#!/usr/bin/env python3
"""
뉴스 요약 평가 실행 스크립트

생성된 요약들을 ROUGE, BERTScore 등으로 평가하고 MLflow에 기록합니다.
"""

import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging
from typing import List, Dict
import mlflow
from src.llm_utils import NewsEvaluator

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def load_evaluation_data(data_file: Path) -> List[Dict]:
    """
    평가 데이터 로드

    Args:
        data_file: 평가 데이터 파일 (JSON)

    Returns:
        평가 대상 요약 리스트
    """
    import json

    try:
        with open(data_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        logger.info(f"✓ {len(data)}개 항목 로드 완료")
        return data
    except FileNotFoundError:
        logger.error(f"❌ 파일을 찾을 수 없습니다: {data_file}")
        return []
    except json.JSONDecodeError as e:
        logger.error(f"❌ JSON 파싱 실패: {str(e)}")
        return []


def run_evaluation(
    eval_data: List[Dict],
    use_bert_score: bool = False,
    mlflow_experiment: str = "news_summarize_llm",
    mlflow_run_name: str = "batch_evaluation",
) -> bool:
    """
    평가 실행

    Args:
        eval_data: 평가 데이터
        use_bert_score: BERTScore 사용 여부
        mlflow_experiment: MLflow 실험 이름
        mlflow_run_name: MLflow Run 이름

    Returns:
        성공 여부
    """
    logger.info("=" * 60)
    logger.info("뉴스 요약 평가 시작")
    logger.info("=" * 60)

    # MLflow 설정
    mlflow.set_experiment(mlflow_experiment)

    try:
        with mlflow.start_run(run_name=mlflow_run_name) as run:
            logger.info(f"\nMLflow Run ID: {run.info.run_id}")

            # NewsEvaluator 초기화
            logger.info("\n[1/2] NewsEvaluator 초기화 중...")
            evaluator = NewsEvaluator(use_bert_score=use_bert_score)

            # 배치 평가
            logger.info(f"\n[2/2] {len(eval_data)}개 항목 평가 중...")
            results = evaluator.evaluate_batch(
                eval_data,
                log_to_mlflow=True,
                run_name=mlflow_run_name,
            )

            if not results:
                logger.error("❌ 평가 결과가 없습니다")
                return False

            # 평가 요약
            summary = evaluator.get_evaluation_summary(results)

            logger.info("\n" + "=" * 60)
            logger.info("평가 완료")
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

            return True

    except Exception as e:
        logger.error(f"❌ 평가 실패: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def create_sample_data() -> List[Dict]:
    """
    샘플 평가 데이터 생성

    Returns:
        샘플 평가 데이터
    """
    return [
        {
            "id": "sample_001",
            "article": """
                Apple Inc. announced record quarterly earnings of $25.3 billion, beating analyst
                expectations by 15%. The company's iPhone sales surged due to strong demand in Asia,
                while Services revenue continued its steady growth trajectory. CEO Tim Cook attributed
                the success to innovation and customer loyalty programs. The stock rose 8% in
                after-hours trading.
            """,
            "reference_summary": """
                Apple이 분기 매출 253억 달러로 분석가 예상을 15% 초과 달성했다.
                아이폰 판매가 아시아 수요 증가로 급증했으며, 서비스 부문은 지속적인 성장을 이어갔다.
                CEO Tim Cook은 혁신과 고객 충성도 프로그램이 성공의 원동력이라고 밝혔다.
            """,
            "generated_summary": """
                Apple은 253억 달러의 기록적 분기 매출을 발표했다.
                아이폰 판매가 증가했고 서비스 부문도 성장을 계속했다.
                CEO Cook은 회사의 성공이 혁신에서 비롯되었다고 말했다.
            """,
        },
        {
            "id": "sample_002",
            "article": """
                Microsoft released its latest financial report showing a 12% revenue increase
                year-over-year. Cloud services drove the growth with Azure expanding its market share.
                The company announced plans for AI integration across its product suite, with a focus
                on enterprise customers. Stock analysts upgraded their price targets following the news.
            """,
            "reference_summary": """
                Microsoft는 연 12% 매출 증가를 보였다.
                Azure를 포함한 클라우드 서비스가 성장을 주도했다.
                회사는 엔터프라이즈 고객을 중심으로 AI 통합 계획을 발표했다.
            """,
            "generated_summary": """
                Microsoft의 매출이 증가했다.
                Azure가 성장했고 AI 계획도 있다.
                분석가들은 긍정적 평가를 했다.
            """,
        },
    ]


def main():
    """메인 함수"""
    import argparse

    parser = argparse.ArgumentParser(
        description="뉴스 요약 평가 실행"
    )
    parser.add_argument(
        "--data",
        type=Path,
        help="평가 데이터 파일 경로 (JSON)",
    )
    parser.add_argument(
        "--use-bert",
        action="store_true",
        help="BERTScore 활성화 (리소스 많이 사용)",
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="샘플 데이터로 평가 실행",
    )
    parser.add_argument(
        "--experiment",
        type=str,
        default="news_summarize_llm",
        help="MLflow 실험 이름",
    )

    args = parser.parse_args()

    # 평가 데이터 준비
    if args.sample:
        logger.info("샘플 데이터로 평가 실행 중...")
        eval_data = create_sample_data()
    elif args.data:
        eval_data = load_evaluation_data(args.data)
    else:
        logger.error("❌ 평가 데이터를 지정해주세요 (--data 또는 --sample)")
        return False

    if not eval_data:
        logger.error("❌ 평가 데이터가 비어있습니다")
        return False

    # 평가 실행
    success = run_evaluation(
        eval_data,
        use_bert_score=args.use_bert,
        mlflow_experiment=args.experiment,
    )

    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

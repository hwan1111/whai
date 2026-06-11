"""
MLflow 원격 서버 연결 테스트 스크립트

로컬에서 원격 MLflow 서버에 정상적으로 연결되는지 확인합니다.
"""

import sys
sys.path.insert(0, '.')

import logging
from config.mlflow_config import MLflowConfig
from src.llm_utils.mlflow_logger import MLflowLogger

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_connection():
    """MLflow 서버 연결 테스트"""
    try:
        logger.info("🔍 MLflow 설정 확인...")
        logger.info(f"  Tracking URI: {MLflowConfig.get_tracking_uri()}")
        logger.info(f"  Username: {MLflowConfig.MLFLOW_TRACKING_USERNAME}")

        logger.info("\n📡 원격 서버 연결 중...")
        mlflow_logger = MLflowLogger(validate_connection=True)

        logger.info("\n✅ 연결 성공!")

        # 기존 실험 목록 조회
        logger.info("\n📚 기존 실험 목록:")
        experiments = mlflow_logger.search_experiments(max_results=5)
        for exp in experiments:
            logger.info(f"  - {exp['name']} (ID: {exp['experiment_id']})")

        return True

    except Exception as e:
        logger.error(f"\n❌ 연결 실패: {str(e)}")
        return False


def test_experiment_creation():
    """실험 생성 및 run 테스트"""
    try:
        logger.info("\n🧪 새로운 실험 생성 테스트...")
        mlflow_logger = MLflowLogger()

        # 실험 생성
        exp_id = mlflow_logger.set_experiment("test_news_summary")
        logger.info(f"✓ 실험 생성: test_news_summary (ID: {exp_id})")

        # Run 시작
        logger.info("\n▶️ Run 시작...")
        run_id = mlflow_logger.start_run(
            experiment_name="test_news_summary",
            run_name="test_run_001",
            tags={"test": "true", "environment": "local"}
        )
        logger.info(f"✓ Run 시작: {run_id}")

        # 파라미터 로깅
        logger.info("\n📝 파라미터 로깅...")
        mlflow_logger.log_params({
            "ticker": "005930",
            "sample_size": 10,
            "endpoint": "mid_performance_llm"
        })
        logger.info("✓ 파라미터 로깅 완료")

        # 메트릭 로깅
        logger.info("\n📊 메트릭 로깅...")
        mlflow_logger.log_metrics({
            "total_news": 45,
            "summaries_generated": 45,
            "processing_time_seconds": 120.5
        })
        logger.info("✓ 메트릭 로깅 완료")

        # Run 종료
        logger.info("\n⏹️ Run 종료...")
        mlflow_logger.end_run(status="FINISHED")
        logger.info("✓ Run 종료 완료")

        logger.info(f"\n✅ 실험 성공!")
        logger.info(f"   MLflow UI: http://52.78.237.104:5001")
        logger.info(f"   Experiment: test_news_summary")
        logger.info(f"   Run ID: {run_id}")

        return True

    except Exception as e:
        logger.error(f"\n❌ 실험 생성 실패: {str(e)}")
        return False


if __name__ == "__main__":
    success = test_connection()
    if success:
        test_experiment_creation()

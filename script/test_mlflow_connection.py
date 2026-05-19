#!/usr/bin/env python3
"""
MLflow 원격 서버 연결 테스트

원격 MLflow 서버에 접속 가능한지 확인합니다.
"""

import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging
from config.mlflow_config import MLflowConfig
from src.llm_utils import MLflowLogger

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    """MLflow 연결 테스트"""
    logger.info("=" * 60)
    logger.info("MLflow 원격 서버 연결 테스트")
    logger.info("=" * 60)

    # 1. 설정 검증
    logger.info("\n[1/4] MLflow 설정 검증 중...")
    if not MLflowConfig.validate():
        logger.error("❌ 설정 검증 실패")
        logger.error("\n다음을 확인하세요:")
        logger.error("1. .env.local 파일이 프로젝트 루트에 있는지 확인")
        logger.error("2. 다음 환경변수가 설정되어 있는지 확인:")
        logger.error("   - MLFLOW_TRACKING_URI (예: http://your-domain.com:5001)")
        logger.error("   - MLFLOW_TRACKING_USERNAME")
        logger.error("   - MLFLOW_TRACKING_PASSWORD")
        return False

    logger.info(f"✓ 설정 검증 완료")
    logger.info(f"   추적 서버 URI: {MLflowConfig.get_tracking_uri()}")

    # 2. MLflow 로거 초기화
    logger.info("\n[2/4] MLflow 로거 초기화 중...")
    try:
        mlflow_logger = MLflowLogger(validate_connection=True)
        logger.info("✓ MLflow 로거 초기화 완료")
    except RuntimeError as e:
        logger.error(f"❌ 초기화 실패: {str(e)}")
        return False

    # 3. 실험 목록 조회
    logger.info("\n[3/4] 실험 목록 조회 중...")
    try:
        experiments = mlflow_logger.search_experiments(max_results=5)
        logger.info(f"✓ {len(experiments)}개의 실험 발견")
        for exp in experiments:
            logger.info(f"   - {exp['name']} (ID: {exp['experiment_id']})")
    except Exception as e:
        logger.error(f"❌ 실험 조회 실패: {str(e)}")
        return False

    # 4. 테스트 실행 생성
    logger.info("\n[4/4] 테스트 실행 생성 중...")
    try:
        run_id = mlflow_logger.start_run(
            experiment_name="llm/connection_test",
            run_name="test_connection",
            tags={"purpose": "connection_test", "status": "testing"},
        )
        logger.info(f"✓ 테스트 실행 생성 완료 (Run ID: {run_id})")

        # 테스트 메트릭 로깅
        mlflow_logger.log_params(
            {
                "test_type": "connection",
                "model": "test",
            }
        )
        mlflow_logger.log_metrics(
            {
                "connection_status": 1.0,  # 1 = 연결 성공
                "latency_ms": 100.0,
            }
        )
        logger.info("✓ 테스트 메트릭 로깅 완료")

        # 실행 종료
        mlflow_logger.end_run(status="FINISHED")
        logger.info("✓ 테스트 실행 종료")

    except Exception as e:
        logger.error(f"❌ 테스트 실행 생성 실패: {str(e)}")
        return False

    # 최종 결과
    logger.info("\n" + "=" * 60)
    logger.info("✅ MLflow 원격 서버 연결 성공!")
    logger.info("=" * 60)
    logger.info(f"\n웹 UI에서 실험을 확인하세요:")
    logger.info(f"   URL: {MLflowConfig.get_tracking_uri()}")
    logger.info(f"   실험명: llm/connection_test")
    logger.info(f"   Run ID: {run_id}")

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

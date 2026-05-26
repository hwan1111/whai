"""
MLflow 원격 서버 클라이언트

원격 MLflow 추적 서버와 통신하고 실험, 메트릭, 아티팩트를 관리합니다.
"""

import logging
import os
from typing import Any, Optional
from urllib.parse import urlparse, urlunparse

import mlflow
from config.mlflow_config import MLflowConfig

logger = logging.getLogger(__name__)

# 프록시 무시 설정 (원격 MLflow 서버 접근용)
# HTTP/HTTPS 프록시가 원격 서버를 차단하는 경우 대비
os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)
os.environ.pop("http_proxy", None)
os.environ.pop("https_proxy", None)


class MLflowLogger:
    """원격 MLflow 서버와의 상호작용을 관리하는 클래스"""

    def __init__(self, validate_connection: bool = True):
        """
        MLflow 로거 초기화

        Args:
            validate_connection: 초기화 시 연결 검증 여부

        Raises:
            RuntimeError: 원격 서버에 연결할 수 없을 때
        """
        self.tracking_uri = self._build_authenticated_uri(
            MLflowConfig.get_tracking_uri(),
            MLflowConfig.MLFLOW_TRACKING_USERNAME,
            MLflowConfig.MLFLOW_TRACKING_PASSWORD,
        )
        mlflow.set_tracking_uri(self.tracking_uri)

        if validate_connection:
            self._validate_connection()

        logger.info(f"✓ MLflow 추적 서버 연결됨")

    @staticmethod
    def _build_authenticated_uri(
        base_uri: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> str:
        """
        인증 정보가 포함된 URI 생성

        Args:
            base_uri: 기본 URI
            username: 사용자명
            password: 비밀번호

        Returns:
            인증 정보가 포함된 URI
        """
        if not (username and password):
            return base_uri

        # URI 파싱
        parsed = urlparse(base_uri)

        # 새로운 netloc 생성 (username:password@host:port)
        netloc = f"{username}:{password}@{parsed.hostname}"
        if parsed.port:
            netloc += f":{parsed.port}"

        # 새로운 URI 생성
        return urlunparse(
            (parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment)
        )

    def _validate_connection(self) -> bool:
        """
        원격 MLflow 서버 연결 확인

        Returns:
            연결 성공 시 True

        Raises:
            RuntimeError: 연결 실패 시
        """
        try:
            # 간단한 테스트: 원격 서버에 접근 가능한지 확인
            client = mlflow.tracking.MlflowClient(tracking_uri=self.tracking_uri)
            experiments = client.search_experiments(max_results=1)
            logger.info("✓ MLflow 원격 서버 연결 검증 완료")
            return True
        except Exception as e:
            error_msg = (
                f"❌ MLflow 원격 서버 연결 실패\n"
                f"   URI: {self.tracking_uri}\n"
                f"   오류: {str(e)}\n\n"
                f"   다음을 확인하세요:\n"
                f"   1. .env.local에서 MLFLOW_TRACKING_URI 설정 확인\n"
                f"   2. 원격 서버가 실행 중인지 확인\n"
                f"   3. 네트워크 연결 확인"
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def set_experiment(self, experiment_name: str) -> str:
        """
        실험 설정 (없으면 생성)

        Args:
            experiment_name: 실험 이름

        Returns:
            실험 ID
        """
        try:
            experiment = mlflow.get_experiment_by_name(experiment_name)
            if experiment is None:
                experiment_id = mlflow.create_experiment(experiment_name)
                logger.info(f"✓ 새 실험 생성: {experiment_name} (ID: {experiment_id})")
                return experiment_id
            else:
                logger.info(f"✓ 기존 실험 사용: {experiment_name}")
                return experiment.experiment_id
        except Exception as e:
            logger.error(f"❌ 실험 설정 실패: {experiment_name}, 오류: {str(e)}")
            raise

    def start_run(
        self,
        experiment_name: str,
        run_name: Optional[str] = None,
        tags: Optional[dict[str, str]] = None,
    ) -> str:
        """
        새 실행(Run) 시작

        Args:
            experiment_name: 실험 이름
            run_name: 실행 이름 (선택)
            tags: 태그 딕셔너리 (선택)

        Returns:
            실행 ID
        """
        try:
            # 실험 설정
            self.set_experiment(experiment_name)
            mlflow.set_experiment(experiment_name)

            # 실행 시작
            run = mlflow.start_run(run_name=run_name)
            run_id = run.info.run_id

            # 태그 설정
            if tags:
                mlflow.set_tags(tags)

            logger.info(f"✓ 실행 시작: {run_id} (실험: {experiment_name})")
            return run_id

        except Exception as e:
            logger.error(f"❌ 실행 시작 실패, 오류: {str(e)}")
            raise

    def log_params(self, params: dict[str, Any]) -> None:
        """
        파라미터 로깅

        Args:
            params: 파라미터 딕셔너리
        """
        try:
            mlflow.log_params(params)
            logger.debug(f"✓ 파라미터 로깅: {len(params)}개")
        except Exception as e:
            logger.error(f"❌ 파라미터 로깅 실패, 오류: {str(e)}")
            raise

    def log_metrics(self, metrics: dict[str, float], step: Optional[int] = None) -> None:
        """
        메트릭 로깅

        Args:
            metrics: 메트릭 딕셔너리
            step: 스텝 번호 (선택)
        """
        try:
            mlflow.log_metrics(metrics, step=step)
            logger.debug(f"✓ 메트릭 로깅: {len(metrics)}개")
        except Exception as e:
            logger.error(f"❌ 메트릭 로깅 실패, 오류: {str(e)}")
            raise

    def log_artifact(self, local_path: str, artifact_path: Optional[str] = None) -> None:
        """
        파일 아티팩트 로깅

        Args:
            local_path: 로컬 파일 경로
            artifact_path: 원격 아티팩트 경로 (선택)
        """
        try:
            mlflow.log_artifact(local_path, artifact_path=artifact_path)
            logger.debug(f"✓ 아티팩트 로깅: {local_path}")
        except Exception as e:
            logger.error(f"❌ 아티팩트 로깅 실패, 오류: {str(e)}")
            raise

    def end_run(self, status: str = "FINISHED") -> None:
        """
        실행 종료

        Args:
            status: 실행 상태 (FINISHED, FAILED 등)
        """
        try:
            mlflow.end_run(status=status)
            logger.info(f"✓ 실행 종료 (상태: {status})")
        except Exception as e:
            logger.error(f"❌ 실행 종료 실패, 오류: {str(e)}")
            raise

    def search_experiments(self, max_results: int = 10) -> list[dict[str, Any]]:
        """
        실험 목록 조회

        Args:
            max_results: 최대 결과 수

        Returns:
            실험 정보 리스트
        """
        try:
            client = mlflow.tracking.MlflowClient(tracking_uri=self.tracking_uri)
            experiments = client.search_experiments(max_results=max_results)
            logger.debug(f"✓ 실험 검색 완료: {len(experiments)}개")

            # MLflow 버전에 따라 다른 메서드 사용
            result = []
            for exp in experiments:
                if hasattr(exp, "to_dictionary"):
                    result.append(exp.to_dictionary())
                else:
                    # 최신 MLflow 버전: __dict__ 또는 속성 직접 접근
                    result.append(
                        {
                            "experiment_id": exp.experiment_id,
                            "name": exp.name,
                            "artifact_location": exp.artifact_location,
                            "lifecycle_stage": exp.lifecycle_stage,
                            "tags": getattr(exp, "tags", {}),
                        }
                    )
            return result
        except Exception as e:
            logger.error(f"❌ 실험 검색 실패, 오류: {str(e)}")
            raise

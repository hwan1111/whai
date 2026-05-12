"""
MLflow 추적 모듈
- LLM 실험 메트릭 기록
- 독립적인 모듈로 운영
"""

import json
from typing import Any
from pathlib import Path

try:
    import mlflow
    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False


class MLflowTracker:
    """MLflow 추적 관리자"""

    def __init__(self, experiment_name: str = "llm/news_summarization"):
        """
        Args:
            experiment_name: MLflow experiment 이름
        """
        if not MLFLOW_AVAILABLE:
            raise ImportError("mlflow not installed. Run: pip install mlflow")

        self.experiment_name = experiment_name
        self._setup_experiment()

    def _setup_experiment(self) -> None:
        """MLflow 실험 설정"""
        mlflow.set_experiment(self.experiment_name)

    def start_run(self, run_name: str, params: dict[str, Any]) -> None:
        """
        실행 시작

        Args:
            run_name: 실행 이름 (e.g., "openai-gpt-oss-20articles")
            params: 파라미터 dict
        """
        self.run = mlflow.start_run(run_name=run_name)

        # 파라미터 기록
        for key, value in params.items():
            mlflow.log_param(key, value)

        print(f"✓ MLflow Run 시작: {run_name}")
        print(f"  Experiment: {self.experiment_name}")

    def log_metrics(self, metrics: dict[str, float]) -> None:
        """
        메트릭 기록

        Args:
            metrics: 메트릭 dict (e.g., {"input_tokens": 873, "elapsed_sec": 10.7})
        """
        for key, value in metrics.items():
            mlflow.log_metric(key, value)

    def log_artifact_json(self, data: Any, filename: str = "results.json") -> None:
        """
        JSON artifact 저장

        Args:
            data: 저장할 데이터
            filename: 파일명
        """
        # 임시 파일에 저장
        temp_path = Path(f"/tmp/{filename}")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        # MLflow에 업로드
        mlflow.log_artifact(str(temp_path), artifact_path=".")
        print(f"✓ Artifact 저장: {filename}")

        # 정리
        temp_path.unlink()

    def log_samples(self, samples: list[dict[str, str]], filename: str = "summary_samples.txt") -> None:
        """
        요약 샘플 텍스트 저장

        Args:
            samples: 샘플 목록 (title, summary 포함)
            filename: 파일명
        """
        content = ""
        for i, sample in enumerate(samples[:5], 1):  # 상위 5개만
            content += f"\n{'='*80}\n"
            content += f"[샘플 {i}] {sample.get('title', 'N/A')[:60]}\n"
            content += f"{'='*80}\n"
            content += f"{sample.get('summary', 'N/A')}\n"

        # 임시 파일 저장
        temp_path = Path(f"/tmp/{filename}")
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(content)

        # MLflow에 업로드
        mlflow.log_artifact(str(temp_path), artifact_path=".")
        print(f"✓ 샘플 저장: {filename}")

        # 정리
        temp_path.unlink()

    def end_run(self) -> None:
        """실행 종료"""
        mlflow.end_run()
        print("✓ MLflow Run 종료")

    @staticmethod
    def get_ui_url() -> str:
        """MLflow UI URL"""
        return "http://localhost:5000"


# ============================================================================
# 간편 함수들
# ============================================================================

def create_tracker(experiment_name: str = "llm/news_summarization") -> MLflowTracker | None:
    """
    Tracker 생성 (MLflow 미설치 시 None 반환)

    Args:
        experiment_name: 실험 이름

    Returns:
        MLflowTracker 또는 None
    """
    if not MLFLOW_AVAILABLE:
        print("⚠️  MLflow not installed. Metrics will not be tracked.")
        print("   Install: pip install mlflow")
        return None

    try:
        return MLflowTracker(experiment_name)
    except Exception as e:
        print(f"⚠️  MLflow initialization failed: {e}")
        return None

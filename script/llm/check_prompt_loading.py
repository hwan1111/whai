"""MLflow Prompt Registry 연동 수동 점검 스크립트

regime_analysis 유저 템플릿이 MLflow Prompt Registry
(prompts:/regime_news_summarys/3)에서 정상적으로 로드되는지 확인한다.
실제 MLflow 서버에 접속하므로 pytest 단위 테스트에는 포함하지 않는다.

사용:
    PYTHONPATH=. python script/llm/check_prompt_loading.py
"""

import mlflow
from dotenv import load_dotenv

from src.llm_utils.mlflow_logger import MLflowLogger

load_dotenv(".env")
MLflowLogger(validate_connection=False)  # mlflow.set_tracking_uri(.env 값으로) 호출

pv = mlflow.genai.load_prompt("prompts:/regime_news_summarys/3")
print(pv.template)

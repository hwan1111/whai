"""MLflow Prompt Registry 연동 수동 점검 (이전 위치)

실제 MLflow 서버에 네트워크 접속하는 수동 점검 스크립트이므로
pytest 자동 실행 대상이 아니다. 최신 버전은
script/llm/check_prompt_loading.py 를 사용한다.

사용:
    PYTHONPATH=. python script/llm/check_prompt_loading.py
"""

import pytest

pytest.skip(
    "수동 점검 스크립트입니다. script/llm/check_prompt_loading.py 를 사용하세요.",
    allow_module_level=True,
)

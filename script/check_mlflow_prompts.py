#!/usr/bin/env python3
"""MLflow Prompt Registry 상태 확인 스크립트"""

import logging
import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))

# .env 로드 (.env.local이 있으면 우선 사용, 없으면 .env 사용)
env_dir = Path(__file__).parent.parent
load_dotenv(env_dir / ".env.local" if (env_dir / ".env.local").exists() else env_dir / ".env")

from model.llm.prompt_loader import (
    load_prompt,
    list_mlflow_prompts,
    MLFLOW_PROMPT_URI,
    MLFLOW_TRACKING_URI,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main():
    print("\n" + "=" * 70)
    print("MLflow Prompt Registry 상태 확인")
    print("=" * 70)

    # 0. 설정 확인
    print(f"\n📍 MLflow 트래킹 서버: {MLFLOW_TRACKING_URI}")
    print(f"📍 MLflow 프롬프트 URI: {MLFLOW_PROMPT_URI}")
    username = os.getenv("MLFLOW_TRACKING_USERNAME")
    if username:
        print(f"📍 인증: {username}@MLflow")

    # 1. MLflow에 등록된 프롬프트 목록
    print("\n" + "-" * 70)
    print("1️⃣  MLflow에 등록된 프롬프트:")
    prompts = list_mlflow_prompts(tracking_uri=MLFLOW_TRACKING_URI)
    if prompts:
        for name, desc in prompts.items():
            print(f"   ✓ {name}")
            if desc:
                print(f"     → {desc}")
    else:
        print("   ⚠️  등록된 프롬프트 없음 또는 MLflow 연결 불가")

    # 2. 실제 로드 시도
    print("\n" + "-" * 70)
    print("2️⃣  프롬프트 로드 테스트:")
    system, template = load_prompt(tracking_uri=MLFLOW_TRACKING_URI)
    print(f"   ✓ 시스템 프롬프트: {len(system)} 문자")
    print(f"   ✓ 유저 템플릿: {len(template)} 문자")
    print(f"   ✓ 템플릿 미리보기: {template[:100]}...")

    print("\n" + "=" * 70 + "\n")


if __name__ == "__main__":
    main()

"""pytest 공통 설정 — 프로젝트 루트를 sys.path에 추가"""

import os
import sys
from pathlib import Path

# backend.db 는 import 시점에 SQLAlchemy 엔진을 생성하므로, 테스트에서는
# 실제 DB 대신 sqlite 인메모리 URL 을 기본값으로 둔다 (실 연결은 발생하지 않음).
os.environ.setdefault("SERVICE_DATABASE_URL", "sqlite://")

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

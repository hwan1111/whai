# Database Management

Aiven MySQL 관리, 마이그레이션, 모니터링을 위한 디렉토리.

## 데이터베이스 구조

```
Aiven MySQL (mysql-12676458-whai.b.aivencloud.com)
├── whai_service     ← 서비스 데이터 (포트폴리오, 거래, 뉴스 등)
└── mlflow       ← 관리/모니터링 (MLflow, 로깅, 감사 등)
```

## 디렉토리 구조

```
db/
  ├── config/         # Aiven 연결 설정
  │   └── aiven.py    # AivenConfig 클래스
  ├── init/           # 초기화 스크립트 (향후)
  ├── migrations/     # Alembic 마이그레이션 (향후)
  └── scripts/        # 유틸리티 스크립트
      ├── init_databases.py   # 모든 DB 초기화
      └── test_connection.py  # 연결 테스트
```

## 사용법

### 1️⃣ 데이터베이스 초기화 (처음 1회만)
```bash
python db/scripts/init_databases.py
```
이 명령어가:
- `whai_service` 데이터베이스 생성
- `mlflow` 데이터베이스 생성

### 2️⃣ 연결 확인
```bash
python db/scripts/test_connection.py
```

### 3️⃣ MLflow 서버 시작
```bash
python script/run_mlflow.py
```

## 환경 변수

`.env` 또는 `.env.local`에서:

```env
# 서비스 데이터베이스 (기본 애플리케이션)
SERVICE_DATABASE_URL=mysql+pymysql://user:pass@host:port/whai_service?ssl_ca=...

# 관리 데이터베이스 (MLflow 등)
MLFLOW_DATABASE_URL=mysql+pymysql://user:pass@host:port/mlflow?ssl_ca=...
```

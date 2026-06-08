#!/bin/bash
# =================================================================
# PostgreSQL 멀티 데이터베이스 초기화 스크립트
# mlflow_db와 airflow_db를 격리된 사용자로 생성
# 💡 중요: DO $$ 블록 대신 직접 SQL 명령어 사용 (CREATE DATABASE 호환성)
# =================================================================

set -e  # 오류 발생 시 즉시 종료

# =================================================================
# 1. 환경 변수 설정 (기본값)
# =================================================================
MLFLOW_USER="${MLFLOW_DB_USER:-mlflow_user}"
MLFLOW_PASSWORD="${MLFLOW_DB_PASSWORD:-mlflow_password}"
AIRFLOW_USER="${AIRFLOW_DB_USER:-airflow_user}"
AIRFLOW_PASSWORD="${AIRFLOW_DB_PASSWORD:-airflow_password}"
POSTGRES_USER="${POSTGRES_ROOT_USER:-postgres}"

echo "[INFO] PostgreSQL 멀티 DB 초기화 시작..."
echo "[INFO] Root User: $POSTGRES_USER"
echo "[INFO] MLflow User: $MLFLOW_USER (Password: ${MLFLOW_PASSWORD:0:5}***)"
echo "[INFO] Airflow User: $AIRFLOW_USER (Password: ${AIRFLOW_PASSWORD:0:5}***)"

# =================================================================
# 2. MLflow 사용자 생성
# =================================================================
echo "[INFO] MLflow 사용자 생성 중..."

psql -v ON_ERROR_STOP=0 --username "$POSTGRES_USER" <<-EOSQL
CREATE USER $MLFLOW_USER WITH PASSWORD '$MLFLOW_PASSWORD';
EOSQL

psql -v ON_ERROR_STOP=0 --username "$POSTGRES_USER" <<-EOSQL
ALTER USER $MLFLOW_USER WITH PASSWORD '$MLFLOW_PASSWORD';
EOSQL

# =================================================================
# 3. MLflow 데이터베이스 생성
# =================================================================
echo "[INFO] MLflow 데이터베이스 생성 중..."

DB_EXISTS=$(psql -v ON_ERROR_STOP=0 --username "$POSTGRES_USER" -tc "SELECT 1 FROM pg_database WHERE datname = 'mlflow_db';" 2>/dev/null | grep -q 1 && echo "true" || echo "false")

if [ "$DB_EXISTS" = "false" ]; then
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
CREATE DATABASE mlflow_db OWNER $MLFLOW_USER ENCODING 'UTF8' LC_COLLATE 'C' LC_CTYPE 'C' TEMPLATE template0;
EOSQL
    echo "[INFO] mlflow_db 생성 완료"
else
    echo "[INFO] mlflow_db는 이미 존재합니다. 스킵..."
fi

psql -v ON_ERROR_STOP=0 --username "$POSTGRES_USER" <<-EOSQL
GRANT ALL PRIVILEGES ON DATABASE mlflow_db TO $MLFLOW_USER;
ALTER DATABASE mlflow_db OWNER TO $MLFLOW_USER;
EOSQL

echo "[INFO] ✓ MLflow 데이터베이스 및 사용자 설정 완료"

# =================================================================
# 4. Airflow 사용자 생성
# =================================================================
echo "[INFO] Airflow 사용자 생성 중..."

psql -v ON_ERROR_STOP=0 --username "$POSTGRES_USER" <<-EOSQL
CREATE USER $AIRFLOW_USER WITH PASSWORD '$AIRFLOW_PASSWORD';
EOSQL

psql -v ON_ERROR_STOP=0 --username "$POSTGRES_USER" <<-EOSQL
ALTER USER $AIRFLOW_USER WITH PASSWORD '$AIRFLOW_PASSWORD';
EOSQL

# =================================================================
# 5. Airflow 데이터베이스 생성
# =================================================================
echo "[INFO] Airflow 데이터베이스 생성 중..."

DB_EXISTS=$(psql -v ON_ERROR_STOP=0 --username "$POSTGRES_USER" -tc "SELECT 1 FROM pg_database WHERE datname = 'airflow_db';" 2>/dev/null | grep -q 1 && echo "true" || echo "false")

if [ "$DB_EXISTS" = "false" ]; then
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
CREATE DATABASE airflow_db OWNER $AIRFLOW_USER ENCODING 'UTF8' LC_COLLATE 'C' LC_CTYPE 'C' TEMPLATE template0;
EOSQL
    echo "[INFO] airflow_db 생성 완료"
else
    echo "[INFO] airflow_db는 이미 존재합니다. 스킵..."
fi

psql -v ON_ERROR_STOP=0 --username "$POSTGRES_USER" <<-EOSQL
GRANT ALL PRIVILEGES ON DATABASE airflow_db TO $AIRFLOW_USER;
ALTER DATABASE airflow_db OWNER TO $AIRFLOW_USER;
EOSQL

echo "[INFO] ✓ Airflow 데이터베이스 및 사용자 설정 완료"

# =================================================================
# 6. 생성 결과 확인
# =================================================================
echo "[INFO] 생성된 데이터베이스 목록:"
psql -v ON_ERROR_STOP=0 --username "$POSTGRES_USER" -l 2>/dev/null | grep -E "mlflow_db|airflow_db" || echo "[INFO] 데이터베이스 확인 중..."

echo "[INFO] 생성된 사용자 목록:"
psql -v ON_ERROR_STOP=0 --username "$POSTGRES_USER" -c "\du" 2>/dev/null | grep -E "$MLFLOW_USER|$AIRFLOW_USER" || echo "[INFO] 사용자 확인 중..."

echo "[INFO] ✓ PostgreSQL 멀티 DB 초기화 완료!"
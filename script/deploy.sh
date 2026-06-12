#!/bin/bash
# =================================================================
# EC2 배포 스크립트
# 경로: whai/script/deploy.sh
# 용도: GitHub Actions에서 호출되어 EC2에서 최신 이미지를 풀 및 배포
#
# 사용법 (수동):
#   cd /path/to/whai
#   bash script/deploy.sh
# =================================================================

set -e

REPO_DIR="/path/to/whai"  # EC2에서 실제 경로로 변경
LOG_FILE="/var/log/whai-deploy.log"
AWS_REGION="ap-northeast-2"

# 로깅 함수
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "================================"
log "배포 시작"
log "================================"

# 1. 저장소 업데이트
log "1. 저장소 최신 코드 풀..."
cd "$REPO_DIR"
git fetch origin main
git reset --hard origin/main

# 2. AWS ECR 로그인
log "2. AWS ECR 로그인..."
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin \
  "$(aws sts get-caller-identity --query Account --output text).dkr.ecr.$AWS_REGION.amazonaws.com"

# 3. 최신 이미지 풀
log "3. 최신 이미지 풀..."
REGISTRY="$(aws sts get-caller-identity --query Account --output text).dkr.ecr.$AWS_REGION.amazonaws.com"

docker pull "$REGISTRY/whai-backend:latest"
docker pull "$REGISTRY/whai-frontend:latest"

# 4. 서비스 재시작
log "4. 서비스 재시작..."
BACKEND_IMAGE="$REGISTRY/whai-backend:latest" \
FRONTEND_IMAGE="$REGISTRY/whai-frontend:latest" \
docker compose down || true
docker compose up -d

# 6. 헬스 체크
log "6. 헬스 체크..."
sleep 5
if docker compose exec -T backend curl -f http://localhost:8000/health 2>/dev/null; then
    log "✓ 백엔드 정상"
else
    log "⚠ 백엔드 헬스 체크 실패"
fi

if curl -f http://localhost:3000 2>/dev/null >/dev/null; then
    log "✓ 프론트엔드 정상"
else
    log "⚠ 프론트엔드 헬스 체크 실패"
fi

log "================================"
log "배포 완료"
log "================================"
docker compose ps

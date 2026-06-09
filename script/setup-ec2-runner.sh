#!/bin/bash
# =================================================================
# EC2 GitHub Actions Runner 초기 설정 스크립트
# 경로: whai/script/setup-ec2-runner.sh
#
# 사용법:
#   1. EC2에 SSH 접속
#   2. bash setup-ec2-runner.sh
#   3. 프롬프트에 GitHub 토큰 입력
# =================================================================

set -e

echo "======================================"
echo "EC2 GitHub Actions Runner 설정"
echo "======================================"

# 1. 시스템 업데이트
echo "1. 시스템 패키지 업데이트..."
sudo apt-get update
sudo apt-get upgrade -y

# 2. 필수 도구 설치
echo "2. 필수 도구 설치..."
sudo apt-get install -y \
  curl \
  wget \
  git \
  jq \
  unzip \
  docker.io \
  docker-compose \
  python3.12 \
  python3.12-venv \
  python3-pip \
  nodejs \
  npm

# AWS CLI 설치 (pipx 또는 pip로 설치)
echo "2-1. AWS CLI 설치..."
if ! command -v aws &> /dev/null; then
  if command -v pipx &> /dev/null; then
    sudo pipx install awscli
    sudo pipx ensurepath
  else
    sudo pip3 install --break-system-packages awscli
  fi
fi

# 3. Docker 권한 설정
echo "3. Docker 권한 설정..."
sudo usermod -aG docker ubuntu
sudo usermod -aG docker root

# 4. GitHub Actions Runner 디렉토리 생성
echo "4. GitHub Actions Runner 디렉토리 생성..."
RUNNER_DIR="/opt/github-actions-runner"
sudo mkdir -p "$RUNNER_DIR"
sudo chown -R ubuntu:ubuntu "$RUNNER_DIR"
cd "$RUNNER_DIR"

# 5. Runner 다운로드
echo "5. GitHub Actions Runner 다운로드..."
RUNNER_VERSION=$(curl -s https://api.github.com/repos/actions/runner/releases/latest | jq -r '.tag_name' | sed 's/v//')
curl -O -L https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz
tar xzf actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz
rm actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz

# 6. Runner 의존성 설치
echo "6. Runner 의존성 설치..."
bash ./bin/installdependencies.sh

# 7. Runner 등록 설정
echo "7. GitHub Runner 등록 설정..."
echo ""
echo "다음 정보를 입력하세요:"
echo "- GitHub Repository URL: https://github.com/hwan1111/whai"
echo "- Runner 인증 토큰: https://github.com/hwan1111/whai/settings/actions/runners 에서 확인"
echo ""

read -p "GitHub 저장소 URL 입력 (기본값: https://github.com/hwan1111/whai): " REPO_URL
REPO_URL="${REPO_URL:-https://github.com/hwan1111/whai}"

read -sp "GitHub 인증 토큰 입력: " GITHUB_TOKEN
echo ""

# Runner 등록
./config.sh \
  --url "$REPO_URL" \
  --token "$GITHUB_TOKEN" \
  --name "ec2-runner-$(hostname)" \
  --labels "ec2,production" \
  --unattended

# 8. systemd 서비스 등록
echo "8. systemd 서비스로 등록..."
sudo ./svc.sh install ubuntu

# 9. 서비스 시작
echo "9. 서비스 시작..."
sudo systemctl daemon-reload
sudo systemctl enable actions.runner.*
sudo systemctl start actions.runner.*

# 10. 프로젝트 저장소 클론
echo "10. 프로젝트 저장소 클론..."
PROJECT_DIR="/opt/whai-project"
sudo mkdir -p "$PROJECT_DIR"
sudo chown -R ubuntu:ubuntu "$PROJECT_DIR"
cd "$PROJECT_DIR"
git clone https://github.com/hwan1111/whai.git .

# 11. Docker network 생성
echo "11. Docker network 생성..."
docker network create whai-network 2>/dev/null || true

# 12. AWS CLI 설정
echo "12. AWS CLI 설정..."
echo ""
echo "AWS 자격증명을 설정하세요 (선택사항):"
read -p "AWS Access Key ID 입력 (선택): " AWS_ACCESS_KEY_ID
if [ -n "$AWS_ACCESS_KEY_ID" ]; then
  read -sp "AWS Secret Access Key 입력: " AWS_SECRET_ACCESS_KEY
  echo ""

  mkdir -p ~/.aws
  cat > ~/.aws/credentials << EOF
[default]
aws_access_key_id = $AWS_ACCESS_KEY_ID
aws_secret_access_key = $AWS_SECRET_ACCESS_KEY
EOF

  cat > ~/.aws/config << EOF
[default]
region = ap-northeast-2
output = json
EOF

  chmod 600 ~/.aws/credentials
fi

echo ""
echo "======================================"
echo "✓ 설정 완료!"
echo "======================================"
echo ""
echo "다음 단계:"
echo "1. GitHub 저장소에서 Runner 상태 확인:"
echo "   https://github.com/hwan1111/whai/settings/actions/runners"
echo ""
echo "2. 서비스 상태 확인:"
echo "   sudo systemctl status actions.runner.*"
echo ""
echo "3. 배포 테스트:"
echo "   - 테스트 PR 생성"
echo "   - main으로 머지"
echo "   - 배포 진행 확인"
echo ""

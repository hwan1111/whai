# CI/CD 자동 배포 설정 가이드

이 문서는 GitHub Actions + ECR + EC2 자동 배포 파이프라인 설정 과정을 설명합니다.

## 🎯 아키텍처

```
PR 생성 → GitHub Actions (테스트: pytest, npm test)
         ↓ (테스트 통과시)
      자동 머지 (squash)
         ↓
   main에 푸시
         ↓
  GitHub Actions Runner
    ├─ ECR 로그인
    ├─ Docker 이미지 빌드 & 푸시
    └─ EC2 배포 트리거
         ↓
   EC2 (self-hosted runner)
    ├─ 최신 이미지 풀
    ├─ docker-compose 재시작
    └─ 헬스 체크
```

---

## 📋 필수 준비물

### 1. AWS 계정 정보
다음 명령어로 확인하세요:

```bash
# Account ID 확인
aws sts get-caller-identity --query Account --output text

# EC2 인스턴스 정보 확인
aws ec2 describe-instances \
  --region ap-northeast-2 \
  --query 'Reservations[*].Instances[*].{ID:InstanceId,IP:PrivateIpAddress,State:State.Name}' \
  --output table
```

### 2. GitHub Secrets 설정

GitHub 저장소 Settings → Secrets and variables → Actions 에서 다음을 추가하세요:

| Secret 이름 | 설명 | 예시 |
|-----------|------|------|
| `AWS_ACCOUNT_ID` | AWS 계정 ID | `123456789012` |
| `AWS_ROLE_TO_ASSUME` | ECR 푸시용 IAM 역할 ARN | `arn:aws:iam::123456789012:role/github-actions-ecr-role` |
| `SLACK_WEBHOOK` | Slack 배포 알림 (선택) | `https://hooks.slack.com/...` |

---

## 🔐 AWS IAM 설정

### 옵션 1: OIDC 연결 (권장)

**Step 1: AWS에서 OIDC Provider 생성**

```bash
# 1. AWS 콘솔에서 생성하거나 CLI 사용:
aws iam create-openid-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1

# 응답에서 ARN 메모 (arn:aws:iam::ACCOUNT:oidc-provider/...)
```

**Step 2: IAM 역할 생성**

```bash
# Trust policy JSON 파일 생성
cat > /tmp/trust-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
          "token.actions.githubusercontent.com:sub": "repo:hwan1111/whai:ref:refs/heads/main"
        }
      }
    }
  ]
}
EOF

# ACCOUNT_ID를 실제 값으로 변경
sed -i 's/ACCOUNT_ID/123456789012/g' /tmp/trust-policy.json

# 역할 생성
aws iam create-role \
  --role-name github-actions-ecr-role \
  --assume-role-policy-document file:///tmp/trust-policy.json
```

**Step 3: ECR 권한 정책 추가**

```bash
cat > /tmp/ecr-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecr:PutImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload",
        "ecr:GetAuthorizationToken"
      ],
      "Resource": "arn:aws:ecr:ap-northeast-2:*:repository/whai-*"
    },
    {
      "Effect": "Allow",
      "Action": "ecr:GetAuthorizationToken",
      "Resource": "*"
    }
  ]
}
EOF

aws iam put-role-policy \
  --role-name github-actions-ecr-role \
  --policy-name ecr-access \
  --policy-document file:///tmp/ecr-policy.json
```

### 옵션 2: IAM 사용자 자격증명 (간단하지만 덜 안전)

```bash
# IAM 사용자 생성
aws iam create-user --user-name github-actions-ecr

# ECR 정책 추가
aws iam attach-user-policy \
  --user-name github-actions-ecr \
  --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPower

# Access Key 생성
aws iam create-access-key --user-name github-actions-ecr
```

GitHub Secrets에 추가:
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`

---

## 🚀 EC2 GitHub Actions Runner 설정

### Step 1: EC2에 Runner 설치

EC2에 SSH로 접속한 후:

```bash
# 1. 작업 디렉토리 생성
mkdir -p /opt/github-actions-runner
cd /opt/github-actions-runner

# 2. Runner 다운로드 (최신 버전)
VERSION=$(curl -s https://api.github.com/repos/actions/runner/releases/latest | grep tag_name | cut -d '"' -f 4 | sed 's/v//')
wget https://github.com/actions/runner/releases/download/v${VERSION}/actions-runner-linux-x64-${VERSION}.tar.gz
tar xzf actions-runner-linux-x64-${VERSION}.tar.gz
rm actions-runner-linux-x64-${VERSION}.tar.gz

# 3. Runner 권한 설정
sudo chown -R ubuntu:ubuntu /opt/github-actions-runner
```

### Step 2: GitHub에서 Runner 등록

GitHub 저장소 Settings → Actions → Runners → New self-hosted runner:

```bash
# GitHub에서 제공한 명령어 실행 (예):
cd /opt/github-actions-runner

./config.sh \
  --url https://github.com/hwan1111/whai \
  --token <GITHUB_TOKEN> \
  --name ec2-runner-1 \
  --labels ec2,production \
  --runnergroup default \
  --work _work
```

### Step 3: Runner를 systemd 서비스로 등록

```bash
# Runner를 서비스로 설치
cd /opt/github-actions-runner
sudo ./svc.sh install ubuntu

# 서비스 시작
sudo systemctl start actions.runner.hwan1111-whai.ec2-runner-1.service
sudo systemctl enable actions.runner.hwan1111-whai.ec2-runner-1.service

# 상태 확인
sudo systemctl status actions.runner.hwan1111-whai.ec2-runner-1.service
```

### Step 4: EC2에 필수 도구 설치

```bash
# Docker (이미 설치되어 있다면 스킵)
sudo apt-get update
sudo apt-get install -y docker.io docker-compose

# Python 및 Node.js
sudo apt-get install -y python3.12 python3.12-venv nodejs npm

# AWS CLI
sudo apt-get install -y awscli

# Runner 사용자에게 Docker 권한 추가
sudo usermod -aG docker ubuntu
```

---

## ✅ ECR 저장소 생성

```bash
# Backend 저장소
aws ecr create-repository \
  --repository-name whai-backend \
  --region ap-northeast-2

# Frontend 저장소
aws ecr create-repository \
  --repository-name whai-frontend \
  --region ap-northeast-2

# 생명주기 정책 설정 (오래된 이미지 자동 삭제)
cat > /tmp/ecr-policy.json << 'EOF'
{
  "rules": [
    {
      "rulePriority": 1,
      "description": "Keep last 10 images",
      "selection": {
        "tagStatus": "any",
        "countType": "imageCountMoreThan",
        "countNumber": 10
      },
      "action": {
        "type": "expire"
      }
    }
  ]
}
EOF

aws ecr put-lifecycle-policy \
  --repository-name whai-backend \
  --lifecycle-policy-text file:///tmp/ecr-policy.json \
  --region ap-northeast-2
```

---

## 🧪 테스트

### 1. PR 생성 및 테스트 확인

```bash
# 로컬에서 브랜치 생성
git checkout -b test/ci-setup
echo "# Test" >> README.md
git add README.md
git commit -m "test: CI workflow"
git push origin test/ci-setup
```

GitHub에서 PR을 생성하면:
- ✓ `test-backend` 실행
- ✓ `test-frontend` 실행
- ✓ 자동 머지 (테스트 통과시)

### 2. 배포 확인

```bash
# EC2에서 로그 확인
sudo journalctl -u actions.runner.hwan1111-whai.ec2-runner-1.service -f

# Docker 로그 확인
docker logs -f whai_backend
docker logs -f whai_frontend
```

---

## 🐛 트러블슈팅

### Runner가 작업을 받지 않음
```bash
# EC2에서 runner 상태 확인
cd /opt/github-actions-runner
./run.sh --once

# 서비스 로그 확인
sudo journalctl -u actions.runner.hwan1111-whai.ec2-runner-1.service -n 50
```

### ECR 로그인 실패
```bash
# AWS 자격증명 확인
aws sts get-caller-identity

# ECR 권한 확인
aws iam list-user-policies --user-name github-actions-ecr
```

### Docker 빌드 실패
```bash
# EC2에서 수동 빌드 테스트
cd /path/to/whai
docker build -f backend/Dockerfile.backend .
```

---

## 📚 추가 설정

### Slack 알림 추가 (선택)

1. Slack Workspace에서 Incoming Webhook 생성
2. GitHub Secrets에 `SLACK_WEBHOOK` 추가

### Branch Protection Rule 설정

GitHub 저장소 Settings → Branches → Add rule:
- Branch name pattern: `main`
- ✓ Require status checks to pass before merging
- ✓ Require branches to be up to date before merging
- ✓ Require code reviews before merging (선택사항)

---

## 🔄 수동 배포

긴급하게 배포해야 할 경우:

```bash
# EC2에서 수동 실행
cd /path/to/whai
bash script/deploy.sh
```

---

## 📊 모니터링

```bash
# Docker 컨테이너 상태 확인
docker compose ps

# 리소스 사용량
docker stats

# 로그 확인
docker compose logs -f backend
docker compose logs -f frontend
```

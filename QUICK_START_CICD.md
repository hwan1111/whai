# 🚀 CI/CD 자동 배포 - 빠른 시작 가이드

5분 안에 GitHub Actions + ECR + EC2 자동 배포를 설정하세요.

---

## 📋 체크리스트

### Step 1: AWS IAM 설정 (5분)
로컬에서 AWS CLI를 사용하여 IAM 역할과 ECR 저장소를 자동 생성합니다.

```bash
# AWS 자격증명 확인
aws sts get-caller-identity

# IAM 자동 설정 실행
bash script/setup-aws-iam.sh
```

**출력된 정보를 메모해두세요:**
- `AWS_ACCOUNT_ID`
- `AWS_ROLE_TO_ASSUME` (ARN)

### Step 2: GitHub Secrets 추가 (2분)
https://github.com/hwan1111/whai/settings/secrets/actions

```
AWS_ACCOUNT_ID = 123456789012
AWS_ROLE_TO_ASSUME = arn:aws:iam::123456789012:role/github-actions-ecr-role
SLACK_WEBHOOK = (선택사항)
```

### Step 3: EC2 GitHub Actions Runner 설정 (10분)

**EC2에 SSH 접속 후:**

```bash
# 1. 저장소 클론
git clone https://github.com/hwan1111/whai.git
cd whai

# 2. 자동 설정 실행
bash script/setup-ec2-runner.sh

# 3. GitHub 정보 입력
# - Repository URL: https://github.com/hwan1111/whai
# - Token: https://github.com/hwan1111/whai/settings/actions/runners 에서 확인
```

**Runner 상태 확인:**

```bash
# Runner 상태
sudo systemctl status actions.runner.*

# Runner 로그
sudo journalctl -u actions.runner.* -f
```

### Step 4: 배포 테스트 (5분)

**로컬에서:**

```bash
# 테스트 브랜치 생성
git checkout -b test/ci-setup
echo "# CI/CD Test" >> README.md
git add README.md
git commit -m "test: CI/CD workflow"
git push origin test/ci-setup
```

**GitHub에서:**
1. PR 생성 → 자동 테스트 실행 대기
2. 테스트 통과 → 자동 머지
3. 배포 워크플로우 실행 대기
4. Actions 탭에서 진행 상황 확인

---

## ✅ 확인 사항

### CI 워크플로우 (PR 시)
```
✓ test-backend (pytest)
✓ test-frontend (npm test)
✓ auto-merge (테스트 통과 시)
```

### Deploy 워크플로우 (main 머지 후)
```
✓ build-and-push (ECR에 이미지 푸시)
✓ deploy-to-ec2 (EC2에서 배포)
✓ healthcheck (헬스 체크)
✓ slack-notification (선택)
```

---

## 🐛 문제 해결

### Runner가 작업을 받지 않음
```bash
# EC2에서 runner 상태 확인
cd /opt/github-actions-runner
./run.sh --once

# 서비스 재시작
sudo systemctl restart actions.runner.*
```

### ECR 로그인 실패
```bash
# AWS 자격증명 확인
aws sts get-caller-identity

# 수동으로 ECR 로그인 테스트
aws ecr get-login-password --region ap-northeast-2 | \
  docker login --username AWS --password-stdin \
  $(aws sts get-caller-identity --query Account --output text).dkr.ecr.ap-northeast-2.amazonaws.com
```

### Docker 빌드 실패
```bash
# EC2에서 수동 빌드 테스트
cd /opt/whai-project
docker build -f backend/Dockerfile.backend .
```

### 배포 후 서비스 응답 없음
```bash
# EC2에서 컨테이너 로그 확인
docker compose logs -f backend
docker compose logs -f frontend

# 컨테이너 상태 확인
docker compose ps

# 네트워크 확인
docker network ls
docker network inspect whai-network
```

---

## 📊 모니터링

### Actions 탭에서 확인
https://github.com/hwan1111/whai/actions

### EC2에서 실시간 로그 확인
```bash
# GitHub Actions Runner 로그
sudo journalctl -u actions.runner.* -f

# Docker 컨테이너 로그
docker compose logs -f

# 시스템 리소스
docker stats
```

---

## 🔄 수동 배포 (긴급)

```bash
# EC2에서
cd /opt/whai-project
BACKEND_IMAGE="123456789012.dkr.ecr.ap-northeast-2.amazonaws.com/whai-backend:latest" \
FRONTEND_IMAGE="123456789012.dkr.ecr.ap-northeast-2.amazonaws.com/whai-frontend:latest" \
docker compose down && docker compose up -d
```

또는:

```bash
bash script/deploy.sh
```

---

## 📚 더 자세한 정보

[CI/CD 설정 완전 가이드](docs/CI_CD_SETUP.md)

---

## 🎉 완료!

모든 설정이 끝났습니다. 이제:

1. ✅ PR을 생성하면 자동으로 테스트
2. ✅ 테스트 통과시 자동으로 머지
3. ✅ main에 머지되면 자동으로 배포
4. ✅ ECR에 이미지 저장
5. ✅ EC2에서 최신 이미지 실행

Happy deploying! 🚀

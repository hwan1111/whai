#!/bin/bash
# =================================================================
# AWS IAM 설정 스크립트 (OIDC 방식)
# 경로: whai/script/setup-aws-iam.sh
#
# 사용법:
#   bash script/setup-aws-iam.sh
# =================================================================

set -e

echo "======================================"
echo "AWS IAM 설정 (GitHub Actions OIDC)"
echo "======================================"

# 1. 계정 정보 확인
echo "1. AWS 계정 정보 확인..."
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION="ap-northeast-2"

echo "✓ Account ID: $AWS_ACCOUNT_ID"
echo "✓ Region: $AWS_REGION"

# 2. OIDC Provider 확인 또는 생성
echo ""
echo "2. OIDC Provider 확인..."
OIDC_ARN=$(aws iam list-open-id-connect-providers \
  --query "OpenIDConnectProviderList[?EndpointUrl=='https://token.actions.githubusercontent.com'].Arn" \
  --output text)

if [ -z "$OIDC_ARN" ]; then
  echo "✓ OIDC Provider 생성..."
  OIDC_ARN=$(aws iam create-open-id-connect-provider \
    --url https://token.actions.githubusercontent.com \
    --client-id-list sts.amazonaws.com \
    --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1 \
    --query 'OpenIDConnectProviderArn' \
    --output text)
  echo "✓ OIDC Provider 생성됨: $OIDC_ARN"
else
  echo "✓ OIDC Provider 이미 존재: $OIDC_ARN"
fi

# 3. IAM Role 생성 위한 Trust Policy
echo ""
echo "3. IAM Role Trust Policy 생성..."
cat > /tmp/trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "$OIDC_ARN"
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

# 4. IAM Role 생성 또는 업데이트
echo "4. IAM Role 생성/업데이트..."
ROLE_NAME="github-actions-ecr-role"

if ! aws iam get-role --role-name "$ROLE_NAME" 2>/dev/null; then
  echo "✓ Role 생성: $ROLE_NAME"
  aws iam create-role \
    --role-name "$ROLE_NAME" \
    --assume-role-policy-document file:///tmp/trust-policy.json \
    --description "GitHub Actions ECR access role"
else
  echo "✓ Role 업데이트: $ROLE_NAME"
  aws iam update-assume-role-policy \
    --role-name "$ROLE_NAME" \
    --policy-document file:///tmp/trust-policy.json
fi

# 5. ECR 권한 정책 추가
echo "5. ECR 권한 정책 추가..."
cat > /tmp/ecr-policy.json << EOF
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
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:DescribeRepositories"
      ],
      "Resource": [
        "arn:aws:ecr:$AWS_REGION:$AWS_ACCOUNT_ID:repository/whai-*"
      ]
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
  --role-name "$ROLE_NAME" \
  --policy-name ecr-access \
  --policy-document file:///tmp/ecr-policy.json

echo "✓ ECR 권한 정책 추가됨"

# 6. ECR 저장소 생성
echo ""
echo "6. ECR 저장소 생성..."

for REPO in "whai-backend" "whai-frontend"; do
  if aws ecr describe-repositories \
    --repository-names "$REPO" \
    --region "$AWS_REGION" 2>/dev/null >/dev/null; then
    echo "✓ 저장소 이미 존재: $REPO"
  else
    echo "✓ 저장소 생성: $REPO"
    aws ecr create-repository \
      --repository-name "$REPO" \
      --region "$AWS_REGION" \
      --image-tag-mutability MUTABLE \
      --image-scanning-configuration scanOnPush=false
  fi
done

# 7. ECR Lifecycle Policy 설정
echo "7. ECR Lifecycle Policy 설정..."
cat > /tmp/ecr-lifecycle.json << EOF
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

for REPO in "whai-backend" "whai-frontend"; do
  aws ecr put-lifecycle-policy \
    --repository-name "$REPO" \
    --lifecycle-policy-text file:///tmp/ecr-lifecycle.json \
    --region "$AWS_REGION" 2>/dev/null || true
  echo "✓ Lifecycle Policy 설정: $REPO"
done

# 8. 정보 출력
echo ""
echo "======================================"
echo "✓ AWS IAM 설정 완료!"
echo "======================================"
echo ""
echo "다음 정보를 GitHub Secrets에 추가하세요:"
echo "https://github.com/hwan1111/whai/settings/secrets/actions"
echo ""
echo "Secret 이름: AWS_ACCOUNT_ID"
echo "값: $AWS_ACCOUNT_ID"
echo ""
echo "Secret 이름: AWS_ROLE_TO_ASSUME"

ROLE_ARN=$(aws iam get-role --role-name "$ROLE_NAME" --query 'Role.Arn' --output text)
echo "값: $ROLE_ARN"
echo ""
echo "======================================"

# 정리
rm -f /tmp/trust-policy.json /tmp/ecr-policy.json /tmp/ecr-lifecycle.json

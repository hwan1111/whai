# CI/CD 파이프라인 테스트

이 파일은 GitHub Actions CI/CD 파이프라인을 테스트하기 위해 생성되었습니다.

테스트 시간: 2026-06-09 02:35:00 UTC

## 테스트 항목

- ✓ GitHub Actions 자동 테스트 (pytest, npm test)
- ✓ 자동 PR 머지
- ✓ ECR 이미지 빌드 및 푸시
- ✓ EC2 자동 배포

## 배포 확인

EC2에서 `docker compose ps`로 최신 이미지 실행 확인 가능

"""
최근 regime 공백 소급 스크립트 (3개 종목)

대상: 삼성전자(005930), LIG넥스원(079550), 신한지주(055550)
공백 구간: 2026-05-10 ~ 현재 (DAG start_date=2026-06-09, catchup=False 로 인한 누락)

실행:
    python script/others/backfill_regime_gaps.py           # 실제 실행
    python script/others/backfill_regime_gaps.py --dry-run # 확인만 (LLM·DB 미실행)
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]
PY = sys.executable

TICKERS = ["005930", "079550", "055550"]
BACKFILL_START = "2026-05-10"


def run(cmd: list[str], label: str, dry_run_mode: bool = False) -> int:
    print(f"\n{'='*60}")
    print(f"  {label}")
    if dry_run_mode:
        print(f"  [DRY-RUN] $ {' '.join(cmd)}")
        print(f"{'='*60}")
        return 0
    print(f"  $ {' '.join(cmd)}")
    print(f"{'='*60}")
    sys.stdout.flush()
    result = subprocess.run(cmd, cwd=ROOT)
    print(f"  -> exit code: {result.returncode}")
    sys.stdout.flush()
    return result.returncode


def main(dry_run: bool) -> None:
    print(f"\n{'*'*60}")
    print(f"  regime 공백 소급: {', '.join(TICKERS)}")
    print(f"  구간: {BACKFILL_START} ~ 현재")
    print(f"  모드: {'DRY-RUN (실제 반영 없음)' if dry_run else '실제 실행'}")
    print(f"{'*'*60}")

    # STEP 1: 국면 재탐지 + LLM 뉴스 요약 (start 날짜 제한 -> 기존 국면 재처리 방지)
    print("\n\n★ STEP 1: 국면 재탐지 + LLM 요약 (regime_news_summary.py)")
    for ticker in TICKERS:
        cmd = [
            PY, "script/news_data/eval/regime_news_summary.py",
            "--ticker", ticker,
            "--start", BACKFILL_START,
        ]
        if dry_run:
            cmd.append("--dry-run")
        run(cmd, f"[국면 분석] {ticker}  start={BACKFILL_START}", dry_run_mode=False)

    if dry_run:
        print("\n[DRY-RUN] STEP 2~3 건너뜀 (--dry-run 모드)")
        print("\n문제 없으면 --dry-run 없이 재실행하세요.")
        return

    # STEP 2: DB 업로드 (append: 신규만 INSERT, 날짜 겹침 국면은 교체)
    print("\n\n★ STEP 2: DB 업로드 (--mode append)")
    for ticker in TICKERS:
        run(
            [
                PY, "script/others/upload_regime_to_db.py",
                "--ticker", ticker,
                "--mode", "append",
                "--no-cleanup",  # 로컬 JSON 유지 (확인용)
            ],
            f"[DB 업로드] {ticker}",
        )

    # STEP 3: S3 summary 파이프라인
    print("\n\n★ STEP 3: S3 요약 파이프라인 (regime_news_summary_pipeline.py)")
    run(
        [
            PY, "script/llm/regime_news_summary_pipeline.py",
            "--tickers",
        ] + TICKERS,
        f"[S3 파이프라인] {' '.join(TICKERS)}",
    )

    print("\n\n완료: regime 공백 소급이 끝났습니다.")
    print("확인: 프론트엔드에서 2026-06-08 신한지주 국면 뉴스 조회 테스트 권장")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="regime 공백 소급 (3개 종목)")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="LLM/DB 반영 없이 처리 대상만 확인",
    )
    args = parser.parse_args()
    main(dry_run=args.dry_run)

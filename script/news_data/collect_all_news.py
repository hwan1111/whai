"""Collect stock, USD/KRW, and KOSPI200 news for one date range."""

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def run_collector(script: str, start: str, end: str) -> None:
    command = [
        sys.executable,
        str(ROOT / "script" / "news_data" / "collect" / script),
        "--start",
        start,
        "--end",
        end,
    ]
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="주식 10종, USD/KRW, KOSPI200 뉴스 통합 수집"
    )
    parser.add_argument("--start", required=True, help="수집 시작일 YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="수집 종료일 YYYY-MM-DD")
    args = parser.parse_args()

    run_collector("news_collector.py", args.start, args.end)
    run_collector("collect_kospi200_news.py", args.start, args.end)


if __name__ == "__main__":
    main()

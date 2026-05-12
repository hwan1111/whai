#!/usr/bin/env python3
"""
Upload local news data to AWS S3 with date-based partitioning.

Usage:
    python script/upload_news_to_s3.py \
        --local-dir data/News_삼성전자_005930 \
        --bucket fisa-news-archive \
        --ticker 005930 \
        --company 삼성전자
"""

import os
import argparse
import boto3
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional


class S3NewsUploader:
    """Upload news JSON files to S3 with date-based partitioning."""

    def __init__(self, bucket_name: str, aws_region: str = "ap-northeast-2"):
        self.bucket_name = bucket_name
        self.s3_client = boto3.client("s3", region_name=aws_region)
        self.uploaded_count = 0
        self.failed_count = 0

    def extract_date_from_filename(self, filename: str) -> Optional[tuple[str, str, str]]:
        """
        Extract year, month, day from filename (YYYY-MM-DD.json).

        Returns:
            Tuple of (year, month, day) or None if parsing fails.
        """
        try:
            # Remove .json extension
            name = filename.replace(".json", "")
            # Parse date string
            date_obj = datetime.strptime(name, "%Y-%m-%d")
            return (
                date_obj.strftime("%Y"),
                date_obj.strftime("%m"),
                date_obj.strftime("%d"),
            )
        except ValueError:
            return None

    def upload_file(
        self,
        local_path: str,
        ticker: str,
        company: str,
    ) -> bool:
        """
        Upload a single news JSON file to S3.

        Args:
            local_path: Local file path
            ticker: Stock ticker (e.g., 005930)
            company: Company name (e.g., 삼성전자)

        Returns:
            True if successful, False otherwise.
        """
        file_path = Path(local_path)
        filename = file_path.name

        # Extract date from filename
        date_parts = self.extract_date_from_filename(filename)
        if not date_parts:
            print(f"⚠️  Skipping {filename} - invalid date format")
            return False

        year, month, day = date_parts

        # Construct S3 path: raw/{ticker}/{year}/{month}/{day}/{filename}
        s3_key = f"raw/{ticker}/{year}/{month}/{day}/{filename}"

        try:
            self.s3_client.upload_file(local_path, self.bucket_name, s3_key)
            self.uploaded_count += 1
            print(f"✓ {s3_key}")
            return True
        except Exception as e:
            self.failed_count += 1
            print(f"✗ {filename} - Error: {str(e)}")
            return False

    def upload_directory(
        self,
        local_dir: str,
        ticker: str,
        company: str,
        max_workers: int = 5,
    ) -> dict:
        """
        Upload all JSON files from a directory to S3.

        Args:
            local_dir: Local directory path
            ticker: Stock ticker
            company: Company name
            max_workers: Number of concurrent upload threads

        Returns:
            Dictionary with upload summary.
        """
        local_path = Path(local_dir)

        if not local_path.exists():
            raise FileNotFoundError(f"Directory not found: {local_dir}")

        # Find all JSON files
        json_files = list(local_path.glob("*.json"))
        if not json_files:
            print(f"⚠️  No JSON files found in {local_dir}")
            return {"uploaded": 0, "failed": 0, "total": 0}

        print(f"\n📤 Starting upload: {len(json_files)} files")
        print(f"   Ticker: {ticker} ({company})")
        print(f"   Bucket: {self.bucket_name}")
        print(f"   Partition: raw/{ticker}/YYYY/MM/DD/\n")

        # Upload files concurrently
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    self.upload_file,
                    str(file_path),
                    ticker,
                    company,
                ): file_path
                for file_path in json_files
            }

            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    print(f"✗ Error: {str(e)}")

        # Summary
        print(f"\n✅ Upload Complete")
        print(f"   Uploaded: {self.uploaded_count}")
        print(f"   Failed: {self.failed_count}")
        print(f"   Total: {len(json_files)}")

        return {
            "uploaded": self.uploaded_count,
            "failed": self.failed_count,
            "total": len(json_files),
        }


def main():
    parser = argparse.ArgumentParser(
        description="Upload news data to AWS S3 with date-based partitioning"
    )
    parser.add_argument(
        "--local-dir",
        required=True,
        help="Local directory containing news JSON files",
    )
    parser.add_argument(
        "--bucket",
        required=True,
        help="S3 bucket name",
    )
    parser.add_argument(
        "--ticker",
        required=True,
        help="Stock ticker (e.g., 005930)",
    )
    parser.add_argument(
        "--company",
        required=True,
        help="Company name (e.g., 삼성전자)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=5,
        help="Number of concurrent upload threads (default: 5)",
    )

    args = parser.parse_args()

    # Upload
    uploader = S3NewsUploader(bucket_name=args.bucket)
    result = uploader.upload_directory(
        local_dir=args.local_dir,
        ticker=args.ticker,
        company=args.company,
        max_workers=args.workers,
    )

    # Exit with appropriate code
    exit(0 if result["failed"] == 0 else 1)


if __name__ == "__main__":
    main()

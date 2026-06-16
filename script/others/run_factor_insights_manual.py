"""
factor_insight 수동 실행 스크립트

DAG 없이 로컬에서 12개 종목 변동 요인 LLM 분석 후 factor_insight 테이블에 UPSERT.

실행:
    python script/others/run_factor_insights_manual.py
    python script/others/run_factor_insights_manual.py --force   # 오늘치 있어도 덮어쓰기
"""

import argparse
import json
import logging
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse

import boto3
import httpx
import pymysql
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env", override=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

_CA_CANDIDATES = [
    Path("/opt/certs/ca.pem"),
    ROOT / "config" / "certs" / "ca.pem",
]
CA_PATH = next((str(p) for p in _CA_CANDIDATES if p.exists()), str(_CA_CANDIDATES[-1]))

TICKER_FACTORS: dict[str, dict] = {
    "000000": {"name": "KOSPI",                   "factors": ["외국인 순매수", "글로벌 증시 동조화", "USD/KRW 환율"]},
    "005930": {"name": "삼성전자",                 "factors": ["시장 전체 (KOSPI)", "HBM 수요 증가", "환율 영향"]},
    "000660": {"name": "SK하이닉스",               "factors": ["시장 전체 (KOSPI)", "HBM 공급 선도", "환율 영향"]},
    "005380": {"name": "현대차",                   "factors": ["시장 전체 (KOSPI)", "전동화 전환 성과", "환율 영향"]},
    "000270": {"name": "기아",                     "factors": ["시장 전체 (KOSPI)", "EV9 판매 호조", "환율 영향"]},
    "079550": {"name": "LIG디펜스앤에어로스페이스", "factors": ["시장 전체 (KOSPI)", "방산 수주 확대", "환율 영향"]},
    "012450": {"name": "한화에어로스페이스",        "factors": ["시장 전체 (KOSPI)", "방산 수주 이슈", "환율 영향"]},
    "105560": {"name": "KB금융",                   "factors": ["시장 전체 (KOSPI)", "금리 상승 수혜", "대손충당금 증가"]},
    "055550": {"name": "신한지주",                 "factors": ["시장 전체 (KOSPI)", "금리 상승 수혜", "대출 부실 위험"]},
    "051910": {"name": "LG화학",                   "factors": ["시장 전체 (KOSPI)", "배터리 사업 부진", "글로벌 수요 약세"]},
    "096770": {"name": "SK이노베이션",              "factors": ["시장 전체 (KOSPI)", "배터리 수주 증가", "유가 변동 영향"]},
    "USD":    {"name": "USD/KRW",                  "factors": ["미 연준 통화정책", "한미 금리차", "무역수지"]},
}


def get_conn():
    raw = os.environ["SERVICE_DATABASE_URL"]
    url = urlparse(raw.replace("mysql+pymysql://", "mysql://", 1).split("?")[0])
    return pymysql.connect(
        host=url.hostname, port=url.port or 3306,
        db=url.path.lstrip("/"), user=url.username, password=url.password,
        charset="utf8mb4", ssl={"ca": CA_PATH},
        cursorclass=pymysql.cursors.DictCursor, autocommit=False,
    )


def call_llm(prompt: str) -> str:
    gateway_uri = os.environ.get("MLFLOW_GATEWAY_URL", "http://52.78.237.104:5001/gateway/mlflow/v1")
    gw_user = os.environ.get("MLFLOW_TRACKING_USERNAME", "")
    gw_pass = os.environ.get("MLFLOW_TRACKING_PASSWORD", "")
    with httpx.Client(timeout=60.0, auth=(gw_user, gw_pass)) as client:
        resp = client.post(
            f"{gateway_uri}/chat/completions",
            json={
                "model": "low_performance_llm",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "max_tokens": 700,
            },
        )
    resp.raise_for_status()
    result = resp.json()
    if "choices" in result:
        return result["choices"][0]["message"]["content"]
    if "content" in result:
        return result["content"]
    raise RuntimeError(f"예상치 못한 LLM 응답: {result}")


def main(force: bool = False):
    today_str = date.today().isoformat()
    cutoff = (date.today() - timedelta(days=21)).isoformat()
    s3_bucket = os.environ.get("AWS_S3_BUCKET", "fisa-news-archive")
    s3 = boto3.client("s3", region_name="ap-northeast-2")

    conn = get_conn()
    failed: list[str] = []
    skipped: list[str] = []
    success: list[str] = []

    try:
        for ticker, info in TICKER_FACTORS.items():
            ticker_name = info["name"]
            factors = info["factors"]
            n = len(factors)

            try:
                with conn.cursor() as cur:
                    if not force:
                        cur.execute(
                            "SELECT 1 FROM factor_insight WHERE ticker=%s AND date=%s LIMIT 1",
                            (ticker, today_str),
                        )
                        if cur.fetchone():
                            log.info("[%s] 이미 존재, 스킵 (--force 로 덮어쓰기 가능)", ticker)
                            skipped.append(ticker)
                            continue

                    cur.execute(
                        "SELECT start_date, end_date, direction, cum_return "
                        "FROM regime "
                        "WHERE ticker=%s AND end_date >= %s "
                        "ORDER BY end_date DESC LIMIT 6",
                        (ticker, cutoff),
                    )
                    rows = cur.fetchall()

                news_lines = []
                for r in rows:
                    key = f"summary/{ticker}/{r['start_date']}_{r['end_date']}.json"
                    try:
                        resp = s3.get_object(Bucket=s3_bucket, Key=key)
                        payload = json.loads(resp["Body"].read().decode("utf-8"))
                        cause = (payload.get("llm_analysis") or {}).get("cause", "")
                    except Exception:
                        cause = ""
                    if cause:
                        cum = r["cum_return"] or 0
                        news_lines.append(f"- {r['direction'] or ''} {cum:.1f}%: {cause}")

                news_context = "\n".join(news_lines) if news_lines else "(최근 뉴스 없음)"
                factors_text = "\n".join(f"{i+1}. {f}" for i, f in enumerate(factors))

                prompt = (
                    f"금융 자산 '{ticker_name}({ticker})'의 최근 뉴스 분석:\n"
                    f"{news_context}\n\n"
                    f"위 뉴스를 바탕으로 아래 {n}개 변동 요인 각각에 대해 작성하고, 종합 투자 주의사항도 작성하세요:\n"
                    f"- label: 현재 시장 상황을 반영한 짧은 요인 이름 (8자 이내)\n"
                    f"- direction: 해당 요인이 자산 가격에 미치는 방향. 반드시 상승/하락/중립 중 하나\n"
                    f"- strength: 해당 요인의 상대적인 영향 강도. 반드시 강함/보통/약함 중 하나. "
                    f"중립 요인도 근거의 뚜렷함에 따라 강도를 판단\n"
                    f"- desc: 왜 이 요인이 자산 가격의 상승 또는 하락으로 이어지는지 인과관계를 설명 "
                    f"(55자 이내, 한국어 1문장). 관찰·확인·검토·주의 등 투자자의 대응 방안은 쓰지 말 것\n"
                    f"- advice: 위 요인들을 종합한 투자 유의사항 3개. 각 항목은 서로 다른 위험을 다루고 "
                    f"35자 이내의 간결한 한국어 문장으로 작성. 매수·매도 지시나 특정 투자 행동 권유는 금지\n\n"
                    f"{factors_text}\n\n"
                    f'반드시 JSON만 반환: {{"labels":["이름1","이름2","이름3"],'
                    f'"directions":["상승","하락","중립"],"strengths":["강함","보통","약함"],'
                    f'"descs":["설명1","설명2","설명3"],'
                    f'"advice":["유의사항1","유의사항2","유의사항3"]}}'
                )

                raw_response = call_llm(prompt)
                match = re.search(r"\{.*\}", raw_response, re.DOTALL)
                if not match:
                    raise ValueError("LLM 응답에 JSON 없음")
                parsed = json.loads(match.group())

                labels = parsed.get("labels", [])
                directions = parsed.get("directions", [])
                strengths = parsed.get("strengths", [])
                descs = parsed.get("descs", [])
                advice = parsed.get("advice", [])

                if len(descs) < n:
                    raise ValueError(f"descs 부족: {len(descs)} < {n}")
                if len(directions) < n or any(d not in {"상승", "하락", "중립"} for d in directions[:n]):
                    raise ValueError("directions 검증 실패")
                if len(strengths) < n or any(s not in {"강함", "보통", "약함"} for s in strengths[:n]):
                    raise ValueError("strengths 검증 실패")
                if not isinstance(advice, list) or len(advice) < 3:
                    raise ValueError("advice 부족")

                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO factor_insight
                            (ticker, date, labels, directions, strengths, descs, advice, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                        ON DUPLICATE KEY UPDATE
                            labels=VALUES(labels),
                            directions=VALUES(directions),
                            strengths=VALUES(strengths),
                            descs=VALUES(descs),
                            advice=VALUES(advice)
                    """, (
                        ticker, today_str,
                        json.dumps(labels, ensure_ascii=False),
                        json.dumps(directions[:n], ensure_ascii=False),
                        json.dumps(strengths[:n], ensure_ascii=False),
                        json.dumps(descs, ensure_ascii=False),
                        json.dumps(advice, ensure_ascii=False),
                    ))
                conn.commit()
                log.info("[%s] %s 완료", ticker, ticker_name)
                success.append(ticker)

            except Exception as e:
                log.error("[%s] %s 실패: %s", ticker, ticker_name, e, exc_info=True)
                failed.append(ticker)

    finally:
        conn.close()

    print(f"\n{'='*50}")
    print(f"  완료: {len(success)}개  {success}")
    print(f"  스킵: {len(skipped)}개  {skipped}")
    print(f"  실패: {len(failed)}개  {failed}")
    print(f"{'='*50}")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="오늘치 있어도 덮어쓰기")
    args = parser.parse_args()
    main(force=args.force)

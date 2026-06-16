"""
Daily factor insight LLM analysis DAG.

Schedule: 16:30 UTC (01:30 KST) 평일 — finance_regime_news_summary_daily 완료 후
Depends on: finance_regime_news_summary_daily

흐름:
  1. finance_regime_news_summary_daily 완료 대기 (ExternalTaskSensor)
  2. 12개 종목(11종목 + KOSPI + USD/KRW)의 변동 요인 LLM 분석
  3. MySQL factor_insight 테이블에 UPSERT (멱등 — 동일 ticker+date 는 스킵)

안전장치:
  - retries=3, retry_exponential_backoff=True (5 → 10 → 20분)
  - 종목별 개별 실패 시 로그 후 계속 진행
  - 전체 실패 시 task 실패 → Airflow 자동 재시도
  - 이미 오늘치 데이터가 있으면 스킵 (idempotent)
"""

import json
import logging
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from airflow.decorators import dag, task

try:
    from airflow.providers.standard.sensors.external_task import ExternalTaskSensor
except ImportError:
    from airflow.sensors.external_task import ExternalTaskSensor

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # /opt (컨테이너 내부)

log = logging.getLogger(__name__)

# 티커별 이름 + 변동 요인
# frontend/src/components/StockDetailModal.jsx (STOCK_CONFIG) 및
# frontend/src/app/(app)/dashboard/page.jsx (FX_INFO) 와 동기화 필요
TICKER_FACTORS: dict[str, dict] = {
    "000000": {"name": "KOSPI",                    "factors": ["외국인 순매수", "글로벌 증시 동조화", "USD/KRW 환율"]},
    "005930": {"name": "삼성전자",                  "factors": ["시장 전체 (KOSPI)", "HBM 수요 증가", "환율 영향"]},
    "000660": {"name": "SK하이닉스",                "factors": ["시장 전체 (KOSPI)", "HBM 공급 선도", "환율 영향"]},
    "005380": {"name": "현대차",                    "factors": ["시장 전체 (KOSPI)", "전동화 전환 성과", "환율 영향"]},
    "000270": {"name": "기아",                      "factors": ["시장 전체 (KOSPI)", "EV9 판매 호조", "환율 영향"]},
    "079550": {"name": "LIG디펜스앤에어로스페이스",  "factors": ["시장 전체 (KOSPI)", "방산 수주 확대", "환율 영향"]},
    "012450": {"name": "한화에어로스페이스",          "factors": ["시장 전체 (KOSPI)", "방산 수주 이슈", "환율 영향"]},
    "105560": {"name": "KB금융",                    "factors": ["시장 전체 (KOSPI)", "금리 상승 수혜", "대손충당금 증가"]},
    "055550": {"name": "신한지주",                  "factors": ["시장 전체 (KOSPI)", "금리 상승 수혜", "대출 부실 위험"]},
    "051910": {"name": "LG화학",                    "factors": ["시장 전체 (KOSPI)", "배터리 사업 부진", "글로벌 수요 약세"]},
    "096770": {"name": "SK이노베이션",               "factors": ["시장 전체 (KOSPI)", "배터리 수주 증가", "유가 변동 영향"]},
    "USD":    {"name": "USD/KRW",                  "factors": ["미 연준 통화정책", "한미 금리차", "무역수지"]},
}


@dag(
    dag_id="finance_factor_insights_daily",
    default_args={
        "owner": "data-eng",
        "depends_on_past": False,
        "start_date": datetime(2026, 6, 16),
        "email_on_failure": True,
        "email_on_retry": False,
        "retries": 3,
        "retry_delay": timedelta(minutes=5),
        "retry_exponential_backoff": True,
        "max_retry_delay": timedelta(minutes=30),
    },
    description="종목별 변동 요인 LLM 분석 (일별)",
    schedule="30 16 * * 1-5",  # 16:30 UTC = 01:30 KST 평일 (regime_news_summary 와 동일 시작, sensor 대기)
    catchup=False,
    tags=["finance", "llm", "factor", "insight"],
    doc_md=__doc__,
)
def finance_factor_insights_daily():

    wait_for_regime_summary = ExternalTaskSensor(
        task_id="wait_for_regime_news_summary",
        external_dag_id="finance_regime_news_summary_daily",
        external_task_id=None,  # DAG 전체 완료 대기
        allowed_states=["success"],
        failed_states=["failed"],
        mode="reschedule",
        poke_interval=60,
        timeout=60 * 60 * 6,  # 최대 6시간 대기
    )

    @task()
    def run_factor_insights():
        """모든 티커의 변동 요인 LLM 분석 후 MySQL factor_insight 테이블에 UPSERT."""
        import httpx
        from dotenv import load_dotenv
        from sqlalchemy import create_engine, text

        load_dotenv(PROJECT_ROOT / ".env", override=True)

        today_str = date.today().isoformat()  # UTC 기준 오늘 날짜 (YYYY-MM-DD)
        cutoff = (date.today() - timedelta(days=21)).isoformat()

        # ── DB 연결 ────────────────────────────────────────────────────────
        def _get_engine():
            raw = os.environ["SERVICE_DATABASE_URL"]
            ca = str(PROJECT_ROOT / "config" / "certs" / "ca.pem")
            if "ssl_ca=" in raw:
                url = raw.split("?")[0] + "?charset=utf8mb4"
                args = {"ssl": {"ca": ca}}
            else:
                url, args = raw, {}
            return create_engine(url, connect_args=args, pool_pre_ping=True)

        engine = _get_engine()

        # ── MLflow Gateway LLM 호출 ────────────────────────────────────────
        gateway_uri = os.environ.get("MLFLOW_GATEWAY_URL", "http://52.78.237.104:5001/gateway/mlflow/v1")
        gw_user = os.environ.get("MLFLOW_TRACKING_USERNAME", "")
        gw_pass = os.environ.get("MLFLOW_TRACKING_PASSWORD", "")

        def _call_llm(prompt: str) -> str:
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
            raise RuntimeError(f"예상치 못한 LLM 응답 형식: {result}")

        # ── 티커별 처리 ────────────────────────────────────────────────────
        failed: list[str] = []

        for ticker, info in TICKER_FACTORS.items():
            ticker_name = info["name"]
            factors = info["factors"]
            n = len(factors)

            try:
                # 멱등 체크: 오늘치가 이미 있으면 스킵
                with engine.connect() as conn:
                    exists = conn.execute(
                        text("SELECT 1 FROM factor_insight WHERE ticker=:t AND date=:d LIMIT 1"),
                        {"t": ticker, "d": today_str},
                    ).fetchone()
                if exists:
                    log.info("[%s] 이미 존재, 스킵 (date=%s)", ticker, today_str)
                    continue

                # regime 조회 후 S3 summary에서 cause 로드
                with engine.connect() as conn:
                    rows = conn.execute(
                        text(
                            "SELECT start_date, end_date, direction, cum_return "
                            "FROM regime "
                            "WHERE ticker = :t AND end_date >= :cutoff "
                            "ORDER BY end_date DESC LIMIT 6"
                        ),
                        {"t": ticker, "cutoff": cutoff},
                    ).fetchall()

                import boto3
                s3_bucket = os.environ.get("AWS_S3_BUCKET", "fisa-news-archive")
                s3 = boto3.client("s3", region_name="ap-northeast-2")
                news_lines = []
                for r in rows:
                    key = f"summary/{ticker}/{r.start_date}_{r.end_date}.json"
                    try:
                        resp = s3.get_object(Bucket=s3_bucket, Key=key)
                        payload = json.loads(resp["Body"].read().decode("utf-8"))
                        cause = (payload.get("llm_analysis") or {}).get("cause", "")
                    except Exception:
                        cause = ""
                    if cause:
                        news_lines.append(
                            f"- {r.direction or ''} {(r.cum_return or 0):.1f}%: {cause}"
                        )
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

                raw_response = _call_llm(prompt)
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

                with engine.begin() as conn:
                    conn.execute(
                        text("""
                            INSERT INTO factor_insight
                                (ticker, date, labels, directions, strengths, descs, advice, created_at)
                            VALUES (:ticker, :date, :labels, :directions, :strengths, :descs, :advice, NOW())
                            ON DUPLICATE KEY UPDATE
                                labels=VALUES(labels),
                                directions=VALUES(directions),
                                strengths=VALUES(strengths),
                                descs=VALUES(descs),
                                advice=VALUES(advice)
                        """),
                        {
                            "ticker": ticker,
                            "date": today_str,
                            "labels": json.dumps(labels, ensure_ascii=False),
                            "directions": json.dumps(directions[:n], ensure_ascii=False),
                            "strengths": json.dumps(strengths[:n], ensure_ascii=False),
                            "descs": json.dumps(descs, ensure_ascii=False),
                            "advice": json.dumps(advice, ensure_ascii=False),
                        },
                    )

                log.info("[%s] %s 완료", ticker, ticker_name)

            except Exception as exc:
                log.error("[%s] %s 실패: %s", ticker, ticker_name, exc, exc_info=True)
                failed.append(ticker)

        if failed:
            raise RuntimeError(f"실패한 티커: {failed} — Airflow가 재시도하면 성공한 티커는 스킵됩니다.")

    insights = run_factor_insights()
    wait_for_regime_summary >> insights


finance_factor_insights_daily()

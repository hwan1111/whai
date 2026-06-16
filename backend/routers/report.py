import json
import logging
import os
import re
from datetime import date, timedelta

import boto3
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.db import get_db
from backend.routers.auth import _get_user_id
from src.llm_utils import portfolio_analyzer
from src.llm_utils.gateway_client import GatewayClient

_S3_BUCKET = os.getenv("AWS_S3_BUCKET", "fisa-news-archive")
_S3_REGION = "ap-northeast-2"


def _fetch_cause_from_s3(s3_client, ticker: str, start_date: str, end_date: str) -> str:
    """summary/{ticker}/{start}_{end}.json 에서 cause 추출."""
    key = f"summary/{ticker}/{start_date}_{end_date}.json"
    try:
        resp = s3_client.get_object(Bucket=_S3_BUCKET, Key=key)
        payload = json.loads(resp["Body"].read().decode("utf-8"))
        return (payload.get("llm_analysis") or {}).get("cause", "")
    except Exception:
        return ""

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/report", tags=["report"])

MAX_SNAPSHOTS = 10


class SnapshotBody(BaseModel):
    id: str
    datetime: str
    holdings: list[dict]


@router.get("/snapshots")
def get_snapshots(
    user_id: str = Depends(_get_user_id),
    db: Session = Depends(get_db),
) -> dict:
    rows = db.execute(
        text(
            "SELECT id, content, ai_analysis FROM user_portfolio "
            "WHERE user_id = :uid ORDER BY created_at DESC LIMIT :lim"
        ),
        {"uid": user_id, "lim": MAX_SNAPSHOTS},
    ).fetchall()
    snapshots = []
    for row in rows:
        try:
            data = json.loads(row.content)
            data["id"] = row.id
            # 레거시 스냅샷은 ai_analysis 가 NULL → 프론트가 rule-based fallback 사용
            data["ai_analysis"] = json.loads(row.ai_analysis) if row.ai_analysis else None
            snapshots.append(data)
        except Exception:
            pass
    return {"snapshots": snapshots}


@router.post("/snapshots")
def add_snapshot(
    body: SnapshotBody,
    user_id: str = Depends(_get_user_id),
    db: Session = Depends(get_db),
) -> dict:
    count = db.execute(
        text("SELECT COUNT(*) FROM user_portfolio WHERE user_id = :uid"),
        {"uid": user_id},
    ).scalar()
    if count >= MAX_SNAPSHOTS:
        db.execute(
            text("DELETE FROM user_portfolio WHERE user_id = :uid ORDER BY created_at ASC LIMIT 1"),
            {"uid": user_id},
        )
    content = json.dumps({"datetime": body.datetime, "holdings": body.holdings}, ensure_ascii=False)

    # LLM 종합 분석 — 실패하더라도 스냅샷 저장은 성공해야 하므로 전체를 try/except 로 감싼다.
    ai_analysis_json = None
    try:
        analysis = portfolio_analyzer.analyze_portfolio(user_id, body.holdings, db)
        if analysis is not None:
            ai_analysis_json = json.dumps(analysis, ensure_ascii=False)
    except Exception as e:  # noqa: BLE001
        logger.error("AI 포트폴리오 분석 실패 (스냅샷은 그대로 저장): %s", e)

    db.execute(
        text(
            "INSERT INTO user_portfolio (id, user_id, content, ai_analysis, created_at) "
            "VALUES (:id, :uid, :content, :ai, NOW())"
        ),
        {"id": body.id, "uid": user_id, "content": content, "ai": ai_analysis_json},
    )
    db.commit()
    return {"ok": True}


class FactorInsightBody(BaseModel):
    ticker: str
    ticker_name: str
    factors: list[dict]


@router.post("/factor-insights")
def get_factor_insights(
    body: FactorInsightBody,
    user_id: str = Depends(_get_user_id),
    db: Session = Depends(get_db),
) -> dict:
    today_str = date.today().isoformat()

    # DAG가 미리 생성한 캐시 조회 (오늘치가 있으면 LLM 호출 없이 즉시 반환)
    cached = db.execute(
        text(
            "SELECT labels, directions, strengths, descs, advice "
            "FROM factor_insight "
            "WHERE ticker = :ticker AND date = :date"
        ),
        {"ticker": body.ticker, "date": today_str},
    ).fetchone()
    if cached:
        return {
            "labels": json.loads(cached.labels),
            "directions": json.loads(cached.directions),
            "strengths": json.loads(cached.strengths),
            "descs": json.loads(cached.descs),
            "advice": json.loads(cached.advice),
        }

    # 캐시 미스 — 실시간 LLM 호출 (DAG 실패 / 장중 첫 요청 시 폴백)
    cutoff = (date.today() - timedelta(days=21)).isoformat()
    rows = db.execute(
        text(
            "SELECT start_date, end_date, direction, cum_return "
            "FROM regime "
            "WHERE ticker = :ticker AND end_date >= :cutoff "
            "ORDER BY end_date DESC LIMIT 6"
        ),
        {"ticker": body.ticker, "cutoff": cutoff},
    ).fetchall()

    # S3 summary/{ticker}/{start}_{end}.json 에서 cause 로드
    news_lines: list[str] = []
    try:
        s3 = boto3.client("s3", region_name=_S3_REGION)
        for r in rows:
            cause = _fetch_cause_from_s3(
                s3, body.ticker, str(r.start_date), str(r.end_date)
            )
            if cause:
                news_lines.append(
                    f"- {r.direction or ''} {(r.cum_return or 0):.1f}%: {cause}"
                )
    except Exception as e:
        logger.warning("S3 뉴스 로드 실패 (컨텍스트 없이 진행): %s", e)
    news_context = "\n".join(news_lines) if news_lines else "(최근 뉴스 없음)"
    factors_text = "\n".join(f"{i+1}. {f['label']}" for i, f in enumerate(body.factors))
    n = len(body.factors)
    prompt = (
        f"금융 자산 '{body.ticker_name}({body.ticker})'의 최근 뉴스 분석:\n"
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
    try:
        client = GatewayClient(endpoint="low_performance_llm", validate_connection=False)
        raw = client.call(text=prompt, temperature=0.2, max_tokens=700)
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not match:
            raise ValueError("no JSON")
        parsed = json.loads(match.group())
        descs = parsed.get("descs", [])
        labels = parsed.get("labels", [])
        directions = parsed.get("directions", [])
        strengths = parsed.get("strengths", [])
        advice = parsed.get("advice", "")
        if len(descs) < n:
            raise ValueError("incomplete descs")
        if len(directions) < n or any(direction not in {"상승", "하락", "중립"} for direction in directions[:n]):
            raise ValueError("incomplete directions")
        if len(strengths) < n or any(strength not in {"강함", "보통", "약함"} for strength in strengths[:n]):
            raise ValueError("incomplete strengths")
        if not isinstance(advice, list) or len(advice) < 3:
            raise ValueError("incomplete advice")
    except Exception as e:
        logger.error("factor-insights LLM 실패: %s", e)
        raise HTTPException(status_code=502, detail="LLM 호출 실패")

    # 실시간 결과를 DB에 저장 → 같은 날 다른 사용자나 재요청은 캐시 히트
    try:
        db.execute(
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
                "ticker": body.ticker,
                "date": today_str,
                "labels": json.dumps(labels, ensure_ascii=False),
                "directions": json.dumps(directions[:n], ensure_ascii=False),
                "strengths": json.dumps(strengths[:n], ensure_ascii=False),
                "descs": json.dumps(descs, ensure_ascii=False),
                "advice": json.dumps(advice, ensure_ascii=False),
            },
        )
        db.commit()
    except Exception as e:
        logger.warning("factor_insight DB 저장 실패 (응답은 정상 반환): %s", e)

    return {
        "labels": labels,
        "directions": directions[:n],
        "strengths": strengths[:n],
        "descs": descs,
        "advice": advice,
    }


class CorrPair(BaseModel):
    key: str  # "{asset_a}|{asset_b}"
    asset_a_name: str
    asset_b_name: str
    correlation: float


class CorrInsightsBatchBody(BaseModel):
    pairs: list[CorrPair]


@router.post("/correlation-insights")
def get_correlation_insights(
    body: CorrInsightsBatchBody,
    user_id: str = Depends(_get_user_id),
) -> dict:
    if not body.pairs:
        return {"descriptions": {}}

    pairs_text = "\n".join(
        f"{i+1}. {p.asset_a_name} · {p.asset_b_name}  r={p.correlation:+.2f}"
        for i, p in enumerate(body.pairs)
    )
    prompt = (
        f"아래 {len(body.pairs)}개 금융 자산 쌍의 상관관계를 각각 한국어 1문장으로 설명하세요.\n\n"
        f"{pairs_text}\n\n"
        f"규칙:\n"
        f"- 각 1문장(30자 이내), 왜 이런 상관관계가 나타나는지 금융·경제적 원인\n"
        f"- 종목명을 직접 사용, 학술 용어 없이 투자자 관점\n"
        f"- 번호 순서대로 JSON 배열만 반환\n"
        f'형식: {{"descs":["설명1","설명2",...]}}'
    )
    try:
        client = GatewayClient(endpoint="low_performance_llm", validate_connection=False)
        raw = client.call(text=prompt, temperature=0.3, max_tokens=600)
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        descs = json.loads(match.group()).get("descs", []) if match else []
    except Exception as e:
        logger.error("상관관계 배치 LLM 실패: %s", e)
        raise HTTPException(status_code=502, detail="LLM 호출 실패")

    return {"descriptions": {p.key: descs[i] for i, p in enumerate(body.pairs) if i < len(descs)}}


_VALID_PERIODS = {"1W", "1M", "3M", "6M", "1Y", "3Y", "ALL"}


@router.get("/correlation")
def get_stored_correlations(
    period: str = Query(default="1M"),
    user_id: str = Depends(_get_user_id),
    db: Session = Depends(get_db),
) -> dict:
    if period not in _VALID_PERIODS:
        raise HTTPException(status_code=400, detail=f"유효하지 않은 period: {period}")

    latest_date = db.execute(
        text("SELECT MAX(computed_date) FROM correlation WHERE period = :p"),
        {"p": period},
    ).scalar()
    if not latest_date:
        raise HTTPException(status_code=404, detail="해당 기간의 상관계수 데이터가 없습니다.")

    rows = db.execute(
        text("""
            SELECT ticker_a, ticker_b, correlation_coeff
            FROM correlation
            WHERE period = :p AND computed_date = :d
            ORDER BY ABS(correlation_coeff) DESC
        """),
        {"p": period, "d": latest_date},
    ).fetchall()

    return {
        "period": period,
        "computed_date": str(latest_date),
        "pairs": [
            {"a": r.ticker_a, "b": r.ticker_b, "v": r.correlation_coeff}
            for r in rows
        ],
    }


@router.delete("/snapshots/{snap_id}")
def delete_snapshot(
    snap_id: str,
    user_id: str = Depends(_get_user_id),
    db: Session = Depends(get_db),
) -> dict:
    db.execute(
        text("DELETE FROM user_portfolio WHERE id = :id AND user_id = :uid"),
        {"id": snap_id, "uid": user_id},
    )
    db.commit()
    return {"ok": True}

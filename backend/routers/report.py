import json
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.db import get_db
from backend.routers.auth import _get_user_id
from src.llm_utils import portfolio_analyzer

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

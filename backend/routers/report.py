import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.db import get_db
from backend.routers.auth import _get_user_id

router = APIRouter(prefix="/report", tags=["report"])


class SnapshotsBody(BaseModel):
    snapshots: list[dict]


@router.get("/snapshots")
def get_snapshots(
    user_id: str = Depends(_get_user_id),
    db: Session = Depends(get_db),
) -> dict:
    row = db.execute(
        text("SELECT content FROM user_report WHERE user_id = :uid LIMIT 1"),
        {"uid": user_id},
    ).fetchone()
    if not row or not row.content:
        return {"snapshots": []}
    try:
        return {"snapshots": json.loads(row.content)}
    except Exception:
        return {"snapshots": []}


@router.put("/snapshots")
def put_snapshots(
    body: SnapshotsBody,
    user_id: str = Depends(_get_user_id),
    db: Session = Depends(get_db),
) -> dict:
    content_json = json.dumps(body.snapshots, ensure_ascii=False)
    existing = db.execute(
        text("SELECT id FROM user_report WHERE user_id = :uid LIMIT 1"),
        {"uid": user_id},
    ).fetchone()

    if existing:
        db.execute(
            text("UPDATE user_report SET content = :content, updated_at = NOW() WHERE user_id = :uid"),
            {"content": content_json, "uid": user_id},
        )
    else:
        db.execute(
            text("""
                INSERT INTO user_report (id, user_id, title, content, created_at, updated_at)
                VALUES (:id, :uid, '마이 리포트', :content, NOW(), NOW())
            """),
            {"id": str(uuid.uuid4()), "uid": user_id, "content": content_json},
        )
    db.commit()
    return {"ok": True}

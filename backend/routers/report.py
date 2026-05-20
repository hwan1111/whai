import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.db import get_db
from backend.routers.auth import _get_user_id

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
        text("SELECT id, content FROM user_report WHERE user_id = :uid ORDER BY created_at DESC LIMIT :lim"),
        {"uid": user_id, "lim": MAX_SNAPSHOTS},
    ).fetchall()
    snapshots = []
    for row in rows:
        try:
            data = json.loads(row.content)
            data["id"] = row.id
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
        text("SELECT COUNT(*) FROM user_report WHERE user_id = :uid"),
        {"uid": user_id},
    ).scalar()
    if count >= MAX_SNAPSHOTS:
        db.execute(
            text("DELETE FROM user_report WHERE user_id = :uid ORDER BY created_at ASC LIMIT 1"),
            {"uid": user_id},
        )
    content = json.dumps({"datetime": body.datetime, "holdings": body.holdings}, ensure_ascii=False)
    db.execute(
        text("INSERT INTO user_report (id, user_id, title, content, created_at) VALUES (:id, :uid, '', :content, NOW())"),
        {"id": body.id, "uid": user_id, "content": content},
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
        text("DELETE FROM user_report WHERE id = :id AND user_id = :uid"),
        {"id": snap_id, "uid": user_id},
    )
    db.commit()
    return {"ok": True}

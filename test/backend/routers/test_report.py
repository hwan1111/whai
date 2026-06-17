"""backend/routers/report.py 단위 테스트

DB 세션과 LLM 분석기는 mock 처리한다. SQLAlchemy 엔진이 import 시점에
생성되므로, backend 모듈 import 전에 SERVICE_DATABASE_URL 을 sqlite 로 설정한다.
"""

import json
import os
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("SERVICE_DATABASE_URL", "sqlite://")

from backend.routers import report  # noqa: E402


def _exec_result(scalar=None, fetchall=None):
    res = MagicMock()
    res.scalar.return_value = scalar
    res.fetchall.return_value = fetchall or []
    return res


# ── add_snapshot ─────────────────────────────────────────────────────


def test_add_snapshot_stores_ai_analysis_when_available(monkeypatch):
    analysis = {"overall_summary": "요약", "confidence": 0.9}
    monkeypatch.setattr(
        report.portfolio_analyzer, "analyze_portfolio", MagicMock(return_value=analysis)
    )

    db = MagicMock()
    db.execute.return_value = _exec_result(scalar=0)  # 현재 스냅샷 0개

    body = report.SnapshotBody(
        id="snap_1", datetime="2026-06-14T00:00:00Z",
        holdings=[{"id": "005930", "qty": 10, "avgPrice": 100, "snapshotPrice": 150}],
    )
    out = report.add_snapshot(body, user_id="user1", db=db)

    assert out == {"ok": True}
    # INSERT 먼저 커밋 후 UPDATE로 ai_analysis 업데이트 → commit 2회
    assert db.commit.call_count == 2
    # 마지막 execute 호출(UPDATE)의 ai 파라미터에 직렬화된 분석이 담겨야 한다
    update_params = db.execute.call_args.args[1]
    assert json.loads(update_params["ai"]) == analysis


def test_add_snapshot_stores_null_when_analysis_returns_none(monkeypatch):
    monkeypatch.setattr(
        report.portfolio_analyzer, "analyze_portfolio", MagicMock(return_value=None)
    )

    db = MagicMock()
    db.execute.return_value = _exec_result(scalar=0)

    body = report.SnapshotBody(
        id="snap_2", datetime="2026-06-14T00:00:00Z",
        holdings=[{"id": "005930", "qty": 1, "avgPrice": 100}],
    )
    out = report.add_snapshot(body, user_id="user1", db=db)

    assert out == {"ok": True}
    # 분석 없으면 UPDATE 없이 INSERT 커밋 1회, INSERT 파라미터에 ai 키 없음
    db.commit.assert_called_once()
    insert_params = db.execute.call_args.args[1]
    assert "ai" not in insert_params


def test_add_snapshot_succeeds_even_if_analyzer_raises(monkeypatch):
    monkeypatch.setattr(
        report.portfolio_analyzer, "analyze_portfolio",
        MagicMock(side_effect=RuntimeError("boom")),
    )

    db = MagicMock()
    db.execute.return_value = _exec_result(scalar=0)

    body = report.SnapshotBody(
        id="snap_3", datetime="2026-06-14T00:00:00Z",
        holdings=[{"id": "005930", "qty": 1, "avgPrice": 100}],
    )
    out = report.add_snapshot(body, user_id="user1", db=db)

    # 분석 실패해도 스냅샷 저장은 성공, commit 1회 + rollback 1회
    assert out == {"ok": True}
    db.commit.assert_called_once()
    db.rollback.assert_called_once()


# ── get_snapshots ────────────────────────────────────────────────────


def test_get_snapshots_parses_ai_analysis_json():
    analysis = {"overall_summary": "요약", "confidence": 0.7}
    row_new = MagicMock()
    row_new.id = "snap_new"
    row_new.content = json.dumps({"datetime": "2026-06-14T00:00:00Z", "holdings": []})
    row_new.ai_analysis = json.dumps(analysis)

    row_legacy = MagicMock()
    row_legacy.id = "snap_legacy"
    row_legacy.content = json.dumps({"datetime": "2026-01-01T00:00:00Z", "holdings": []})
    row_legacy.ai_analysis = None

    db = MagicMock()
    db.execute.return_value = _exec_result(fetchall=[row_new, row_legacy])

    out = report.get_snapshots(user_id="user1", db=db)

    snaps = {s["id"]: s for s in out["snapshots"]}
    assert snaps["snap_new"]["ai_analysis"] == analysis
    assert snaps["snap_legacy"]["ai_analysis"] is None  # 레거시 → fallback 대상

"""HTTP 层测试：版本冲突必须返回 409，且与缺字段的参数校验错误（422）可区分。"""

import hashlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import router
from app.auth import get_current_user, require_researcher
from app.database import Base, get_db
from fastapi import FastAPI


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, compiler, **kw):
    return "JSON"


RESEARCHER = {"username": "researcher", "role": "researcher"}


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    def _get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = lambda: RESEARCHER
    app.dependency_overrides[require_researcher] = lambda: RESEARCHER
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _create_run(client: TestClient) -> str:
    resp = client.post(
        "/api/runs",
        json={
            "project": "p1",
            "name": "n1",
            "dataset_content_sha256": sha("ds"),
            "code_commit_sha": "abc1234",
            "description": None,
            "expected_version": 0,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_stale_version_returns_409_not_validation_error(client):
    run_id = _create_run(client)

    # 当前 version=1，刻意提交过期的 expected_version=999
    resp = client.post(
        f"/api/runs/{run_id}/metrics",
        json={"name": "loss", "value": 1.0, "step": 1, "expected_version": 999},
    )

    # 冲突必须是独立状态码 409，不能是参数错误码 400/422
    assert resp.status_code == 409
    assert resp.status_code != 400
    assert resp.status_code != 422
    detail = resp.json()["detail"]
    assert "参数不合法" not in detail
    assert "expected_version" in detail or "版本冲突" in detail or "乐观锁" in detail


def test_terminal_state_returns_409(client):
    run_id = _create_run(client)
    ok = client.post(
        f"/api/runs/{run_id}/complete",
        json={"result_summary": "done", "expected_version": 1},
    )
    assert ok.status_code == 200, ok.text

    # 已终态再发命令 → 409 冲突
    resp = client.post(
        f"/api/runs/{run_id}/complete",
        json={"result_summary": "again", "expected_version": 2},
    )
    assert resp.status_code == 409
    assert resp.status_code != 400


def test_missing_field_returns_validation_status_not_conflict(client):
    run_id = _create_run(client)

    # 缺 name 字段 → FastAPI 参数校验失败（422），与 409 冲突明确区分
    resp = client.post(
        f"/api/runs/{run_id}/metrics",
        json={"value": 1.0, "step": 1, "expected_version": 1},
    )
    assert resp.status_code == 422
    assert resp.status_code != 409

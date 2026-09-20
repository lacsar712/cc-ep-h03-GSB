"""API 级测试：版本冲突必须返回独立的 409，与缺字段的参数校验错误（422）可区分。"""

from __future__ import annotations

import hashlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import database
from app.database import Base
from app.main import app
import app.main as main_mod


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @compiles(JSONB, "sqlite")
    def _compile_jsonb_sqlite(_type, compiler, **kw):
        return "JSON"

    Base.metadata.create_all(bind=engine)
    testing_session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    # lifespan 启动时会用 app.main.engine 建表，将其也指向内存 SQLite
    main_mod.engine = engine

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[database.get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def token(client):
    resp = client.post(
        "/api/auth/login",
        json={"username": "researcher", "password": "lab123456"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture()
def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def valid_start_body(name: str = "n1") -> dict:
    return {
        "project": "p1",
        "name": name,
        "dataset_content_sha256": sha("ds"),
        "code_commit_sha": "abc1234",
        "description": None,
        "expected_version": 0,
    }


def test_stale_version_returns_409_not_validation_error(client, auth_headers):
    # 启动 run，当前 version=1
    run_id = client.post("/api/runs", json=valid_start_body(), headers=auth_headers).json()["id"]

    # 先成功推进到 version=2
    ok = client.post(
        f"/api/runs/{run_id}/metrics",
        json={"name": "loss", "value": 0.5, "step": 1, "expected_version": 1},
        headers=auth_headers,
    )
    assert ok.status_code == 200

    # 刻意提交过期版本 expected_version=1（当前已为 2）
    conflict = client.post(
        f"/api/runs/{run_id}/metrics",
        json={"name": "loss", "value": 0.7, "step": 2, "expected_version": 1},
        headers=auth_headers,
    )
    assert conflict.status_code == 409
    # 冲突码绝不能是参数错误码
    assert conflict.status_code != 400
    assert conflict.status_code != 422
    detail = conflict.json()["detail"]
    assert "版本冲突" in detail or "乐观锁" in detail
    assert "参数不合法" not in detail
    assert "请求参数不合法" not in detail


def test_missing_field_returns_validation_error_distinct_from_conflict(client, auth_headers):
    run_id = client.post("/api/runs", json=valid_start_body(), headers=auth_headers).json()["id"]

    # 缺少必填字段 name —— 这才是参数校验失败
    validation = client.post(
        f"/api/runs/{run_id}/metrics",
        json={"value": 0.5, "step": 1, "expected_version": 1},
        headers=auth_headers,
    )
    assert validation.status_code == 422

    # 先合法推进到 version=2，再提交过期版本 1 制造真实冲突
    client.post(
        f"/api/runs/{run_id}/metrics",
        json={"name": "loss", "value": 0.5, "step": 1, "expected_version": 1},
        headers=auth_headers,
    )
    conflict = client.post(
        f"/api/runs/{run_id}/metrics",
        json={"name": "loss", "value": 0.9, "step": 3, "expected_version": 1},
        headers=auth_headers,
    )
    # 两种错误在 HTTP 状态码层面必须可区分
    assert conflict.status_code == 409
    assert conflict.status_code != validation.status_code


def test_stale_start_version_returns_409(client, auth_headers):
    body = valid_start_body(name="n2")
    body["expected_version"] = 99  # 非 0 的起始版本属于版本冲突，而非请求体格式错误
    resp = client.post("/api/runs", json=body, headers=auth_headers)
    assert resp.status_code == 409
    assert resp.status_code != 422
    assert resp.status_code != 400

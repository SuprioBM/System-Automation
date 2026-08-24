"""Spec §19 F (duplicate Resume can't create two executions) and part of E
(worker-restart orphan recovery). F uses the real Redis claim lock (Redis
Cloud, already configured for this project) rather than mocking it, since
that's the actual mechanism providing the guarantee."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core import config as config_module
from app.core.redis_client import release_claim
from app.routes.discord_router import router as discord_router
from app.services import registry_service


@pytest.fixture
def app():
    from fastapi import FastAPI
    a = FastAPI()
    a.include_router(discord_router)
    return a


@pytest.fixture(autouse=True)
def secret(monkeypatch):
    monkeypatch.setattr(config_module.settings, "DISCORD_CALLBACK_SHARED_SECRET", "test-secret")


HEADERS = {"X-DevSync-Secret": "test-secret"}


def test_resume_rejects_workflow_not_in_recoverable_state(app, monkeypatch):
    monkeypatch.setattr(registry_service, "get_workflow_run",
                         lambda wf_id: {"workflow_id": wf_id, "status": "completed", "recoverable": False})
    client = TestClient(app)
    res = client.post("/discord/workflow-action", json={
        "workflow_id": "wf-1", "action": "resume", "discord_user_id": "123",
    }, headers=HEADERS)
    assert res.status_code == 409


def test_resume_rejects_unknown_workflow(app, monkeypatch):
    monkeypatch.setattr(registry_service, "get_workflow_run", lambda wf_id: None)
    client = TestClient(app)
    res = client.post("/discord/workflow-action", json={
        "workflow_id": "wf-missing", "action": "resume", "discord_user_id": "123",
    }, headers=HEADERS)
    assert res.status_code == 404


def test_f_duplicate_resume_click_only_starts_one_execution(app, monkeypatch):
    """Two rapid Resume clicks on the same failed/recoverable workflow: the
    second must be rejected by the real Redis claim, not silently accepted."""
    workflow_id = f"wf-duptest-{uuid.uuid4()}"
    monkeypatch.setattr(registry_service, "get_workflow_run",
                         lambda wf_id: {"workflow_id": wf_id, "status": "failed", "recoverable": True,
                                        "failed_node": "analyze_repository"})
    monkeypatch.setattr(registry_service, "mark_workflow_resuming", lambda wf_id: None)

    enqueued = []
    monkeypatch.setattr("app.routes.discord_router.enqueue_recovery", lambda wf_id: enqueued.append(wf_id))

    claim_key = f"devsync:resume_claim:{workflow_id}"
    release_claim(claim_key)  # ensure a clean slate for this test's key
    client = TestClient(app)
    try:
        first = client.post("/discord/workflow-action", json={
            "workflow_id": workflow_id, "action": "resume", "discord_user_id": "123",
        }, headers=HEADERS)
        second = client.post("/discord/workflow-action", json={
            "workflow_id": workflow_id, "action": "resume", "discord_user_id": "123",
        }, headers=HEADERS)

        assert first.status_code == 200
        assert second.status_code == 409
        assert enqueued == [workflow_id]  # only enqueued once, not twice
    finally:
        release_claim(claim_key)


def test_cancel_marks_workflow_cancelled(app, monkeypatch):
    monkeypatch.setattr(registry_service, "get_workflow_run",
                         lambda wf_id: {"workflow_id": wf_id, "status": "failed", "recoverable": True})
    cancelled = []
    monkeypatch.setattr(registry_service, "mark_workflow_cancelled", lambda wf_id: cancelled.append(wf_id))
    client = TestClient(app)
    res = client.post("/discord/workflow-action", json={
        "workflow_id": "wf-cancel-me", "action": "cancel", "discord_user_id": "123",
    }, headers=HEADERS)
    assert res.status_code == 200
    assert cancelled == ["wf-cancel-me"]


def test_cancelled_workflow_cannot_then_be_resumed(app, monkeypatch):
    """Spec §10: a cancelled workflow must never be accidentally resumable."""
    monkeypatch.setattr(registry_service, "get_workflow_run",
                         lambda wf_id: {"workflow_id": wf_id, "status": "cancelled", "recoverable": False})
    client = TestClient(app)
    res = client.post("/discord/workflow-action", json={
        "workflow_id": "wf-was-cancelled", "action": "resume", "discord_user_id": "123",
    }, headers=HEADERS)
    assert res.status_code == 409


def test_wrong_secret_rejected(app):
    client = TestClient(app)
    res = client.post("/discord/workflow-action", json={
        "workflow_id": "wf-1", "action": "resume", "discord_user_id": "123",
    }, headers={"X-DevSync-Secret": "wrong"})
    assert res.status_code == 401


# ── E: worker-restart orphan recovery (the decision logic; the RQ/Postgres
#    parts are exercised live in test_failure_recovery.py and this session's
#    manual testing, not re-simulated with a real worker process here) ────

def test_e_orphaned_running_workflow_gets_reenqueued(monkeypatch):
    from app.workers import worker as worker_module

    monkeypatch.setattr(
        "app.core.supabase.get_supabase",
        lambda: type("S", (), {"table": lambda self, name: _FakeTable([{"workflow_id": "wf-orphan"}])})(),
    )
    reenqueued = []
    monkeypatch.setattr("app.workers.queue.enqueue_recovery", lambda wf_id: reenqueued.append(wf_id))

    claim_key = "devsync:resume_claim:wf-orphan"
    release_claim(claim_key)
    try:
        worker_module._recover_orphaned_workflows()
        assert reenqueued == ["wf-orphan"]
    finally:
        release_claim(claim_key)


def test_e_orphan_scan_skips_a_workflow_another_worker_already_claimed(monkeypatch):
    from app.workers import worker as worker_module

    monkeypatch.setattr(
        "app.core.supabase.get_supabase",
        lambda: type("S", (), {"table": lambda self, name: _FakeTable([{"workflow_id": "wf-owned"}])})(),
    )
    reenqueued = []
    monkeypatch.setattr("app.workers.queue.enqueue_recovery", lambda wf_id: reenqueued.append(wf_id))

    claim_key = "devsync:resume_claim:wf-owned"
    from app.core.redis_client import acquire_claim
    assert acquire_claim(claim_key, ttl_seconds=30)  # simulate another worker already owning it
    try:
        worker_module._recover_orphaned_workflows()
        assert reenqueued == []  # must not double-enqueue
    finally:
        release_claim(claim_key)


class _FakeTable:
    def __init__(self, rows):
        self._rows = rows

    def select(self, *_):
        return self

    def eq(self, *_):
        return self

    def execute(self):
        return type("R", (), {"data": self._rows})()

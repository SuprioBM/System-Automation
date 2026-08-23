import pytest

from app.core.errors import StaleApprovalError
from app.services import registry_service


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, table, rows, filters=None, update_payload=None):
        self.table, self.rows, self.filters = table, rows, filters or {}
        self.update_payload = update_payload

    def select(self, *_):
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def update(self, payload):
        self.update_payload = payload
        return self

    def execute(self):
        if self.update_payload is not None:
            for row in self.rows:
                if all(row.get(k) == v for k, v in self.filters.items()):
                    row.update(self.update_payload)
            return _Result(self.rows)
        matched = [r for r in self.rows if all(r.get(k) == v for k, v in self.filters.items())]
        return _Result(matched)


class FakeSupabase:
    def __init__(self, tables: dict):
        self.tables = tables

    def table(self, name):
        return _Query(name, self.tables[name])


@pytest.fixture
def fake_db(monkeypatch):
    tables = {
        "approvals": [{"id": "appr-1", "workflow_id": "wf-1", "artifact_id": "art-1", "artifact_version": 1,
                        "status": "pending"}],
        "artifacts": [{"id": "art-1", "workflow_id": "wf-1", "version": 1, "status": "draft"}],
    }
    fake = FakeSupabase(tables)
    monkeypatch.setattr(registry_service, "get_supabase", lambda: fake)
    return tables


def test_decide_approval_succeeds_for_current_version(fake_db):
    result = registry_service.decide_approval("appr-1", "approved")
    assert result["status"] == "approved"


def test_decide_approval_rejects_stale_artifact_version(fake_db):
    fake_db["artifacts"][0]["version"] = 2  # a newer draft superseded the one this approval targeted
    with pytest.raises(StaleApprovalError):
        registry_service.decide_approval("appr-1", "approved")


def test_decide_approval_rejects_already_decided_artifact(fake_db):
    fake_db["artifacts"][0]["status"] = "approved"  # already resolved by a prior decision
    with pytest.raises(StaleApprovalError):
        registry_service.decide_approval("appr-1", "approved")

import uuid
from types import SimpleNamespace

import pytest

from app.api.v1 import sync as sync_module
from app.schemas.health import SyncChange, SyncPushRequest, SyncPushResult, SyncTombstone


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one(self):
        return self._value

    def scalar_one_or_none(self):
        return self._value


class _FakeStatusDb:
    def __init__(self):
        self._results = [
            _ScalarResult(3),  # entries_count
            _ScalarResult(2),  # meds_count
            _ScalarResult(None),  # latest_ts
        ]

    async def execute(self, _stmt):
        return self._results.pop(0)


class _FakePushDb:
    def __init__(self):
        self.flush_called = False

    async def flush(self):
        self.flush_called = True


@pytest.mark.asyncio
async def test_sync_push_rejects_stale_base(monkeypatch):
    async def _fake_cursor(_db, _user_id):
        return 500

    monkeypatch.setattr(sync_module, "_compute_server_cursor", _fake_cursor)

    req = SyncPushRequest(
        client_change_id="c-stale",
        base_server_version=100,
        changes=[SyncChange(entity="health_entry", op="upsert", payload={"android_id": 1})],
    )
    response = await sync_module.sync_push(
        req=req,
        current_user=SimpleNamespace(id=uuid.uuid4()),
        db=_FakePushDb(),
    )

    assert response.conflicts == 1
    assert response.applied == 0
    assert response.server_cursor == 500
    assert response.results[0].status == "conflict"


@pytest.mark.asyncio
async def test_sync_push_aggregates_apply_results(monkeypatch):
    async def _fake_cursor(_db, _user_id):
        return 100

    calls = iter([
        SyncPushResult(entity="health_entry", op="upsert", status="applied"),
        SyncPushResult(entity="medication", op="upsert", status="conflict"),
        SyncPushResult(entity="medication_course", op="upsert", status="failed"),
    ])

    async def _fake_apply(_db, _user, _change):
        return next(calls)

    monkeypatch.setattr(sync_module, "_compute_server_cursor", _fake_cursor)
    monkeypatch.setattr(sync_module, "_apply_change", _fake_apply)

    db = _FakePushDb()
    req = SyncPushRequest(
        client_change_id="c-normal",
        base_server_version=100,
        changes=[
            SyncChange(entity="health_entry", op="upsert", payload={}),
            SyncChange(entity="medication", op="upsert", payload={}),
            SyncChange(entity="medication_course", op="upsert", payload={}),
        ],
    )

    response = await sync_module.sync_push(
        req=req,
        current_user=SimpleNamespace(id=uuid.uuid4()),
        db=db,
    )

    assert db.flush_called is True
    assert response.accepted == 3
    assert response.applied == 1
    assert response.conflicts == 1
    assert [item.status for item in response.results] == ["applied", "conflict", "failed"]


@pytest.mark.asyncio
async def test_sync_status_declares_tombstone_and_conflict_capabilities(monkeypatch):
    async def _fake_cursor(_db, _user_id):
        return 999

    monkeypatch.setattr(sync_module, "_compute_server_cursor", _fake_cursor)

    response = await sync_module.sync_status(
        current_user=SimpleNamespace(id=uuid.uuid4()),
        db=_FakeStatusDb(),
    )

    assert response.server_cursor == 999
    assert "sync.tombstone.v1" in response.capabilities
    assert "sync.conflict.v1" in response.capabilities


def test_sync_tombstone_payload_roundtrip():
    tombstone = SyncTombstone(
        entity="health_entry",
        record_id=501,
        deleted_at=1773000000000,
        payload={"entry_date": "2026-03-08", "android_id": 501},
    )

    assert tombstone.payload["entry_date"] == "2026-03-08"
    assert tombstone.payload["android_id"] == 501

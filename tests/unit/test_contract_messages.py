"""C4 — 계약 버전이 다른 단계 간 알림은 처리하지 않고 운영 이벤트로 남긴다 (2.2절)"""
from __future__ import annotations

import pytest

from common.queue import MemoryQueue


class _OnlyEventsRepo:
    """운영 이벤트 기록만 허용 — 다른 저장소 호출이 있으면 처리한 것이므로 실패"""

    def __init__(self):
        self.events: list[dict] = []

    def insert_ops_events(self, rows):
        self.events.extend(rows)

    def __getattr__(self, name):
        raise AssertionError(f"계약 버전이 다른 알림인데 저장소 {name}() 호출")


def _call(consumer: str, payload: dict, repo, monkeypatch):
    q = MemoryQueue()
    if consumer == "interpolation.obs.loaded":
        import interpolation.main as m
        m.handle_obs_loaded(payload, repo, q, {})
    elif consumer == "grading.obs.loaded":
        import grading.main as m
        m.handle_obs_loaded(payload, repo, q, {})
    elif consumer == "grading.interp.done":
        import grading.main as m
        m.handle_interp_done(payload, repo, q, {})
    elif consumer == "evaluation.grade.done":
        import evaluation.main as m
        m.handle_grade_done(payload, repo, q, {})
    elif consumer == "processor.raw.fetched":
        import processor.main as m
        monkeypatch.setitem(m._CONFIG, "repo", repo)
        m.handle_raw_fetched(payload, q)
    return q


CONSUMERS = [
    ("interpolation.obs.loaded", {"topic": "obs.loaded", "source": "tide", "load_id": "x", "observed_to_utc": "2026-08-01T00:00:00"}),
    ("grading.obs.loaded", {"topic": "obs.loaded", "source": "tide", "load_id": "x"}),
    ("grading.interp.done", {"topic": "interp.done", "run_id": "r"}),
    ("evaluation.grade.done", {"topic": "grade.done", "axis": "water_temp", "farm_ids": ["f"]}),
    ("processor.raw.fetched", {"topic": "raw.fetched", "raw_id": "k", "api": "dtRecent"}),
]


@pytest.mark.parametrize("schema", [None, "queue-v0", "queue-v2"])
@pytest.mark.parametrize("consumer,payload", CONSUMERS, ids=[c for c, _ in CONSUMERS])
def test_other_contract_version_is_not_processed(consumer, payload, schema, monkeypatch):
    repo = _OnlyEventsRepo()
    msg = {**payload, **({"schema": schema} if schema else {})}
    q = _call(consumer, msg, repo, monkeypatch)
    assert [e["event_type"] for e in repo.events] == ["CONTRACT_VERSION_MISMATCH"]
    assert repo.events[0]["detail"]["schema"] == schema
    assert all(not q.drain(t) for t in ("obs.loaded", "interp.done", "grade.done", "result.updated"))

"""원문 저장소 — RAW_STORE_DSN 설정 시 로컬 디스크로 대체하지 않고 멈춘다 (계획서 11절 미결, 2026-10-02 점검 D4)"""
from __future__ import annotations

import pytest

import common.raw_store._store as store_mod


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setattr(store_mod, "_store", None)


def test_dsn_set_stops(monkeypatch, tmp_path):
    monkeypatch.setenv("RAW_STORE_DSN", "s3://placeholder")
    monkeypatch.setenv("RAW_STORE_PATH", str(tmp_path))
    with pytest.raises(SystemExit):
        store_mod.get_raw_meta("raw/x/2026/10/02/1_t.json")


def test_no_dsn_uses_local_disk(monkeypatch, tmp_path):
    monkeypatch.delenv("RAW_STORE_DSN", raising=False)
    monkeypatch.setenv("RAW_STORE_PATH", str(tmp_path))
    assert store_mod.get_raw_meta("raw/x/2026/10/02/1_t.json") is None
    assert isinstance(store_mod._store, store_mod.LocalDiskStore)

"""원문 저장소 (2.3절, 개정 22)
- RAW_STORE_DSN 없이 init_store() 미주입이면 운영 진입점은 멈춘다
- init_store(LocalDiskStore) 주입 시 DSN 없이도 로컬 디스크 사용 (테스트·flowtest 용)
- RAW_STORE_DSN 있으면 S3Store 생성 (boto3 의존)
"""
from __future__ import annotations

import pytest

import common.raw_store._store as store_mod


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setattr(store_mod, "_store", None)


def test_no_dsn_no_init_stops(monkeypatch):
    """RAW_STORE_DSN 미설정 + init_store 미주입이면 멈춘다 (2.3절, 개정 22)"""
    monkeypatch.delenv("RAW_STORE_DSN", raising=False)
    with pytest.raises(SystemExit):
        store_mod._get_store()


def test_init_store_overrides(tmp_path, monkeypatch):
    """init_store()로 주입된 구현체는 DSN 없이도 사용된다 (테스트·flowtest 용)"""
    monkeypatch.delenv("RAW_STORE_DSN", raising=False)
    store_mod.init_store(store_mod.LocalDiskStore(str(tmp_path)))
    result = store_mod.get_raw_meta("raw/x/2026/10/02/1_t.json")
    assert result is None
    assert isinstance(store_mod._store, store_mod.LocalDiskStore)


def test_init_store_put_get(tmp_path, monkeypatch):
    """LocalDiskStore 주입 후 저장·조회 동작 확인"""
    monkeypatch.delenv("RAW_STORE_DSN", raising=False)
    store_mod.init_store(store_mod.LocalDiskStore(str(tmp_path)))
    content = {"url": "u", "params": {}, "http_status": 200, "final_url": None,
               "fetched_at": "2026-10-01T00:00:00", "_fetched_ms": 1727740800000,
               "body": "test", "error": None}
    key = store_mod.save_raw("dtRecent", "DT_0016", content)
    assert store_mod.get_raw_body(key) == "test"
    meta = store_mod.get_raw_meta(key)
    assert meta is not None
    assert "body" not in meta

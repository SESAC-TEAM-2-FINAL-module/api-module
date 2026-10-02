"""
processor 진입점 — 기동 시 검사·어댑터 등록·품질 규칙 연결 (2.0.6·2.1·4.6절)
"""
import pytest
import yaml
from pathlib import Path

import processor.main as pm
from common.config import load_definitions
from common.queue import MemoryQueue

def _fake_repo():
    """DB 없는 단위 검사용 — 적재 호출은 받기만 한다 (DB 경로는 tests/db/test_processor_load.py)"""
    from contextlib import contextmanager
    from unittest.mock import MagicMock
    repo = MagicMock()
    repo.insert_raw_index.return_value = 1
    repo.get_ingest_runs_for_raw.return_value = []
    repo.get_adapter_health.return_value = []
    repo.get_unmapped_locations.return_value = []
    repo.get_publication_checks.return_value = []

    @contextmanager
    def _tx():
        yield repo
    repo.transaction.side_effect = _tx
    return repo


_OPERATIONAL = yaml.safe_load(
    (Path(__file__).parents[2] / "config" / "operational.initial.yaml").read_text(encoding="utf-8")
)


def test_load_adapters_registers_into_processor_main():
    """어댑터가 processor.main 레지스트리에 등록된다 (python -m 실행 시 레지스트리 분리 방지)"""
    pm._load_adapters()
    assert {"dtRecent", "sooList", "femoSeaList", "redtideList"} <= set(pm._REGISTRY)


def test_startup_requires_operational(monkeypatch):
    """운영 조정이 없으면 기동하지 않는다 — 기본값으로 대체하지 않는다"""
    monkeypatch.delenv("OPERATIONAL_CONFIG_PATH", raising=False)
    with pytest.raises(SystemExit):
        pm.startup(definitions=load_definitions(), repo=_fake_repo())


def test_startup_requires_database(monkeypatch):
    """DATABASE_URL이 없으면 기동하지 않는다"""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(SystemExit):
        pm.startup(definitions=load_definitions(), operational=_OPERATIONAL)


def test_startup_checks_schema():
    """기동 시 테이블 검사를 부른다 (2.0.3절)"""
    repo = _fake_repo()
    pm.startup(definitions=load_definitions(), operational=_OPERATIONAL, repo=repo)
    repo.check_schema.assert_called_once()


def test_process_before_startup_fails(monkeypatch):
    monkeypatch.setattr(pm, "_CONFIG", {})
    with pytest.raises(RuntimeError):
        pm._process_one("raw-1", "dtRecent", MemoryQueue())


def test_process_applies_quality_with_definitions(monkeypatch):
    """processor가 판정 정의를 품질 규칙에 넘긴다 — R3 범위 밖 수온이 SENSOR_QUALITY로 표시된다"""
    defs = load_definitions()
    hi = defs["quality"]["r3_water_temp_range"][1]

    class _FakeAdapter:
        api_id = "dtRecent"

        def interpret(self, pr, meta):
            return [{"station_id": "tide:DT_0001", "observed_at_utc": "2026-08-01T00:00:00",
                     "metric": "water_temp", "value": hi + 1.0, "flags": [], "missing_reason": None}]

        def normalize(self, rows):
            return rows

    captured = {}
    real_apply = pm.apply_quality

    def _spy(rows, api, *a, **kw):
        out = real_apply(rows, api, *a, **kw)
        captured["rows"] = out
        return out

    monkeypatch.setattr(pm, "_REGISTRY", {"dtRecent": _FakeAdapter()})
    monkeypatch.setattr(pm, "get_raw_body", lambda raw_id: "{}")
    monkeypatch.setattr(pm, "get_raw_meta", lambda raw_id: {"http_status": 200, "fetched_at": "2026-08-01T00:00:00"})
    monkeypatch.setattr(pm, "apply_quality", _spy)
    pm.startup(definitions=defs, operational=_OPERATIONAL, repo=_fake_repo())

    q = MemoryQueue()
    pm._process_one("raw-1", "dtRecent", q)
    assert captured["rows"][0]["quality_rule"] == "R3"
    assert "SENSOR_QUALITY" in captured["rows"][0]["flags"]


def test_obs_loaded_payload_matches_queue_contract(monkeypatch):
    """obs.loaded payload가 contracts/queue/queue-v1.json을 통과하고 source는 수집 원천이다 (2.2절)"""
    import json
    import jsonschema

    class _FakeAdapter:
        api_id = "dtRecent"

        def interpret(self, pr, meta):
            return [{"station_id": "tide:DT_0001", "observed_at_utc": "2026-08-01T00:00:00",
                     "metric": "water_temp", "value": 20.0, "flags": [], "missing_reason": None}]

        def normalize(self, rows):
            return rows

    monkeypatch.setattr(pm, "_REGISTRY", {"dtRecent": _FakeAdapter()})
    monkeypatch.setattr(pm, "get_raw_body", lambda raw_id: "{}")
    monkeypatch.setattr(pm, "get_raw_meta", lambda raw_id: {"http_status": 200, "fetched_at": "2026-08-01T00:00:00"})
    pm.startup(definitions=load_definitions(), operational=_OPERATIONAL, repo=_fake_repo())

    q = MemoryQueue()
    pm._process_one("raw-1", "dtRecent", q)
    msg = q.drain("obs.loaded")[0]
    contract = json.loads((Path(__file__).parents[2] / "contracts" / "queue" / "queue-v1.json").read_text(encoding="utf-8"))
    schema = {**contract["definitions"]["obs_loaded"], "definitions": contract["definitions"]}
    jsonschema.validate(msg.payload, schema)
    assert msg.payload["source"] == "tide"

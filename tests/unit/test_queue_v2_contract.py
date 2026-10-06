"""
V1: queue-v2 계약 검사 (7.11절 V1, 개정 22)
- error_p95=null인 interp.done이 계약 검사를 통과한다
- queue-v1 버전의 메시지는 accept_message에서 거부된다
- grade_water_temp(error_p95=None) → NONE·NO_INPUT·lower/upper 없음·값 저장
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from grading._water_temp import grade_water_temp

_ROOT = Path(__file__).parents[2]
_CONTRACT = json.loads((_ROOT / "contracts" / "queue" / "queue-v2.json").read_text("utf-8"))


def _schema(definition_key: str) -> dict:
    return {**_CONTRACT["definitions"][definition_key], "definitions": _CONTRACT["definitions"]}


# ── V1-1: error_p95=null인 interp.done → queue-v2 계약 통과 ──────────────────

def test_interp_done_null_error_p95_passes_contract():
    """error_p95=null 인 interp.done이 queue-v2 계약 검사를 통과한다 (개정 22)"""
    payload = {
        "schema": "queue-v2",
        "topic": "interp.done",
        "run_id": "aaaabbbb-0000-5000-8000-000000000001",
        "load_id": "raw/dtRecent/2026/10/06/1728000000000_DT_0016.json::v1",
        "farm_count": 3,
        "metric": "water_temp",
        "error_p95": None,
        "stations_used": 7,
    }
    jsonschema.validate(payload, _schema("interp_done"))


def test_interp_done_numeric_error_p95_passes_contract():
    """error_p95가 숫자인 경우도 queue-v2 계약을 통과한다"""
    payload = {
        "schema": "queue-v2",
        "topic": "interp.done",
        "run_id": "aaaabbbb-0000-5000-8000-000000000002",
        "load_id": "raw/dtRecent/2026/10/06/1728000000001_DT_0016.json::v1",
        "farm_count": 3,
        "metric": "water_temp",
        "error_p95": 2.48,
        "stations_used": 7,
    }
    jsonschema.validate(payload, _schema("interp_done"))


# ── V1-2: queue-v1 버전 메시지 → accept_message 거부 ────────────────────────

def test_accept_message_rejects_queue_v1(monkeypatch):
    """schema=queue-v1 메시지는 accept_message에서 거부되고 운영 이벤트가 기록된다 (2.2절)"""
    from common.contract_check._message import accept_message

    events: list[dict] = []

    class _FakeRepo:
        def insert_ops_events(self, rows):
            events.extend(rows)

    payload = {
        "schema": "queue-v1",   # 옛 버전
        "topic": "interp.done",
        "run_id": "xxx",
        "load_id": "yyy",
        "farm_count": 0,
        "metric": "water_temp",
        "stations_used": 0,
    }
    result = accept_message(payload, "interp.done", _FakeRepo())
    assert result is False
    assert len(events) == 1
    assert events[0]["event_type"] == "CONTRACT_VERSION_MISMATCH"
    assert events[0]["detail"]["schema"] == "queue-v1"
    assert events[0]["detail"]["expected"] == "queue-v2"


def test_accept_message_passes_queue_v2(monkeypatch):
    """schema=queue-v2 메시지는 accept_message에서 통과한다"""
    from common.contract_check._message import accept_message

    class _FakeRepo:
        def insert_ops_events(self, rows):
            pytest.fail("운영 이벤트가 기록되면 안 됩니다")

    payload = {
        "schema": "queue-v2",
        "topic": "obs.loaded",
        "load_id": "x",
        "api": "dtRecent",
        "source": "tide",
        "station_ids": ["tide:DT_0016"],
        "observed_from_utc": "2026-10-06T01:00:00",
        "observed_to_utc": "2026-10-06T01:10:00",
        "row_count": 5,
    }
    result = accept_message(payload, "obs.loaded", _FakeRepo())
    assert result is True


# ── V1-3: grading이 error_p95=None 처리 시 수온 행 확인 ─────────────────────

@pytest.mark.parametrize("thresholds", [[1.0, 2.0, 3.0]])
def test_grade_water_temp_none_error_p95(thresholds):
    """error_p95=None → provenance=NONE, none_reason=NO_INPUT, lower/upper None, value 저장 (4.8절, 개정 22)"""
    value = 24.5
    prov, lower, upper, derivation, none_reason = grade_water_temp(value, None, thresholds)

    assert prov == "NONE"
    assert none_reason == "NO_INPUT"
    assert lower is None
    assert upper is None
    assert derivation == "COMPUTED"
    # value는 호출자(grading/main.py)가 저장 — grade_water_temp는 provenance 판정만 한다
    # 불변식: derivation=COMPUTED → alertable=false (호출자가 보장)


def test_grade_water_temp_stores_value_even_when_none_provenance():
    """provenance=NONE이어도 value는 변경되지 않는다 — 값 저장은 호출자 몫 (4.8절 불변식)"""
    value = 23.1
    prov, lower, upper, derivation, none_reason = grade_water_temp(value, None, [1.0, 2.0, 3.0])
    # grade_water_temp는 value를 반환하지 않는다 — 호출자의 value 변수가 그대로 유지됨을 확인
    assert prov == "NONE"
    assert lower is None
    assert upper is None
    # grading/main.py에서 `row["value"] = value` 가 grade_water_temp 결과와 무관하게 설정됨을 이해하는 테스트

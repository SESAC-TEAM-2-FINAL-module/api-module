"""실행 ID 결정화 (2.2절, 개정 22 — 검수 H2·N5)"""
import uuid

from common.run_ids import RUN_ID_NAMESPACE, run_id_from


def test_namespace_is_module_specific_and_fixed():
    assert RUN_ID_NAMESPACE == uuid.uuid5(uuid.NAMESPACE_URL, "urn:aquasentinel:api-module:run-id")
    assert RUN_ID_NAMESPACE != uuid.NAMESPACE_DNS


def test_same_input_same_id_and_fixed_length():
    long_key = "raw/dtRecent/2026/10/07/1791000000000_DT_0014_y.json::v0.1:water_temp"
    assert run_id_from(long_key) == run_id_from(long_key)
    assert len(run_id_from(long_key)) == 36                     # VARCHAR(64) 안 — 입력 키를 이으면 넘친다
    assert run_id_from(f"obs.loaded:{long_key}") != run_id_from(f"interp.done:{long_key}")

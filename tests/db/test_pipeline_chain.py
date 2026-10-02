"""
I-12 L6·L7 — 단계 연결: dtRecent 원문 → processor → obs.loaded → interpolation → interp.done
→ grading → grade.done → evaluation → farm_readings·axis_status

- farm_sites는 웹 소유라 모델이 없다(1.6절). 테스트 컨테이너에만 합성으로 만들고 끝나면 지운다(2.0.3절 — 운영 스키마 아님)
- 큐는 MemoryQueue. 단계 함수를 차례로 부른다 — 각 단계가 앞 단계의 알림만 보고 도는지 확인한다
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from sqlalchemy import text

from common.queue import MemoryQueue


@pytest.fixture()
def farm_sites(schema_engine):
    with schema_engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE farm_sites (farm_id VARCHAR(64) PRIMARY KEY, lat DOUBLE PRECISION, "
            "lng DOUBLE PRECISION, active BOOLEAN, updated_at_utc TIMESTAMP, area_id VARCHAR(64))"))
        conn.execute(text(
            "INSERT INTO farm_sites VALUES ('syn_gam_001', 34.68, 127.69, TRUE, '2026-07-01 00:00:00', 'jeonnam_yeosu')"))
    yield ["syn_gam_001"]
    with schema_engine.begin() as conn:
        conn.execute(text("DROP TABLE farm_sites"))


def _rows(engine, sql: str) -> list[dict]:
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(text(sql)).mappings().all()]


def _run_to_grading(pm, repo, raw_store, schema_engine, tide):
    import grading.main as gr
    import interpolation.main as ip
    from common.config import load_definitions
    defs = load_definitions()
    # 시연권역 7개소, 같은 시각(KST 09:00 = UTC 00:00) 수온
    obs = [(code, "2026-08-01 09:00:00", 24.0 + i * 0.3) for i, code in enumerate(tide.STATIONS)]
    key = raw_store.put("dtRecent", "all", tide.raw(tide.body(obs)))
    q = MemoryQueue()
    pm.process(key, "dtRecent", q)
    loaded = q.drain("obs.loaded")
    ip.handle_obs_loaded(loaded[0].payload, repo, q, defs)
    interp = q.drain("interp.done")
    gr.handle_interp_done(interp[0].payload, repo, q, defs) if interp else None
    n_interp_grade = len(q.drain("grade.done"))
    gr.handle_obs_loaded(loaded[0].payload, repo, q, defs)
    return q, loaded, interp, n_interp_grade


def test_L6_L7_chain_from_raw_to_result_tables(processor_up, raw_store, schema_engine, tide, farm_sites):
    """수온 경로: 원문 → processor → interpolation → grading(interp.done) → evaluation"""
    import evaluation.main as ev
    pm, repo = processor_up
    op = yaml.safe_load((Path(__file__).parents[2] / "config" / "operational.initial.yaml").read_text("utf-8"))

    q, loaded, interp, _ = _run_to_grading(pm, repo, raw_store, schema_engine, tide)
    assert len(loaded) == 1 and loaded[0].payload["source"] == "tide"
    assert len(_rows(schema_engine, "SELECT * FROM stations WHERE source_api = 'tide'")) == len(tide.STATIONS)
    assert len(interp) == 1, "interpolation이 obs.loaded(조위)를 받아 interp.done을 내야 한다"

    wt = _rows(schema_engine, "SELECT * FROM farm_readings WHERE farm_id = 'syn_gam_001' AND axis = 'water_temp'")
    assert len(wt) == 1
    assert wt[0]["derivation"] == "COMPUTED" and wt[0]["alertable"] is False      # N11
    assert wt[0]["value"] is not None                                              # 영역 판정과 값 저장은 별개

    # evaluation — 수온 grade.done (grading.handle_interp_done이 낸 것과 같은 형태로)
    ev.handle_grade_done({"grade_run_id": "chain", "axis": "water_temp", "farm_ids": ["syn_gam_001"]}, repo, q, op)
    status = _rows(schema_engine, "SELECT * FROM axis_status WHERE farm_id = 'syn_gam_001' AND axis = 'water_temp'")
    assert len(status) == 1
    assert q.drain("result.updated"), "evaluation이 result.updated를 내야 한다"

    # L7 — evaluation 조회가 수집 원천(tide) → api_id(dtRecent) 대응으로 처리 기록을 찾는다 (결정 D2)
    latest = repo.get_latest_ingest_result_by_adapter("tide")
    assert latest is not None and latest["status"] == "OK"


def test_L6_grade_done_from_obs_loaded_matches_contract(processor_up, raw_store, schema_engine, tide, farm_sites):
    import json
    import jsonschema
    from common.repository.tables import AXIS_VALS
    pm, repo = processor_up
    q, *_ = _run_to_grading(pm, repo, raw_store, schema_engine, tide)
    msgs = q.drain("grade.done")
    assert msgs
    contract = json.loads((Path(__file__).parents[2] / "contracts" / "queue" / "queue-v1.json").read_text("utf-8"))
    schema = {**contract["definitions"]["grade_done"], "definitions": contract["definitions"]}
    for m in msgs:
        assert m.payload["axis"] in AXIS_VALS
        jsonschema.validate(m.payload, schema)


def test_L6_all_grade_done_evaluate_to_axis_status(processor_up, raw_store, schema_engine, tide, farm_sites):
    """grading이 낸 grade.done을 그대로 evaluation에 넘기면 축마다 axis_status가 생긴다 (수온 + 인근 실측 축)"""
    import evaluation.main as ev
    pm, repo = processor_up
    op = yaml.safe_load((Path(__file__).parents[2] / "config" / "operational.initial.yaml").read_text("utf-8"))
    import grading.main as gr
    import interpolation.main as ip
    from common.config import load_definitions
    defs = load_definitions()
    obs = [(code, "2026-08-01 09:00:00", 24.0 + i * 0.3) for i, code in enumerate(tide.STATIONS)]
    q = MemoryQueue()
    pm.process(raw_store.put("dtRecent", "all", tide.raw(tide.body(obs))), "dtRecent", q)
    loaded = q.drain("obs.loaded")[0].payload
    ip.handle_obs_loaded(loaded, repo, q, defs)
    gr.handle_interp_done(q.drain("interp.done")[0].payload, repo, q, defs)
    gr.handle_obs_loaded(loaded, repo, q, defs)
    msgs = q.drain("grade.done")
    for m in msgs:
        ev.handle_grade_done(m.payload, repo, q, op)
    axes = {r["axis"] for r in _rows(schema_engine, "SELECT axis FROM axis_status WHERE farm_id = 'syn_gam_001'")}
    assert axes == {m.payload["axis"] for m in msgs}
    assert {"water_temp", "salinity", "tide_level", "wind_speed", "air_temp"} <= axes



# ── 개정 15 — 양식장 해역은 모듈이 정해 알린다 ───────────────────────────────

def test_farm_area_published_and_season_applied(processor_up, schema_engine, farm_sites, monkeypatch):
    """evaluation이 해역을 정해 farm_areas에 쓰고, 그 해역의 계절 선언으로 적조 축을 판정한다"""
    from datetime import datetime
    import evaluation.main as ev
    from processor.adapters.bulletin._seed import load_seeds
    _, repo = processor_up
    load_seeds(repo)
    op = yaml.safe_load((Path(__file__).parents[2] / "config" / "operational.initial.yaml").read_text("utf-8"))
    payload = {"schema": "queue-v1", "topic": "grade.done", "grade_run_id": "t", "axis": "red_tide",
               "farm_ids": ["syn_gam_001"]}

    monkeypatch.setattr(ev, "_now_utc", lambda: datetime(2026, 11, 15, 0, 0, 0))   # 계절 [5..10] 밖
    ev.handle_grade_done(payload, repo, MemoryQueue(), op)
    fa = _rows(schema_engine, "SELECT * FROM farm_areas WHERE farm_id = 'syn_gam_001'")
    assert len(fa) == 1 and fa[0]["area_id"] is not None and fa[0]["rule"] == "NEAREST_CENTER_WITHIN_RADIUS"
    st = _rows(schema_engine, "SELECT state FROM axis_status WHERE farm_id = 'syn_gam_001' AND axis = 'red_tide'")
    assert st[0]["state"] == "OUT_OF_SEASON"

    with schema_engine.begin() as conn:
        conn.execute(text("DELETE FROM axis_status"))
    monkeypatch.setattr(ev, "_now_utc", lambda: datetime(2026, 8, 15, 0, 0, 0))    # 계절 안
    ev.handle_grade_done(payload, repo, MemoryQueue(), op)
    st = _rows(schema_engine, "SELECT state FROM axis_status WHERE farm_id = 'syn_gam_001' AND axis = 'red_tide'")
    assert st[0]["state"] != "OUT_OF_SEASON"

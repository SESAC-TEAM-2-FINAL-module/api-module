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
    ev.handle_grade_done({"schema": "queue-v1", "topic": "grade.done", "grade_run_id": "chain", "axis": "water_temp",
                          "farm_ids": ["syn_gam_001"]}, repo, q, op)
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



# ── 수온 값 재현 — run_id의 기준 시각 관측으로 (최근접 대체·재정규화 금지) ─────

def _interp_at(pm, repo, raw_store, tide, kst: str, values: list[float], tag: str):
    import interpolation.main as ip
    from common.config import load_definitions
    obs = [(code, kst, v) for code, v in zip(tide.STATIONS, values)]
    q = MemoryQueue()
    pm.process(raw_store.put("dtRecent", tag, tide.raw(tide.body(obs))), "dtRecent", q)
    ip.handle_obs_loaded(q.drain("obs.loaded")[0].payload, repo, q, load_definitions())
    return q.drain("interp.done")[0].payload


def _expected_value(schema_engine, run_id: str, farm_id: str, values_by_station: dict) -> float:
    ws = _rows(schema_engine, "SELECT station_id, weight FROM interpolation_weights "
                              f"WHERE run_id = '{run_id}' AND farm_id = '{farm_id}'")
    assert ws and abs(sum(w["weight"] for w in ws) - 1.0) < 1e-9, "관측소마다 한 번, 가중치 합 1"
    return sum(w["weight"] * values_by_station[w["station_id"]] for w in ws)


def test_water_temp_reproduces_run_even_after_newer_observations(processor_up, raw_store, schema_engine,
                                                                 tide, farm_sites):
    """interp.done(09:00)을 처리하기 전에 09:10 관측이 적재돼도 grading 값은 09:00 실행의 값이다"""
    import grading.main as gr
    from common.config import load_definitions
    pm, repo = processor_up
    v0 = [24.0 + i * 0.3 for i in range(len(tide.STATIONS))]
    done = _interp_at(pm, repo, raw_store, tide, "2026-08-01 09:00:00", v0, "t0")
    pm.process(raw_store.put("dtRecent", "t1", tide.raw(tide.body(
        [(c, "2026-08-01 09:10:00", 30.0) for c in tide.STATIONS]))), "dtRecent", MemoryQueue())

    gr.handle_interp_done(done, repo, MemoryQueue(), load_definitions())
    wt = _rows(schema_engine, "SELECT * FROM farm_readings WHERE farm_id = 'syn_gam_001' AND axis = 'water_temp'")[0]
    expected = _expected_value(schema_engine, done["run_id"], "syn_gam_001",
                               {f"tide:{c}": v for c, v in zip(tide.STATIONS, v0)})
    assert wt["value"] == pytest.approx(expected) and wt["source_ref"] == done["run_id"]


def test_idw_uses_one_latest_observation_per_station(processor_up, raw_store, schema_engine, tide, farm_sites):
    """정렬 창 안에 직전 적재(09:00)가 남아 있어도 09:10 실행은 관측소마다 09:10 값 하나만 쓴다 (4.7절)"""
    pm, repo = processor_up
    _interp_at(pm, repo, raw_store, tide, "2026-08-01 09:00:00", [20.0] * len(tide.STATIONS), "t0")
    v1 = [24.0 + i * 0.3 for i in range(len(tide.STATIONS))]
    done = _interp_at(pm, repo, raw_store, tide, "2026-08-01 09:10:00", v1, "t1")
    ws = _rows(schema_engine, f"SELECT station_id FROM interpolation_weights WHERE run_id = '{done['run_id']}'")
    assert len(ws) == len({w["station_id"] for w in ws})
    assert done["stations_used"] == len(tide.STATIONS)
    _expected_value(schema_engine, done["run_id"], "syn_gam_001", {f"tide:{c}": v for c, v in zip(tide.STATIONS, v1)})


def test_water_temp_missing_weighted_observation_is_none_not_renormalized(processor_up, raw_store, schema_engine,
                                                                         tide, farm_sites):
    """가중치를 받은 관측소의 기준 시각 관측이 사라지면 남은 가중치로 다시 나누지 않고 NONE"""
    import grading.main as gr
    from common.config import load_definitions
    pm, repo = processor_up
    done = _interp_at(pm, repo, raw_store, tide, "2026-08-01 09:00:00",
                      [24.0 + i * 0.3 for i in range(len(tide.STATIONS))], "t0")
    top = _rows(schema_engine, "SELECT station_id FROM interpolation_weights "
                               f"WHERE run_id = '{done['run_id']}' ORDER BY weight DESC LIMIT 1")[0]["station_id"]
    with schema_engine.begin() as conn:
        conn.execute(text("DELETE FROM observations WHERE station_id = :s AND metric = 'water_temp'"), {"s": top})

    gr.handle_interp_done(done, repo, MemoryQueue(), load_definitions())
    wt = _rows(schema_engine, "SELECT * FROM farm_readings WHERE farm_id = 'syn_gam_001' AND axis = 'water_temp'")[0]
    assert wt["value"] is None and wt["provenance"] == "NONE" and wt["none_reason"] == "NO_INPUT"
    assert wt["derivation"] == "COMPUTED" and wt["alertable"] is False


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


# ── C4 — 체인에서 나오는 알림은 전부 queue-v1 계약을 통과한다 ────────────────────

def test_all_chain_messages_match_queue_contract(processor_up, raw_store, schema_engine, tide, farm_sites,
                                                 monkeypatch):
    import json
    from datetime import datetime
    import jsonschema
    import common.repository.sql as sql_mod
    import evaluation.main as ev
    import grading.main as gr
    import interpolation.main as ip
    from common.config import load_definitions

    now = datetime(2026, 8, 1, 0, 10, 0)

    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return now.replace(tzinfo=tz) if tz else now

    for mod, name in ((gr, "_utcnow"), (ip, "_utcnow"), (ev, "_now_utc")):
        monkeypatch.setattr(mod, name, lambda: now)
    monkeypatch.setattr(sql_mod, "datetime", _Frozen)

    pm, repo = processor_up
    defs = load_definitions()
    op = yaml.safe_load((Path(__file__).parents[2] / "config" / "operational.initial.yaml").read_text("utf-8"))
    for h in range(3, 9):          # 오늘의 오차가 계산되도록 앞선 관측
        prior = [(c, f"2026-08-01 0{h}:00:00", 23.0 + h * 0.1 + i * 0.4) for i, c in enumerate(tide.STATIONS)]
        pm.process(raw_store.put("dtRecent", f"h{h}", tide.raw(tide.body(prior))), "dtRecent", MemoryQueue())

    q = MemoryQueue()
    sent: list = []
    obs = [(c, "2026-08-01 09:00:00", 24.0 + i * 0.3) for i, c in enumerate(tide.STATIONS)]
    pm.process(raw_store.put("dtRecent", "all", tide.raw(tide.body(obs))), "dtRecent", q)
    loaded = q.drain("obs.loaded"); sent += loaded
    ip.handle_obs_loaded(loaded[0].payload, repo, q, defs)
    interp = q.drain("interp.done"); sent += interp
    gr.handle_interp_done(interp[0].payload, repo, q, defs)
    gr.handle_obs_loaded(loaded[0].payload, repo, q, defs)
    graded = q.drain("grade.done"); sent += graded
    for m in graded:
        ev.handle_grade_done(m.payload, repo, q, op)
    sent += q.drain("result.updated")

    contract = json.loads((Path(__file__).parents[2] / "contracts" / "queue" / "queue-v1.json").read_text("utf-8"))
    topics = {m.topic for m in sent}
    assert {"obs.loaded", "interp.done", "grade.done", "result.updated"} <= topics
    for m in sent:
        definition = contract["definitions"][m.topic.replace(".", "_")]
        jsonschema.validate(m.payload, {**definition, "definitions": contract["definitions"]})


# ── C13 — 적조 유효 기간 기준일은 KST 날짜 (day_report가 KST 날짜) ──────────────

@pytest.mark.parametrize("now_utc,expected_ref", [
    ("2026-08-21T14:00:00", "20260818-001#1"),   # KST 08-21 23:00 — 0818 속보가 3일 안
    ("2026-08-21T16:00:00", None),               # KST 08-22 01:00 — 3일 밖 (UTC 날짜로는 아직 08-21)
])
def test_red_tide_validity_uses_kst_date(processor_up, raw_store, schema_engine, farm_sites, monkeypatch,
                                         now_utc, expected_ref):
    from datetime import datetime
    import grading.main as gr
    from common.config import load_definitions
    from processor.adapters.bulletin._seed import load_seeds
    pm, repo = processor_up
    load_seeds(repo)
    q = MemoryQueue()
    pm.process(raw_store.put_fixture("redtideList", "r1", "redtideList_r1_*.json"), "redtideList", q)
    monkeypatch.setattr(gr, "_utcnow", lambda: datetime.fromisoformat(now_utc))
    gr.handle_obs_loaded(q.drain("obs.loaded")[0].payload, repo, MemoryQueue(), load_definitions())
    rt = _rows(schema_engine, "SELECT * FROM farm_readings WHERE farm_id = 'syn_gam_001' AND axis = 'red_tide'")[0]
    assert rt["source_ref"] == expected_ref

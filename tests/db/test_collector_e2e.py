"""
연결 검사 — 매니페스트의 워크로드 명령으로 collector부터 결과 테이블까지 (2026-10-01 점검 후속)

공공 API는 호출하지 않는다. HTTP 호출층(fetch)만 픽스처 원문을 돌려주는 가짜로 바꾼다.
collector.main(워크로드) → 원문 저장 → raw.fetched(계약 queue-v1) → processor → DB → (tide) 이후 단계
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
import yaml
from sqlalchemy import text

from common.queue import MemoryQueue

from .conftest import count_rows

_ROOT = Path(__file__).parents[2]
_FIX = _ROOT / "fixtures" / "raw"
_CONTRACT = json.loads((_ROOT / "contracts" / "queue" / "queue-v1.json").read_text("utf-8"))


def _body(glob: str) -> str:
    return json.loads(next(_FIX.glob(glob)).read_text("utf-8"))["body"]


def _ok(body: str) -> dict:
    return {"url": "https://example.invalid/", "params": {"key": "***"}, "http_status": 200,
            "final_url": None, "fetched_at": "2026-09-20T00:00:00", "body": body, "error": None}


@pytest.fixture()
def collectors(monkeypatch, tide):
    """수집 환경(가짜 URL·키) + 원천별 가짜 fetch. 반환: 실패 주입 스위치"""
    import collector.main as cm
    import collector.adapters.tide._adapter as ct
    import collector.adapters.bulletin._adapter as cb
    import collector.adapters.line._adapter as cl
    import collector.adapters.fishery._adapter as cf
    import collector.fishery_watch as cw
    cm._load_adapters()
    for var in ("DTRECENT_URL", "NIFS_URL"):
        monkeypatch.setenv(var, "https://example.invalid/")
    for var in ("DTRECENT_KEY", "NIFS_KEY_BULLETIN", "NIFS_KEY_LINE", "NIFS_KEY_FISHERY_SEA"):
        monkeypatch.setenv(var, "test-placeholder")

    state = {"fail": False}
    empty_femo = _body("femoSeaList_f1_*.json")
    femo = {2023: _body("femoSeaList_f3_2023_*.json"), 2024: _body("femoSeaList_f3_2024_*.json"),
            2025: _body("femoSeaList_f3_2025_*.json")}

    def _fail():
        return {"url": "https://example.invalid/", "params": {}, "http_status": None, "final_url": None,
                "fetched_at": "2026-09-20T00:00:00", "body": None,
                "error": {"type": "NET_ERROR", "message": "연결 실패 주입"}}

    def tide_fetch(url, params, key_name, key, *a, **k):
        if state["fail"]:
            return _fail()
        code = params["obsCode"]
        return _ok(tide.body([(code, "2026-08-01 09:00:00", 24.5)]) if code in tide.STATIONS else tide.body([]))

    def nifs_fetch(url, params, key_name, key, *a, **k):
        if state["fail"]:
            return _fail()
        api, sdate = params["id"], params.get("sdate", "")
        if api == "redtideList":
            return _ok(_body("redtideList_r1_*.json"))
        if api == "sooList":
            return _ok(_body("sooList_depth_*.json"))
        if api == "femoSeaList":
            year = int(sdate[:4]) if sdate else 0
            return _ok(femo.get(year, empty_femo))
        raise AssertionError(f"모르는 호출: {api}")

    monkeypatch.setattr(ct, "fetch", tide_fetch)
    for mod in (cb, cl, cf, cw):
        monkeypatch.setattr(mod, "fetch", nifs_fetch)
    monkeypatch.setattr(ct.time, "sleep", lambda s: None)
    return state


def _run(workload: str) -> list:
    import collector.main as cm
    q = MemoryQueue()
    cm.main(workload, q)
    msgs = q.drain("raw.fetched")
    schema = {**_CONTRACT["definitions"]["raw_fetched"], "definitions": _CONTRACT["definitions"]}
    import jsonschema
    for m in msgs:
        jsonschema.validate(m.payload, schema)            # 계약 queue-v1
    return msgs


def _process(pm, msgs) -> MemoryQueue:
    q = MemoryQueue()
    for m in msgs:
        pm.process(m.payload["raw_id"], m.payload["api"], q)
    return q


@pytest.mark.parametrize("workload,table,min_rows", [
    ("bulletin", "bulletins", 1),
    ("line", "line_observations", 1),
    ("fishery-backfill", "survey_observations", 1),
])
def test_workload_to_db(processor_up, raw_store, schema_engine, collectors, workload, table, min_rows):
    pm, _ = processor_up
    msgs = _run(workload)
    assert msgs, f"{workload}: raw.fetched 없음"
    _process(pm, msgs)
    assert count_rows(schema_engine, table) >= min_rows
    assert count_rows(schema_engine, "ingest_runs") == len(msgs)


def test_fishery_backfill_years_and_stop(processor_up, raw_store, schema_engine, collectors):
    """백필: 직전 연도부터 거슬러 올라가 연속 2개 연도 0건이면 정지 — 2023~2025는 적재 (2.1절)"""
    pm, _ = processor_up
    msgs = _run("fishery-backfill")
    tags = [m.payload["tag"] for m in msgs]
    this_year = date.today().year
    assert tags[0] == str(this_year - 1)
    _process(pm, msgs)
    with schema_engine.connect() as conn:
        years = {r[0] for r in conn.execute(text("SELECT DISTINCT surveyed_on FROM survey_observations"))}
    assert {y.year for y in years} >= {2023, 2024, 2025}


def test_fishery_watch_to_publication_checks(processor_up, raw_store, schema_engine, collectors):
    pm, _ = processor_up
    msgs = _run("fishery-watch")
    assert msgs and msgs[0].payload["api"] == "femoSeaList-watch"
    _process(pm, msgs)
    assert count_rows(schema_engine, "publication_checks") == 1


def test_completeness_publishes_no_raw_fetched(processor_up, raw_store, schema_engine, collectors):
    """분할 합산 원문에는 raw.fetched가 없다 — processor는 받지 않는다 (개정 17 보완).
    완료 알림·판정은 tests/db/test_completeness_e2e.py"""
    msgs = _run("completeness")
    assert msgs == []
    assert count_rows(schema_engine, "raw_index") == 0


def test_failed_call_is_kept_and_counted(processor_up, raw_store, schema_engine, collectors):
    """호출 실패도 원문으로 남고(2.3절) processor가 adapter_health에 장애로 센다(4.9절)"""
    pm, _ = processor_up
    collectors["fail"] = True
    msgs = _run("bulletin")
    assert len(msgs) == 1
    _process(pm, msgs)
    with schema_engine.connect() as conn:
        h = conn.execute(text("SELECT adapter, consecutive_failures FROM adapter_health")).mappings().all()
        st = conn.execute(text("SELECT status FROM ingest_runs")).scalar_one()
    assert [dict(r) for r in h] == [{"adapter": "bulletin", "consecutive_failures": 1}]
    assert st == "NET_ERROR"


def test_tide_workload_through_result_tables(processor_up, raw_store, schema_engine, collectors, farm_sites_table):
    """tide 워크로드 → processor → interpolation → grading → evaluation → farm_readings·axis_status"""
    import evaluation.main as ev
    import grading.main as gr
    import interpolation.main as ip
    from common.config import load_definitions
    pm, repo = processor_up
    defs = load_definitions()
    op = yaml.safe_load((_ROOT / "config" / "operational.initial.yaml").read_text("utf-8"))

    msgs = _run("tide")
    assert len(msgs) == len(defs["tide"]["stations"])         # 관측소마다 원문 하나
    q = _process(pm, msgs)
    for loaded in q.drain("obs.loaded"):
        ip.handle_obs_loaded(loaded.payload, repo, q, defs)
        gr.handle_obs_loaded(loaded.payload, repo, q, defs)
    for interp in q.drain("interp.done"):
        gr.handle_interp_done(interp.payload, repo, q, defs)
    for g in q.drain("grade.done"):
        ev.handle_grade_done(g.payload, repo, q, op)
    with schema_engine.connect() as conn:
        axes = {r[0] for r in conn.execute(text("SELECT axis FROM axis_status WHERE farm_id = 'syn_gam_001'"))}
        wt = conn.execute(text("SELECT derivation, alertable FROM farm_readings "
                               "WHERE farm_id = 'syn_gam_001' AND axis = 'water_temp'")).mappings().all()
    assert {"water_temp", "salinity", "tide_level"} <= axes
    assert [dict(r) for r in wt] == [{"derivation": "COMPUTED", "alertable": False}]


# ── 2026-10-02 점검 C7·C12 — 게시 감시 직전 건수, 실패 원문 보관, 백필 실패 ────────────

@pytest.fixture()
def watch_2025(monkeypatch, collectors):
    """게시 감시의 '올해'를 2025로 — 픽스처에 2025년 어장환경 원문이 있다"""
    import collector.fishery_watch as cw
    monkeypatch.setattr(cw, "kst_today", lambda: date(2025, 12, 1))
    return collectors


def test_fishery_watch_second_run_skips_full_fetch(processor_up, raw_store, schema_engine, watch_2025):
    """직전 감시 원문의 건수와 같으면 전량 호출을 하지 않는다 (2.1절). 첫 실행은 직전 원문이 없어 전량 수집"""
    first = [m.payload["api"] for m in _run("fishery-watch")]
    second = [m.payload["api"] for m in _run("fishery-watch")]
    assert first == ["femoSeaList-watch", "femoSeaList"]
    assert second == ["femoSeaList-watch"]


def test_fishery_watch_full_fetch_failure_is_kept(processor_up, raw_store, schema_engine, watch_2025, monkeypatch):
    """전량 호출이 실패해도 원문을 저장·발행한다 — processor가 장애로 센다 (2.3절, 개정 16)"""
    import collector.fishery_watch as cw
    real = cw.fetch
    calls = {"n": 0}

    def second_fails(*a, **k):
        calls["n"] += 1
        if calls["n"] == 2:
            return {"url": "https://example.invalid/", "params": {}, "http_status": None, "final_url": None,
                    "fetched_at": "2026-09-20T00:00:01", "body": None,
                    "error": {"type": "NET_ERROR", "message": "주입"}}
        return real(*a, **k)

    monkeypatch.setattr(cw, "fetch", second_fails)
    pm, _ = processor_up
    msgs = _run("fishery-watch")
    assert [m.payload["api"] for m in msgs] == ["femoSeaList-watch", "femoSeaList"]
    _process(pm, msgs)
    with schema_engine.connect() as conn:
        statuses = sorted(r[0] for r in conn.execute(text("SELECT status FROM ingest_runs")))
    assert "NET_ERROR" in statuses


def test_fishery_backfill_failure_stops_without_counting_zero(processor_up, raw_store, schema_engine, collectors):
    """백필 호출 실패 → 0건으로 세지 않고 원문을 발행한 뒤 멈춘다(다음 연도로 넘어가지 않는다) (4.5·3.1절)"""
    import collector.main as cm
    collectors["fail"] = True
    q = MemoryQueue()
    with pytest.raises(SystemExit):
        cm.main("fishery-backfill", q)
    msgs = q.drain("raw.fetched")
    assert len(msgs) == 1                                   # 첫 연도 실패 원문 하나 — 더 거슬러 가지 않는다

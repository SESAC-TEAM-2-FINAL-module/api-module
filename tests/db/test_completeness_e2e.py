"""
7.9 E7 — 분할 합산 (계획서 3.3절 "분할 합산 처리 경로", 개정 17)

collector `completeness` 워크로드 → 원문 저장 + 원천마다 completeness.collected(raw.fetched 없음 — 개정 17 보완)
→ 검사기(processor.main.completeness_check) → completeness_checks 한 행.
공공 API는 호출하지 않는다 — 가짜 fetch가 픽스처 항목 중 **요청 창 안의 것만** 돌려준다(실제 API처럼).
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest
from sqlalchemy import text

from common.queue import MemoryQueue

from .conftest import count_rows

_ROOT = Path(__file__).parents[2]
_FIX = _ROOT / "fixtures" / "raw"
_CONTRACT = json.loads((_ROOT / "contracts" / "queue" / "queue-v2.json").read_text("utf-8"))
_END = date(2025, 11, 30)          # 고정한 실행의 "KST 어제" — 세 원천 픽스처가 모두 이 창에 항목을 갖는다
_RUN_KEY = "20251201T000000"


def _items(glob: str) -> list[dict]:
    from common.classifier import parse
    return parse(json.loads(next(_FIX.glob(glob)).read_text("utf-8"))["body"]).items


def _date_of(api: str, it: dict) -> str:
    if api == "redtideList":
        return it["day_report"][:8]
    if api == "sooList":
        return it["obs_dtm"][:10].replace("-", "")
    return f"{int(it['DATE_Y']):04d}{int(it['DATE_M']):02d}{int(it['DATE_D']):02d}"


@pytest.fixture()
def nifs(monkeypatch):
    """창을 반영하는 가짜 NIFS — mode로 절단·실패를 주입한다. 반환: 상태 dict"""
    import collector._completeness as cc
    import collector.adapters.bulletin._adapter as cb
    import collector.adapters.fishery._adapter as cf
    import collector.adapters.line._adapter as cl
    import collector.main as cm
    cm._load_adapters()
    monkeypatch.setenv("NIFS_URL", "https://example.invalid/")
    monkeypatch.setenv("DTRECENT_URL", "https://example.invalid/")
    for var in ("NIFS_KEY_BULLETIN", "NIFS_KEY_LINE", "NIFS_KEY_FISHERY_SEA"):
        monkeypatch.setenv(var, "test-placeholder")
    monkeypatch.setattr(cc.CompletenessRun, "start",
                        staticmethod(lambda now_utc=None: cc.CompletenessRun(run_key=_RUN_KEY, end=_END)))

    pool = {"redtideList": _items("redtideList_r1_*.json") + _items("redtideList_r3_*.json"),
            "sooList": _items("sooList_depth_*.json"),
            "femoSeaList": _items("femoSeaList_f3_2025_*.json")}
    state = {"mode": "ok", "target": "sooList", "calls": []}   # 정선 — 13개월에 걸쳐 분할이 여럿

    def fake(url, params, key_name, key, *a, **k):
        api, s, e = params["id"], params["sdate"], params["edate"]
        state["calls"].append((api, s, e))
        items = [it for it in pool[api] if s <= _date_of(api, it) <= e]
        is_single = (s, e) == state.get(f"single_{api}")
        if api == state["target"]:
            if state["mode"] == "single_trunc" and is_single and items:
                items = items[:-1]
            if state["mode"] == "part_trunc" and not is_single and items and s == state.get(f"last_part_{api}"):
                items = items[:-1]
            if state["mode"] == "part_fail" and not is_single and s == state.get(f"last_part_{api}"):
                return {"url": url, "params": {"id": api, "key": "***", "sdate": s, "edate": e},
                        "http_status": None, "final_url": None, "fetched_at": "2025-12-01T00:00:00",
                        "body": None, "error": {"type": "NET_ERROR", "message": "주입"}}
        body = json.dumps({"header": {"resultCode": "00", "resultMsg": "success"}, "body": {"item": items}},
                          ensure_ascii=False)
        return {"url": url, "params": {"id": api, "key": "***", "sdate": s, "edate": e}, "http_status": 200,
                "final_url": None, "fetched_at": "2025-12-01T00:00:00", "body": body, "error": None}

    for mod in (cb, cl, cf):
        monkeypatch.setattr(mod, "fetch", fake)
    # 각 원천의 단일 창·마지막 분할 시작을 미리 알려 둔다(주입 대상 식별용)
    from collector.adapters.line._adapter import year_window
    from common.clock import split_by_month
    wins = {"sooList": year_window(_END),
            "femoSeaList": (date(_END.year, 1, 1), _END)}
    for api, (s, e) in wins.items():
        state[f"single_{api}"] = (s.strftime("%Y%m%d"), e.strftime("%Y%m%d"))
        state[f"last_part_{api}"] = split_by_month(s, e)[-1][0].strftime("%Y%m%d")
    return state


def _run(pm):
    """completeness 워크로드 → 검사기. 반환: (알림들, raw.fetched 수, obs.loaded 수) — 뒤 둘은 0이어야 한다"""
    import collector.main as cm
    import jsonschema
    q = MemoryQueue()
    cm.main("completeness", q)
    notices = q.drain("completeness.collected")
    raws = q.drain("raw.fetched")
    schema = {**_CONTRACT["definitions"]["completeness_collected"], "definitions": _CONTRACT["definitions"]}
    for n in notices:
        jsonschema.validate(n.payload, schema)
    q2 = MemoryQueue()
    for m in raws:
        pm.process(m.payload["raw_id"], m.payload["api"], q2)
    for n in notices:
        pm.completeness_check(n.payload, now_utc=datetime(2025, 12, 1, 1, 0, 0))
    return notices, len(raws), len(q2.drain("obs.loaded"))


def _rows(engine, sql):
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(text(sql)).mappings().all()]


def _check(engine, api):
    rows = _rows(engine, f"SELECT * FROM completeness_checks WHERE api = '{api}'")
    assert len(rows) == 1
    return rows[0]


def test_E7_all_sources_ok_and_processor_untouched(processor_up, raw_store, schema_engine, nifs):
    pm, _ = processor_up
    notices, n_raw, n_loaded = _run(pm)
    # 적조는 분할 합산에서 뺐다 — 알림·호출·결과 행 0 (3.3절, 개정 18)
    assert {n.payload["api"] for n in notices} == {"sooList", "femoSeaList"}
    assert not [c for c in nifs["calls"] if c[0] == "redtideList"]
    assert not _rows(schema_engine, "SELECT * FROM completeness_checks WHERE api = 'redtideList'")
    for api in ("sooList", "femoSeaList"):
        r = _check(schema_engine, api)
        assert r["status"] == "OK" and r["single_count"] == r["split_sum"] and r["run_key"] == _RUN_KEY
    # 분할 원문은 processor에 가지 않는다 — raw.fetched 0건, 색인·처리 기록·관측 테이블 어디에도 없다
    assert n_raw == 0
    for tbl in ("raw_index", "ingest_runs", "adapter_health", "bulletins", "line_observations", "survey_observations", "stations"):
        assert count_rows(schema_engine, tbl) == 0, tbl
    assert n_loaded == 0


def test_E7_single_first_then_parts(processor_up, raw_store, schema_engine, nifs):
    """원천마다 단일 창을 먼저 부른다 (3.3절 — 실행 중 증가가 분할만 키우지 않게)"""
    pm, _ = processor_up
    _run(pm)
    for api in ("sooList", "femoSeaList"):
        calls = [c for c in nifs["calls"] if c[0] == api]
        assert (calls[0][1], calls[0][2]) == nifs[f"single_{api}"]


def test_E7_line_window_is_same_day_last_year(processor_up, raw_store, schema_engine, nifs):
    pm, _ = processor_up
    _run(pm)
    r = _check(schema_engine, "sooList")
    assert (r["window_start"], r["window_end"]) == (date(2024, 11, 30), _END)


@pytest.mark.parametrize("mode,status,side,reason", [
    ("single_trunc", "INCOMPLETE", "SINGLE", None),
    ("part_trunc", "INCOMPLETE", "SPLIT", None),
    ("part_fail", "INVALID", None, "PART_STATUS"),
])
def test_E7_injected_faults(processor_up, raw_store, schema_engine, nifs, mode, status, side, reason):
    pm, _ = processor_up
    nifs["mode"] = mode
    _run(pm)
    r = _check(schema_engine, "sooList")
    assert (r["status"], r["truncated_side"], r["reason"]) == (status, side, reason)
    events = _rows(schema_engine, "SELECT event_type FROM ops_events WHERE api = 'sooList'")
    assert [e["event_type"] for e in events] == [status]
    assert _check(schema_engine, "femoSeaList")["status"] == "OK"   # 다른 원천은 그대로


def test_E7_missing_part_window_is_range_mismatch(processor_up, raw_store, schema_engine, nifs):
    pm, _ = processor_up
    import collector.main as cm
    q = MemoryQueue()
    cm.main("completeness", q)
    notice = next(n.payload for n in q.drain("completeness.collected") if n.payload["api"] == "sooList")
    notice = {**notice, "parts": notice["parts"][:3] + notice["parts"][4:]}       # 가운데 달 하나를 뺀다
    pm.completeness_check(notice, now_utc=datetime(2025, 12, 1, 1, 0, 0))
    assert _check(schema_engine, "sooList")["status"] == "COMPARISON_RANGE_MISMATCH"


def test_E7_duplicate_notice_changes_nothing(processor_up, raw_store, schema_engine, nifs):
    pm, _ = processor_up
    nifs["mode"] = "single_trunc"
    notices, _, _ = _run(pm)
    before = _check(schema_engine, "sooList")
    assert before["status"] == "INCOMPLETE"
    n_events = count_rows(schema_engine, "ops_events")
    for n in notices:
        pm.completeness_check(n.payload, now_utc=datetime(2025, 12, 2, 0, 0, 0))   # 하루 뒤 재전달
    assert _check(schema_engine, "sooList") == before                              # checked_at_utc 포함
    assert count_rows(schema_engine, "ops_events") == n_events


def test_E7_raw_missing_does_not_overwrite_judged_row(processor_up, raw_store, schema_engine, nifs, monkeypatch):
    pm, _ = processor_up
    notices, _, _ = _run(pm)
    before = _check(schema_engine, "femoSeaList")
    import processor.completeness._split_check as sc
    monkeypatch.setattr(sc, "get_raw_meta", lambda raw_id: None)                    # 일시적으로 원문을 못 읽음
    for n in notices:
        pm.completeness_check(n.payload, now_utc=datetime(2025, 12, 2, 0, 0, 0))
    assert _check(schema_engine, "femoSeaList") == before


def test_E7_raw_missing_then_recovered_is_judged(processor_up, raw_store, schema_engine, nifs, monkeypatch):
    pm, _ = processor_up
    import collector.main as cm
    import processor.completeness._split_check as sc
    q = MemoryQueue()
    cm.main("completeness", q)
    notice = next(n.payload for n in q.drain("completeness.collected") if n.payload["api"] == "femoSeaList")
    real = sc.get_raw_meta
    monkeypatch.setattr(sc, "get_raw_meta", lambda raw_id: None)
    pm.completeness_check(notice, now_utc=datetime(2025, 12, 1, 1, 0, 0))
    assert _check(schema_engine, "femoSeaList")["reason"] == "RAW_MISSING"
    monkeypatch.setattr(sc, "get_raw_meta", real)
    pm.completeness_check(notice, now_utc=datetime(2025, 12, 1, 2, 0, 0))
    assert _check(schema_engine, "femoSeaList")["status"] == "OK"

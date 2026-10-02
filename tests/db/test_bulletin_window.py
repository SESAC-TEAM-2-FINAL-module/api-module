"""
I-14 — 적조 직전 원문 대조 (계획서 3.3절 "적조 직전 원문 대조", 7.2절 N15·N16, 개정 18)

원문 저장소(임시 디스크) → processor.process() → 고른 DB. 직전 원문은 원문 저장소 키 순서로 정해지므로
처리 순서를 바꿔도 결과가 같아야 한다. 원문 키의 순서는 raw_store.put 호출 순서(epoch_ms 증가)다.
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from common.metrics import bulletin_window_check_skipped_total, bulletin_window_missing_total
from common.queue import MemoryQueue

from .conftest import count_rows

_WIN = ("20260901", "20260930")          # 30일 창 (2.1절)
_TAG = f"{_WIN[0]}_{_WIN[1]}"


def _bulletin(code: str, day: str) -> dict:
    return {"cod_news": code, "day_report": day,
            "item2": [{"nam_biology": "Cochlodinium polykrikoides", "txt_seas": "전남 득량만",
                       "min_density": "1", "max_density": "5", "min_watertemp": "", "max_watertemp": "",
                       "min_salt": "", "max_salt": ""}]}


def _raw(items: list[dict] | None, window=_WIN, *, error: bool = False, body: str | None = None) -> dict:
    s, e = window
    params = {"id": "redtideList", "key": "***", "sdate": s, "edate": e}
    if error:
        return {"url": "https://example.invalid/", "params": params, "http_status": None, "final_url": None,
                "fetched_at": "2026-09-20T00:00:00", "body": None, "error": {"type": "NET_ERROR", "message": "주입"}}
    if body is None:
        body = json.dumps({"header": {"resultCode": "00", "resultMsg": "success"}, "body": {"item": items or []}},
                          ensure_ascii=False)
    return {"url": "https://example.invalid/", "params": params, "http_status": 200, "final_url": None,
            "fetched_at": "2026-09-20T00:00:00", "body": body, "error": None}


def _put(raw_store, items, window=_WIN, tag=None, **kw) -> str:
    return raw_store.put("redtideList", tag or f"{window[0]}_{window[1]}", _raw(items, window, **kw))


def _events(engine) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT detail FROM ops_events WHERE event_type = 'BULLETIN_WINDOW_MISSING' ORDER BY id")).all()
    return [json.loads(r[0]) if isinstance(r[0], str) else r[0] for r in rows]


def _status(engine, key: str) -> str:
    with engine.connect() as conn:
        return conn.execute(text(
            "SELECT r.status FROM ingest_runs r JOIN raw_index i ON i.id = r.raw_id WHERE i.storage_key = :k"),
            {"k": key}).scalar_one()


@pytest.fixture()
def metrics():
    bulletin_window_missing_total._values.clear()
    bulletin_window_check_skipped_total._values.clear()
    return {"missing": bulletin_window_missing_total._values,
            "skipped": bulletin_window_check_skipped_total._values}


X = _bulletin("20260915-001", "20260915")
A = _bulletin("20260920-001", "20260920")


# ── N15 — 잡아야 하는 것 ──────────────────────────────────────────────────────

class TestN15Detects:

    def test_one_missing_then_quiet(self, processor_up, raw_store, schema_engine, metrics):
        """① 창 안 속보 X가 빠짐 → 1건, 응답 상태 그대로. 다음 원문(여전히 없음)에서는 없음"""
        pm, _ = processor_up
        k1, k2, k3 = _put(raw_store, [X, A]), _put(raw_store, [A]), _put(raw_store, [A])
        for k in (k1, k2, k3):
            pm.process(k, "redtideList", MemoryQueue())
        ev = _events(schema_engine)
        assert len(ev) == 1
        assert [m["cod_news"] for m in ev[0]["missing"]] == ["20260915-001"]
        assert ev[0]["raw_key"] == k2 and ev[0]["prev_raw_key"] == k1 and ev[0]["window"] == list(_WIN)
        assert _status(schema_engine, k2) == "OK"            # INCOMPLETE로 두지 않는다
        assert metrics["missing"][()] == 1

    def test_ok_empty_flags_all_in_window(self, processor_up, raw_store, schema_engine, metrics):
        """② 이번 원문 OK_EMPTY, 직전 원문 창 안 3건 → 1건(빠진 3개)"""
        pm, _ = processor_up
        prev = [X, A, _bulletin("20260925-001", "20260925")]
        k1, k2 = _put(raw_store, prev), _put(raw_store, [])
        for k in (k1, k2):
            pm.process(k, "redtideList", MemoryQueue())
        ev = _events(schema_engine)
        assert len(ev) == 1 and len(ev[0]["missing"]) == 3
        assert _status(schema_engine, k2) == "OK_EMPTY"
        assert metrics["missing"][()] == 3

    def test_boundary_sdate_included(self, processor_up, raw_store, schema_engine, metrics):
        """③ day_report = sdate → 포함"""
        pm, _ = processor_up
        edge = _bulletin("20260901-001", "20260901")
        for k in (_put(raw_store, [edge, A]), _put(raw_store, [A])):
            pm.process(k, "redtideList", MemoryQueue())
        ev = _events(schema_engine)
        assert len(ev) == 1 and ev[0]["missing"][0]["cod_news"] == "20260901-001"

    def test_same_day_number_replaced(self, processor_up, raw_store, schema_engine, metrics):
        """④ 같은 day_report의 번호 교체 → 1건, same_day_replaced = true"""
        pm, _ = processor_up
        y = _bulletin("20260916-002", "20260915")
        for k in (_put(raw_store, [X, A]), _put(raw_store, [y, A])):
            pm.process(k, "redtideList", MemoryQueue())
        ev = _events(schema_engine)
        assert len(ev) == 1
        assert ev[0]["missing"] == [{"cod_news": "20260915-001", "day_report": "20260915", "same_day_replaced": True}]


# ── N16 — 걸리면 안 되는 것 ───────────────────────────────────────────────────

class TestN16DoesNotFlag:

    def test_slid_out_of_window(self, processor_up, raw_store, schema_engine, metrics):
        """① 직전 원문의 속보가 이번 창 밖으로 밀림"""
        pm, _ = processor_up
        first = _bulletin("20260901-001", "20260901")
        k1 = _put(raw_store, [first, A])
        k2 = _put(raw_store, [A], window=("20260902", "20261001"))
        for k in (k1, k2):
            pm.process(k, "redtideList", MemoryQueue())
        assert _events(schema_engine) == []

    @pytest.mark.parametrize("order", [(0, 2, 1), (0, 1, 2)])
    def test_out_of_order_flags_once(self, processor_up, raw_store, schema_engine, metrics, order):
        """② N−1·N 둘 다 X 없음, N−2에 있음 — 처리 순서와 무관하게 N−1에서 1건만"""
        pm, _ = processor_up
        keys = [_put(raw_store, [X, A]), _put(raw_store, [A]), _put(raw_store, [A])]
        for i in order:
            pm.process(keys[i], "redtideList", MemoryQueue())
        ev = _events(schema_engine)
        assert len(ev) == 1 and ev[0]["raw_key"] == keys[1]

    def test_late_old_raw(self, processor_up, raw_store, schema_engine, metrics):
        """③ 나중 원문에 새 속보 Y, 늦게 온 옛 원문에는 없음"""
        pm, _ = processor_up
        y = _bulletin("20260921-001", "20260921")
        k_old, k_new = _put(raw_store, [A]), _put(raw_store, [A, y])
        pm.process(k_new, "redtideList", MemoryQueue())
        pm.process(k_old, "redtideList", MemoryQueue())
        assert _events(schema_engine) == []

    def test_duplicate_and_reprocess(self, processor_up, raw_store, schema_engine, metrics, monkeypatch):
        """④ 같은 알림 두 번·파서 버전을 올린 재처리 → 추가 이벤트 없음"""
        pm, _ = processor_up
        k1, k2 = _put(raw_store, [X, A]), _put(raw_store, [A])
        for k in (k1, k2, k2):
            pm.process(k, "redtideList", MemoryQueue())
        monkeypatch.setattr(pm, "PARSER_VERSION", "v0.2-test")
        pm.process(k2, "redtideList", MemoryQueue())
        assert len(_events(schema_engine)) == 1

    @pytest.mark.parametrize("bad", ["net_error", "parse_failure"])
    def test_failed_prev_uses_earlier_normal(self, processor_up, raw_store, schema_engine, metrics, bad):
        """⑤ 바로 앞 원문이 실패 → 그 앞 정상 원문을 직전으로. X가 거기 있고 이번에 없으면 1건"""
        pm, _ = processor_up
        k1 = _put(raw_store, [X, A])
        k2 = _put(raw_store, None, error=True) if bad == "net_error" else _put(raw_store, None, body="<<깨진 본문>>")
        k3 = _put(raw_store, [A])
        for k in (k1, k2, k3):
            pm.process(k, "redtideList", MemoryQueue())
        ev = _events(schema_engine)
        assert len(ev) == 1 and ev[0]["raw_key"] == k3 and ev[0]["prev_raw_key"] == k1

    def test_first_run_no_prev(self, processor_up, raw_store, schema_engine, metrics):
        """⑥ 처음 실행 → 이벤트 없음, NO_PREV 건너뜀 지표"""
        pm, _ = processor_up
        pm.process(_put(raw_store, [X, A]), "redtideList", MemoryQueue())
        assert _events(schema_engine) == []
        assert metrics["skipped"][(("reason", "NO_PREV"),)] == 1

    def test_current_abnormal_not_checked(self, processor_up, raw_store, schema_engine, metrics):
        """⑦ 이번 원문이 비정상(PARSE_FAILURE) → 대조하지 않음(건너뜀 지표도 없음)"""
        pm, _ = processor_up
        _k1 = _put(raw_store, [X, A])
        pm.process(_k1, "redtideList", MemoryQueue())
        metrics["skipped"].clear()
        pm.process(_put(raw_store, None, body="<<깨진 본문>>"), "redtideList", MemoryQueue())
        assert _events(schema_engine) == [] and not metrics["skipped"]

    def test_current_filter_ignored_not_checked(self):
        """⑦ FILTER_IGNORED — 정상 응답이 아니면 대조 함수를 부르지 않는다"""
        from common.classifier import ParsedResponse
        from processor._load import _check_bulletin_window
        assert _check_bulletin_window("redtideList", True, "FILTER_IGNORED", "{}", "raw/redtideList/2026/09/20/1_x.json",
                                      {}, ParsedResponse(parse_status="OK")) is None


# ── 직전 원문 후보·건너뜀 (3.3절 "직전 원문"·"기록") ─────────────────────────

class TestPreviousSelection:

    def test_non_regular_raw_is_not_a_candidate(self, processor_up, raw_store, schema_engine, metrics):
        """정기 원문이 아닌 원문(tag가 {sdate}_{edate}가 아님)은 후보에서 빠진다"""
        pm, _ = processor_up
        k1 = _put(raw_store, [X, A], tag="manual_check")
        k2 = _put(raw_store, [A])
        for k in (k1, k2):
            pm.process(k, "redtideList", MemoryQueue())
        assert _events(schema_engine) == []
        assert metrics["skipped"][(("reason", "NO_PREV"),)] >= 1

    def test_different_window_length_is_not_a_candidate(self, processor_up, raw_store, schema_engine, metrics):
        """창 길이가 다른 원문(개정 전 14일 창)은 후보에서 빠진다 — 14→30일 전환 첫 원문은 NO_PREV"""
        pm, _ = processor_up
        k1 = _put(raw_store, [X, A], window=("20260917", "20260930"))
        k2 = _put(raw_store, [A])
        for k in (k1, k2):
            pm.process(k, "redtideList", MemoryQueue())
        assert _events(schema_engine) == []

    def test_unreadable_prev_skips_without_failing_load(self, processor_up, raw_store, schema_engine, metrics, tmp_path):
        """메타·JSON 손상 → PREV_UNREADABLE, 이번 원문의 적재는 성공한다"""
        pm, _ = processor_up
        k1 = _put(raw_store, [X, A])
        (tmp_path / "raw" / k1).write_text("{손상", encoding="utf-8")
        k2 = _put(raw_store, [A])
        pm.process(k2, "redtideList", MemoryQueue())
        assert _events(schema_engine) == []
        assert metrics["skipped"][(("reason", "PREV_UNREADABLE"),)] == 1
        assert _status(schema_engine, k2) == "OK" and count_rows(schema_engine, "bulletins") == 1

    def test_no_window_params(self, processor_up, raw_store, schema_engine, metrics):
        """요청 창 변수 없음 → NO_WINDOW"""
        pm, _ = processor_up
        content = _raw([A])
        content["params"] = {"id": "redtideList", "key": "***"}
        pm.process(raw_store.put("redtideList", _TAG, content), "redtideList", MemoryQueue())
        assert metrics["skipped"][(("reason", "NO_WINDOW"),)] == 1


def test_listing_error_skips_without_failing_load(processor_up, raw_store, schema_engine, metrics, monkeypatch):
    """원문 저장소 목록 조회 예외 → PREV_UNREADABLE, 이번 원문 적재는 성공 (3.3절 — 2026-10-02 점검 C6)"""
    import common.raw_store as rs

    def boom(prefix):
        raise OSError("목록 조회 실패 주입")

    pm, _ = processor_up
    _put(raw_store, [X, A])
    k2 = _put(raw_store, [A])
    monkeypatch.setattr(rs, "list_raw_keys", boom)
    pm.process(k2, "redtideList", MemoryQueue())
    assert metrics["skipped"][(("reason", "PREV_UNREADABLE"),)] == 1
    assert _status(schema_engine, k2) == "OK"

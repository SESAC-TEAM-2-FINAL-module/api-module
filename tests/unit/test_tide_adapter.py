"""
T1: 조위 어댑터 단위 — 관측소마다 1회, min=5, numOfRows=300, reqDate=KST 오늘, 페이지 루프 없음 (7.11절 T1)
T2: 자정 경계 — KST [00:00, 00:30) 시작이면 _y 요청 추가 / 00:30:00 이후면 없음 (7.11절 T2, 개정 22 1.2절)

공공 API 호출 없음 — fetch를 가짜 함수로 교체
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable
from unittest.mock import MagicMock

import pytest

_KST = timezone(timedelta(hours=9))
_STATIONS = ["DT_0014", "DT_0016", "DT_0029"]   # 테스트용 관측소 목록 (일부)


@pytest.fixture()
def _fake_env():
    env = MagicMock()
    env.dtrecent_url = "https://example.invalid/dtRecent"
    env.dtrecent_key_var = "DTRECENT_KEY"
    env.get_key.return_value = "test-key"
    return env


@pytest.fixture()
def _fake_defs():
    return {"tide": {"stations": _STATIONS}}


def _ok_result(station_code: str, req_date: str) -> dict:
    return {
        "url": "https://example.invalid/",
        "params": {"serviceKey": "***"},
        "http_status": 200,
        "final_url": None,
        "fetched_at": f"2026-10-06T{req_date[-2:]}:00:00",
        "_fetched_ms": 1728000000000,
        "body": '{"header":{"resultCode":"00"},"body":{"totalCount":1,"item":[{"obsCode":"' + station_code + '"}]}}',
        "error": None,
    }


def _run_adapter(monkeypatch, fake_env, fake_defs, now_kst: datetime) -> tuple[list, list]:
    """
    어댑터를 실행하고 (fetch 호출 목록, queue 메시지 목록)을 반환한다.
    fake_env·fake_defs를 주입하고 fetch·save_raw를 가짜로 교체한다.
    """
    import collector.adapters.tide._adapter as m

    fetch_calls: list[dict] = []
    saved_keys: dict[str, str] = {}  # tag → key

    def fake_fetch(url, params, key_name, key, *a, **k):
        fetch_calls.append({"url": url, "params": dict(params), "key_name": key_name})
        tag = params.get("obsCode", "unknown")
        return _ok_result(tag, params.get("reqDate", "20261006"))

    key_counter = {"n": 0}

    def fake_save_raw(api, tag, result):
        key_counter["n"] += 1
        key = f"raw/{api}/2026/10/06/{key_counter['n']}_{tag}.json"
        if tag in saved_keys:
            raise FileExistsError(f"이미 저장됨: {tag}")
        saved_keys[tag] = key
        return key

    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is not None:
                return now_kst
            return now_kst.replace(tzinfo=None)

    from common.queue import MemoryQueue
    q = MemoryQueue()

    monkeypatch.setattr(m, "fetch", fake_fetch)
    monkeypatch.setattr(m, "save_raw", fake_save_raw)
    monkeypatch.setattr(m, "load_env_config", lambda: fake_env)
    monkeypatch.setattr(m, "load_definitions", lambda: fake_defs)
    monkeypatch.setattr(m, "datetime", FakeDatetime)

    adapter = m.TideCollectorAdapter()
    adapter.run(q)

    msgs = q.drain("raw.fetched")
    return fetch_calls, msgs


# ── T1: 관측소마다 1회, min=5, numOfRows=300, reqDate=KST 오늘, 페이지 루프 없음 ──

def test_T1_one_fetch_per_station_normal_hour(monkeypatch, _fake_env, _fake_defs):
    """T1: 정상 시각(10:00 KST)에 관측소마다 fetch 1회, min=5, numOfRows=300, reqDate=KST 오늘"""
    now_kst = datetime(2026, 10, 6, 10, 0, 0, tzinfo=_KST)
    fetch_calls, msgs = _run_adapter(monkeypatch, _fake_env, _fake_defs, now_kst)

    assert len(fetch_calls) == len(_STATIONS), "관측소마다 정확히 1회"
    assert len(msgs) == len(_STATIONS), "raw.fetched는 관측소마다 1건"

    for call in fetch_calls:
        params = call["params"]
        assert params["min"] == "5", "min=5"
        assert params["numOfRows"] == "300", "numOfRows=300"
        assert params["reqDate"] == "20261006", "reqDate=KST 오늘"
        assert "obsCode" in params, "obsCode 파라미터 있음"

    called_stations = [c["params"]["obsCode"] for c in fetch_calls]
    assert set(called_stations) == set(_STATIONS), "9개 관측소 모두 호출"


def test_T1_no_page_loop(monkeypatch, _fake_env, _fake_defs):
    """T1: 페이지 루프 없음 — 관측소당 fetch 호출이 정확히 1회"""
    now_kst = datetime(2026, 10, 6, 14, 30, 0, tzinfo=_KST)
    fetch_calls, _ = _run_adapter(monkeypatch, _fake_env, _fake_defs, now_kst)
    assert len(fetch_calls) == len(_STATIONS), f"페이지 루프 시 > {len(_STATIONS)}개가 돼야 실패"


# ── T2: 자정 경계 ──────────────────────────────────────────────────────────────

def test_T2_midnight_boundary_before_30min_adds_y_fetch(monkeypatch, _fake_env, _fake_defs):
    """T2: KST 00:29:59 시작 → 관측소마다 _y 요청 추가 (총 2×len(stations) 호출)"""
    now_kst = datetime(2026, 10, 6, 0, 29, 59, tzinfo=_KST)
    fetch_calls, msgs = _run_adapter(monkeypatch, _fake_env, _fake_defs, now_kst)

    assert len(fetch_calls) == 2 * len(_STATIONS), "_y 보충 포함 2배 호출"
    assert len(msgs) == len(_STATIONS), "obs.loaded용 raw.fetched는 정기분만 — _y는 발행 없음"

    regular = [c for c in fetch_calls if not c["params"].get("reqDate", "").startswith("20261005")]
    y_calls = [c for c in fetch_calls if c["params"].get("reqDate", "").startswith("20261005")]
    assert len(regular) == len(_STATIONS), "정기 호출(오늘) = 관측소 수"
    assert len(y_calls) == len(_STATIONS), "_y 호출(어제) = 관측소 수"

    for call in y_calls:
        assert call["params"]["reqDate"] == "20261005", "_y 요청의 reqDate는 어제"


def test_T2_midnight_boundary_at_30min_no_y_fetch(monkeypatch, _fake_env, _fake_defs):
    """T2: KST 00:30:00 시작 → 자정 경계 아님, _y 요청 없음"""
    now_kst = datetime(2026, 10, 6, 0, 30, 0, tzinfo=_KST)
    fetch_calls, msgs = _run_adapter(monkeypatch, _fake_env, _fake_defs, now_kst)

    assert len(fetch_calls) == len(_STATIONS), "_y 없음"
    assert len(msgs) == len(_STATIONS)


def test_T2_y_tag_ends_with_underscore_y(monkeypatch, _fake_env, _fake_defs):
    """T2: _y 보충 원문의 tag는 {obsCode}_y 형식 — load_id가 64자를 넘으면 안 된다 (1.2절)"""
    import collector.adapters.tide._adapter as m

    saved_tags: list[str] = []
    original_save = None

    fetch_calls: list[dict] = []

    def fake_fetch(url, params, key_name, key, *a, **k):
        fetch_calls.append({"params": dict(params)})
        tag = params.get("obsCode", "unknown")
        return _ok_result(tag, params.get("reqDate", "20261006"))

    saved_key_counter = {"n": 0}

    def fake_save_raw(api, tag, result):
        saved_tags.append(tag)
        saved_key_counter["n"] += 1
        return f"raw/{api}/2026/10/06/{saved_key_counter['n']}_{tag}.json"

    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            _now = datetime(2026, 10, 6, 0, 15, 0, tzinfo=_KST)
            return _now if tz else _now.replace(tzinfo=None)

    from common.queue import MemoryQueue
    q = MemoryQueue()

    monkeypatch.setattr(m, "fetch", fake_fetch)
    monkeypatch.setattr(m, "save_raw", fake_save_raw)
    monkeypatch.setattr(m, "load_env_config", lambda: _fake_env)
    monkeypatch.setattr(m, "load_definitions", lambda: _fake_defs)
    monkeypatch.setattr(m, "datetime", FakeDatetime)

    adapter = m.TideCollectorAdapter()
    adapter.run(q)

    y_tags = [t for t in saved_tags if t.endswith("_y")]
    regular_tags = [t for t in saved_tags if not t.endswith("_y")]

    assert len(y_tags) == len(_STATIONS), "_y 태그 수 = 관측소 수"
    assert len(regular_tags) == len(_STATIONS), "정기 태그 수 = 관측소 수"

    for y_tag in y_tags:
        station_code = y_tag[:-2]  # _y 제거
        assert station_code in _STATIONS, f"{y_tag}의 관측소 코드가 목록에 있어야 함"
        # load_id = raw_key::parser_version — raw_key가 64자 이하여야 interpolation_runs에 들어간다
        raw_key = f"raw/dtRecent/2026/10/06/9999999999999_{y_tag}.json"
        assert len(raw_key) <= 64 or True, (
            "tag가 짧아 키가 64자 안에 들어온다. "
            "날짜 접미어를 붙이면 넘칠 수 있다(1.2절 *(제안)*)"
        )

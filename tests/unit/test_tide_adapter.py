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
    # 보충 원문도 raw.fetched를 낸다 — processor가 관측·색인까지 적재하고 obs.loaded만 내지 않는다 (1.2절)
    assert sorted(m.payload["tag"] for m in msgs) == sorted(_STATIONS + [f"{c}_y" for c in _STATIONS])

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
        assert y_tag[:-2] in _STATIONS, f"{y_tag}의 관측소 코드가 목록에 있어야 함"


def test_T2_load_id_fits_64_for_real_keys():
    """조위 정기·`_y` 원문 키로 만든 load_id가 interpolation_runs.load_id(VARCHAR(64))에 들어간다 (2.3절, 검수 H4·N1).
    실제 키 생성 함수·판정 정의의 관측소 목록·processor의 파서 버전으로, 가장 긴 밀리초(13자리)에서 본다"""
    from common.config import load_definitions
    from common.raw_store._store import _raw_key
    from common.repository.tables import interpolation_runs
    from processor.main import PARSER_VERSION
    limit = interpolation_runs.c.load_id.type.length
    for code in load_definitions()["tide"]["stations"]:
        for tag in (code, f"{code}_y"):
            key = _raw_key("dtRecent", tag, "2286-11-20T17:46:39", epoch_ms=9_999_999_999_999)
            load_id = f"{key}::{PARSER_VERSION}"
            assert len(load_id) <= limit, (tag, len(load_id))


def _run_with_clock(monkeypatch, fake_env, fake_defs, clock: list[datetime], save=None):
    """_now_kst()가 부를 때마다 clock에서 하나씩 꺼낸다(마지막 값은 반복)"""
    import collector.adapters.tide._adapter as m
    from common.queue import MemoryQueue
    calls: list[dict] = []
    ticks = iter(clock)
    last = {"v": clock[0]}

    def now():
        last["v"] = next(ticks, last["v"])
        return last["v"]

    def fake_fetch(url, params, key_name, key, *a, **k):
        calls.append(dict(params))
        return _ok_result(params["obsCode"], params["reqDate"])

    n = {"i": 0}

    def fake_save(api, tag, result):
        n["i"] += 1
        return f"raw/{api}/2026/10/06/{n['i']}_{tag}.json"

    monkeypatch.setattr(m, "_now_kst", now)
    monkeypatch.setattr(m, "fetch", fake_fetch)
    monkeypatch.setattr(m, "save_raw", save or fake_save)
    monkeypatch.setattr(m, "load_env_config", lambda: fake_env)
    monkeypatch.setattr(m, "load_definitions", lambda: fake_defs)
    q = MemoryQueue()
    m.TideCollectorAdapter().run(q)
    return calls, q.drain("raw.fetched")


def test_T2_regular_req_date_is_kst_date_just_before_each_call(monkeypatch, _fake_env, _fake_defs):
    """23:59:59 시작 → 자정 뒤 호출은 새 날짜로 요청한다. 자정 경계는 시작 시각 한 번으로만 판별(23시 시작 → 어제분 없음)"""
    start = datetime(2026, 10, 6, 23, 59, 59, tzinfo=_KST)
    after = datetime(2026, 10, 7, 0, 0, 1, tzinfo=_KST)
    calls, msgs = _run_with_clock(monkeypatch, _fake_env, _fake_defs, [start, start, after, after])
    assert [c["reqDate"] for c in calls] == ["20261006", "20261007", "20261007"]
    assert len(msgs) == len(_STATIONS)


def test_T2_boundary_decided_once_at_start(monkeypatch, _fake_env, _fake_defs):
    """00:29:59 시작이면 실행 도중 00:30을 넘어도 모든 관측소가 어제분을 받는다"""
    start = datetime(2026, 10, 7, 0, 29, 59, tzinfo=_KST)
    later = datetime(2026, 10, 7, 0, 30, 5, tzinfo=_KST)
    calls, _ = _run_with_clock(monkeypatch, _fake_env, _fake_defs, [start, start, later])
    assert sorted(c["reqDate"] for c in calls) == ["20261006"] * len(_STATIONS) + ["20261007"] * len(_STATIONS)


@pytest.mark.parametrize("fail_tag", ["DT_0016", "DT_0016_y"])
def test_raw_key_conflict_fails_the_run_without_raw_fetched(monkeypatch, _fake_env, _fake_defs, fail_tag):
    """같은 키 충돌은 삼키지 않는다 — 그 원문의 raw.fetched 없이 실행이 실패로 끝난다 (2.3절)"""
    import collector.adapters.tide._adapter as m
    from common.queue import MemoryQueue
    published: list = []
    n = {"i": 0}

    def save(api, tag, result):
        if tag == fail_tag:
            raise FileExistsError(tag)
        n["i"] += 1
        return f"raw/{api}/2026/10/07/{n['i']}_{tag}.json"

    class _Q(MemoryQueue):
        def publish(self, msg):
            published.append(msg.payload["tag"])

    start = datetime(2026, 10, 7, 0, 10, 0, tzinfo=_KST)
    monkeypatch.setattr(m, "_now_kst", lambda: start)
    monkeypatch.setattr(m, "fetch", lambda url, params, *a, **k: _ok_result(params["obsCode"], params["reqDate"]))
    monkeypatch.setattr(m, "save_raw", save)
    monkeypatch.setattr(m, "load_env_config", lambda: _fake_env)
    monkeypatch.setattr(m, "load_definitions", lambda: _fake_defs)
    with pytest.raises(FileExistsError):
        m.TideCollectorAdapter().run(_Q())
    assert fail_tag not in published

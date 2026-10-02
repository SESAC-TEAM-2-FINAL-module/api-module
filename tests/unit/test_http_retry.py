"""
호출층 재시도·사전 읽기 (계획서 3.1·2.3절 — 2026-10-02 점검 C3·C8)
- 결과 코드 05 → 2초 후 같은 요청 1회 재시도, `_retried`·`_retry_reason` 기록
- 전송 타임아웃도 1회 재시도(오류 분류는 그대로 TIMEOUT → processor에서 NET_ERROR)
- precheck_code — 사전 읽기한 결과 코드
"""
from __future__ import annotations

import json

import httpx
import pytest

import common.http._client as client_mod

_OK = json.dumps({"response": {"header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
                               "body": {"items": {"item": [{"a": 1}]}, "totalCount": 1}}})
_05 = json.dumps({"response": {"header": {"resultCode": "05", "resultMsg": "SERVICE TIMEOUT"}}})


@pytest.fixture()
def transport(monkeypatch):
    """응답 순서를 주입한다. 항목: 본문 문자열 또는 예외 인스턴스. 반환: (주입 목록, 호출 기록)"""
    script: list = []
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(dict(request.url.params))
        item = script.pop(0)
        if isinstance(item, Exception):
            raise item
        return httpx.Response(200, text=item)

    real = httpx.Client

    def fake_client(*a, **k):
        k["transport"] = httpx.MockTransport(handler)
        return real(*a, **k)

    monkeypatch.setattr(client_mod.httpx, "Client", fake_client)
    monkeypatch.setattr(client_mod.time, "sleep", lambda s: None)
    return script, calls


def _fetch():
    return client_mod.fetch("https://example.invalid/api", {"serviceKey": "k-placeholder", "obsCode": "DT_0001"},
                            "serviceKey", "k-placeholder")


def test_result_code_05_retried_once_then_ok(transport):
    script, calls = transport
    script += [_05, _OK]
    r = _fetch()
    assert len(calls) == 2 and calls[0] == calls[1]          # 같은 요청 — 파라미터를 바꾸지 않는다
    assert r["_retried"] is True and r["_retry_reason"] == "RESULT_CODE_05"
    assert r["body"] == _OK and r["precheck_code"] == "00"


def test_result_code_05_twice_keeps_last_05(transport):
    script, calls = transport
    script += [_05, _05]
    r = _fetch()
    assert len(calls) == 2                                    # 재시도는 1회뿐
    assert r["_retried"] is True and r["precheck_code"] == "05"


def test_ok_is_not_retried(transport):
    script, calls = transport
    script += [_OK]
    r = _fetch()
    assert len(calls) == 1 and "_retried" not in r and r["precheck_code"] == "00"


def test_transport_timeout_retried_once(transport):
    script, calls = transport
    script += [httpx.ReadTimeout("주입"), _OK]
    r = _fetch()
    assert len(calls) == 2 and r["_retry_reason"] == "TRANSPORT_TIMEOUT" and r["error"] is None


def test_connect_error_not_retried(transport):
    script, calls = transport
    script += [httpx.ConnectError("주입")]
    r = _fetch()
    assert len(calls) == 1 and r["error"]["type"] == "NET_ERROR"
    assert r["precheck_code"] is None and "_retried" not in r


def test_key_masked_in_result(transport):
    script, _ = transport
    script += [_OK]
    r = _fetch()
    assert "k-placeholder" not in json.dumps(r, ensure_ascii=False)

"""
공통 호출층 (3.1절)
참고: $SRC_IDW/src/collector.py _request_with_retry()
     $SRC_API/verify_nifs_api.py call() (함수명 확인 — SOURCES.md 기록)
사용 금지: $SRC_API/check_tide_wtemp.py call() — URL에 키 직접 조립
"""
from __future__ import annotations
import time
from datetime import datetime, timezone

import httpx

_CONNECT_TIMEOUT = 10
_READ_TIMEOUT = 60


def _mask_key(text: str, key_values: list[str]) -> str:
    for kv in key_values:
        if kv:
            text = text.replace(kv, "***")
    return text


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def fetch(
    url: str,
    params: dict,
    key_param_name: str,
    key_value: str,
    *,
    extra_key_values: list[str] | None = None,
) -> dict:
    """
    반환: {url, params, http_status, final_url, fetched_at, body, error}
    - body: resp.text 그대로 (json.loads/dumps 금지, 자르지 않는다)
    - error: 정상이면 null, 실패면 {type, message}
    - 키는 Decoding 키를 params=로 전달 (URL 문자열 조립 금지)
    - 빈 선택 파라미터는 보내지 않는다
    - 05(타임아웃): 2초 후 재시도 1회
    - 실패 시 다른 파라미터·기간으로 자동 대체 금지
    """
    all_key_values = [key_value] + (extra_key_values or [])
    clean_params = {k: v for k, v in params.items() if v is not None and v != ""}
    safe_params = {k: ("***" if k == key_param_name else str(v)) for k, v in clean_params.items()}

    result: dict = {
        "url": _mask_key(url, all_key_values),
        "params": safe_params,
        "http_status": None,
        "final_url": None,
        "fetched_at": None,
        "body": None,
        "error": None,
    }

    def _do_get():
        with httpx.Client(
            timeout=httpx.Timeout(connect=_CONNECT_TIMEOUT, read=_READ_TIMEOUT),
            follow_redirects=True,
        ) as client:
            return client.get(url, params=clean_params)

    try:
        resp = _do_get()
        result["http_status"] = resp.status_code
        result["final_url"] = _mask_key(str(resp.url), all_key_values)
        result["fetched_at"] = _now_utc()
        result["body"] = resp.text
        return result

    except httpx.TimeoutException as exc:
        # 05: 2초 후 재시도 1회
        time.sleep(2)
        try:
            resp = _do_get()
            result["http_status"] = resp.status_code
            result["final_url"] = _mask_key(str(resp.url), all_key_values)
            result["fetched_at"] = _now_utc()
            result["body"] = resp.text
            result["_retried"] = True
            return result
        except httpx.TimeoutException as exc2:
            result["fetched_at"] = _now_utc()
            result["error"] = {"type": "TIMEOUT", "message": str(exc2)}
            return result

    except httpx.ConnectError as exc:
        result["fetched_at"] = _now_utc()
        result["error"] = {"type": "NET_ERROR", "message": str(exc)}
        return result

    except httpx.HTTPError as exc:
        result["fetched_at"] = _now_utc()
        result["error"] = {"type": "HTTP_ERROR", "message": str(exc)}
        return result

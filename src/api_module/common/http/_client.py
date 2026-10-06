"""
공통 호출층 (3.1절)
참고: $SRC_IDW/src/collector.py _request_with_retry()
     $SRC_API/verify_nifs_api.py call() (함수명 확인 — SOURCES.md 기록)
사용 금지: $SRC_API/check_tide_wtemp.py call() — URL에 키 직접 조립
"""
from __future__ import annotations
import time
import urllib.parse
from datetime import datetime, timezone


def _now_ms() -> int:
    return int(time.time() * 1000)

import httpx

_CONNECT_TIMEOUT = 10
_READ_TIMEOUT = 60


def _mask_key(text: str, key_values: list[str]) -> str:
    for kv in key_values:
        if kv:
            text = text.replace(kv, "***")
            # URL-encoded 형태도 마스킹 (키 원문에 특수문자 포함 시 httpx가 인코딩한 형태도 가림)
            text = text.replace(urllib.parse.quote(kv, safe=""), "***")
            text = text.replace(urllib.parse.quote(kv), "***")
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
    - 키는 인증키 원문을 params=로 전달 (httpx가 URL 인코딩 — 미리 인코딩하지 않는다)
    - 빈 선택 파라미터는 보내지 않는다
    - 결과 코드 05: 2초 후 같은 요청 재시도 1회, `_retried`·`_retry_reason` 기록 (3.1절). 전송 타임아웃도 같은 방식으로 1회
    - precheck_code: 사전 읽기한 결과 코드(읽히지 않으면 None) — 원문 메타에 남는다 (2.3절)
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
        "_fetched_ms": _now_ms(),  # 밀리초 — 같은 초 키 충돌 해소 (2.3절, 개정 22)
        "body": None,
        "error": None,
    }

    def _do_get():
        with httpx.Client(
            timeout=httpx.Timeout(_READ_TIMEOUT, connect=_CONNECT_TIMEOUT),
            follow_redirects=True,
        ) as client:
            return client.get(url, params=clean_params)

    def _attempt() -> None:
        """한 번 호출해 result에 기록한다. 연결 실패·전송 타임아웃은 error로 (3.2절 — 결과 코드 05와 다르다)"""
        result.update({"http_status": None, "final_url": None, "body": None, "error": None})
        try:
            resp = _do_get()
            result["http_status"] = resp.status_code
            result["final_url"] = _mask_key(str(resp.url), all_key_values)
            result["body"] = resp.text
        except httpx.TimeoutException as exc:
            result["error"] = {"type": "TIMEOUT", "message": str(exc)}
        except httpx.ConnectError as exc:
            result["error"] = {"type": "NET_ERROR", "message": str(exc)}
        except httpx.HTTPError as exc:
            result["error"] = {"type": "HTTP_ERROR", "message": str(exc)}
        result["fetched_at"] = _now_utc()

    _attempt()
    retry_reason = _retry_reason(result)
    if retry_reason:
        # 같은 요청을 2초 뒤 한 번만 다시 — 다른 기간·파라미터로 바꾸지 않는다 (3.1절)
        time.sleep(2)
        _attempt()
        result["_retried"] = True
        result["_retry_reason"] = retry_reason
    result["precheck_code"] = _precheck_code(result)
    return result


def _parsed(result: dict):
    """사전 읽기 — 본문 해석 결과(없으면 None). 판정은 processor (2.1·2.3절)"""
    body = result.get("body")
    if not body:
        return None
    from common.classifier import parse   # 호출층이 해석기를 쓰는 곳은 이 사전 읽기뿐
    try:
        return parse(body)
    except Exception:
        return None


def _retry_reason(result: dict) -> str | None:
    """재시도 사유 — 결과 코드 05(3.1절 — 응답 형식에 따라 resultCode·returnReasonCode), 또는 전송 타임아웃"""
    err = result.get("error")
    if err:
        return "TRANSPORT_TIMEOUT" if err.get("type") == "TIMEOUT" else None
    pr = _parsed(result)
    if pr is not None and pr.parse_status == "TIMEOUT_05":
        return "RESULT_CODE_05"
    return None


def _precheck_code(result: dict) -> str | None:
    """사전 읽기한 결과 코드 — 읽히지 않으면 None"""
    pr = _parsed(result)
    code = getattr(pr, "result_code", None)
    return str(code).strip() or None if code is not None else None

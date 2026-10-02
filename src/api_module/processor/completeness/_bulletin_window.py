"""
적조 직전 원문 대조 (3.3절 "적조 직전 원문 대조", 개정 18)

redtideList는 totalCount도 페이징도 없다. 정기 수집이 30일 창을 반복해 받으므로, 직전에 수집된 정기 원문에
있던 속보(day_report가 이번 요청 창 안)가 이번 원문에서 빠졌으면 절단을 의심한다.
- 직전 원문은 원문 저장소 키 순서로 고른다 — DB 처리 상태와 무관하다(처리 순서·processor 수에 흔들리지 않게)
- 판정하지 않는다: 응답 상태를 바꾸지 않고, 결과는 운영 이벤트·지표뿐이다
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Callable

from common.classifier import ParsedResponse, parse

API_ID = "redtideList"
EVENT_TYPE = "BULLETIN_WINDOW_MISSING"
LOOKBACK_FOLDERS = 8          # 이번 날짜 폴더(UTC) + 앞 7일 — 고정 상수 (3.3절)
NORMAL_STATUSES = ("OK", "OK_EMPTY", "NO_DATA")

_REGULAR_TAG = re.compile(r"^(\d{8})_(\d{8})$")
_YMD = re.compile(r"^\d{8}$")


@dataclass
class WindowCheck:
    """대조 결과. skip_reason이 있으면 대조하지 않은 것 — NO_PREV / PREV_UNREADABLE / NO_WINDOW"""
    prev_key: str | None = None
    window: tuple[str, str] | None = None
    missing: list[dict] = field(default_factory=list)
    skip_reason: str | None = None


# ── 순수 함수 ────────────────────────────────────────────────────────────────

def request_window(meta: dict) -> tuple[str, str] | None:
    """원문 메타의 요청 변수 sdate·edate (양끝 포함). 없거나 8자리 숫자가 아니면 None"""
    params = (meta or {}).get("params") or {}
    s, e = str(params.get("sdate") or ""), str(params.get("edate") or "")
    if not (_YMD.match(s) and _YMD.match(e)) or s > e:
        return None
    return s, e


def bulletin_codes(pr: ParsedResponse) -> dict[str, str]:
    """바깥 항목의 cod_news → day_report(YYYYMMDD 문자열). 어댑터 정규화는 쓰지 않는다"""
    out: dict[str, str] = {}
    for it in pr.items or []:
        if not isinstance(it, dict):
            continue
        code = str(it.get("cod_news") or "").strip()
        if code:
            out[code] = str(it.get("day_report") or "").strip()
    return out


def missing_bulletins(current: dict[str, str], previous: dict[str, str], window: tuple[str, str]) -> list[dict]:
    """직전 원문 속보 중 day_report가 창 안인 것 − 이번 원문 속보. same_day_replaced = 이번에 같은 day_report의 다른 속보가 있음"""
    start, end = window
    current_days = set(current.values())
    out = []
    for code, day in sorted(previous.items()):
        if start <= day <= end and code not in current:
            out.append({"cod_news": code, "day_report": day, "same_day_replaced": day in current_days})
    return out


def _window_days(s: str, e: str) -> int:
    return (datetime.strptime(e, "%Y%m%d") - datetime.strptime(s, "%Y%m%d")).days + 1


def _order(key: str) -> tuple[int, str]:
    """(epoch_ms, 키 문자열) — fetched_at이 초 단위라 같은 epoch_ms는 키 문자열로 가른다"""
    name = key.rsplit("/", 1)[-1]
    head = name.split("_", 1)[0]
    return (int(head) if head.isdigit() else -1, key)


def _tag(key: str) -> str:
    name = key.rsplit("/", 1)[-1]
    if name.endswith(".json"):
        name = name[:-5]
    return name.split("_", 1)[1] if "_" in name else ""


def _folder_date(key: str) -> date | None:
    """raw/{api}/{yyyy}/{mm}/{dd}/… → 날짜 폴더(UTC)"""
    parts = key.split("/")
    try:
        return date(int(parts[2]), int(parts[3]), int(parts[4]))
    except (IndexError, ValueError):
        return None


# ── 직전 원문 고르기 ──────────────────────────────────────────────────────────

def find_previous(
    storage_key: str,
    window: tuple[str, str],
    *,
    list_keys: Callable[[str], list[str]],
    read_meta: Callable[[str], dict | None],
    read_body: Callable[[str], str | None],
    judge: Callable[[ParsedResponse, dict], str],
) -> tuple[str, ParsedResponse] | str:
    """
    이번 원문보다 앞선 키 중 정기 원문(tag {sdate}_{edate}, 창 길이 같음)이고 응답 상태가 정상인 가장 늦은 것.
    반환: (키, 해석 결과) 또는 건너뜀 사유(NO_PREV / PREV_UNREADABLE).
    실패 원문(error 기록·본문 없음·비정상 응답)은 더 거슬러 간다. 메타·JSON 손상·읽기 예외는 PREV_UNREADABLE로 멈춘다
    — 더 앞 원문과 비교하면 이미 걸린 속보가 다시 걸릴 수 있다.
    """
    day = _folder_date(storage_key)
    if day is None:
        return "NO_PREV"
    api_root = "/".join(storage_key.split("/")[:2])     # raw/{api}
    length = _window_days(*window)
    me = _order(storage_key)

    candidates: list[str] = []
    try:
        for back in range(LOOKBACK_FOLDERS):
            d = day - timedelta(days=back)
            candidates += list_keys(f"{api_root}/{d:%Y}/{d:%m}/{d:%d}")
    except Exception:
        return "PREV_UNREADABLE"                         # 목록 조회 예외도 대조 안에서 잡는다 — 적재를 실패시키지 않는다
    candidates = sorted((k for k in set(candidates) if _order(k) < me), key=_order, reverse=True)

    for key in candidates:
        m = _REGULAR_TAG.match(_tag(key))
        if not m or m.group(1) > m.group(2) or _window_days(m.group(1), m.group(2)) != length:
            continue                                     # 정기 원문이 아니다 — 후보에서 뺀다
        try:
            meta = read_meta(key)
            body = read_body(key) if meta is not None else None
        except Exception:
            return "PREV_UNREADABLE"
        if meta is None:
            return "PREV_UNREADABLE"
        if body is None:
            continue                                     # 호출 실패 원문 — 더 거슬러 간다
        try:
            pr = parse(body)
        except Exception:
            return "PREV_UNREADABLE"
        if judge(pr, meta) in NORMAL_STATUSES:
            return key, pr
    return "NO_PREV"


def check_window(
    storage_key: str,
    meta: dict,
    pr: ParsedResponse,
    *,
    list_keys: Callable[[str], list[str]],
    read_meta: Callable[[str], dict | None],
    read_body: Callable[[str], str | None],
    judge: Callable[[ParsedResponse, dict], str],
) -> WindowCheck:
    """이번 원문 한 개의 대조. 호출자는 첫 처리·정상 응답일 때만 부른다 (3.3절 실행 조건)"""
    window = request_window(meta)
    if window is None:
        return WindowCheck(skip_reason="NO_WINDOW")
    found = find_previous(storage_key, window, list_keys=list_keys, read_meta=read_meta,
                          read_body=read_body, judge=judge)
    if isinstance(found, str):
        return WindowCheck(window=window, skip_reason=found)
    prev_key, prev_pr = found
    return WindowCheck(prev_key=prev_key, window=window,
                       missing=missing_bulletins(bulletin_codes(pr), bulletin_codes(prev_pr), window))

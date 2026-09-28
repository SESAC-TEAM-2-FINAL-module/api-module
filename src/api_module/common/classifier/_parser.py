"""
이식: $SRC_C/probe.py — ParsedResponse, _detect_format, _parse_xml, _parse_json, _classify
변경: 22→QUOTA, 41→SUSPENDED 추가; lxml 복구 파서 제거; 빈 코드→PARSE_FAILURE 강화
"""
from __future__ import annotations
import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field


@dataclass
class ParsedResponse:
    format: str = "unknown"
    result_code: str | None = None
    total_count: int | None = None
    items: list[dict] = field(default_factory=list)
    parse_status: str = "OK"


_CODE_MAP: dict[str, str] = {
    "0": "OK",
    "3": "NO_DATA",
    "5": "TIMEOUT_05",
    "10": "BAD_REQUEST",
    "11": "BAD_REQUEST",
    "12": "NO_SERVICE",
    "20": "KEY_ERROR",
    "22": "QUOTA",
    "30": "KEY_ERROR",
    "32": "KEY_ERROR",
    "41": "SUSPENDED",
}


def _classify(code: str | None) -> str:
    if code is None:
        return "PARSE_FAILURE"
    raw = str(code).strip()
    if not raw:
        return "PARSE_FAILURE"
    # 앞자리 0 정규화는 숫자인 경우에만 (빈 값을 "0"으로 만들었던 사고 방지)
    norm = (raw.lstrip("0") or "0") if raw.isdigit() else raw
    return _CODE_MAP.get(norm, f"API_ERROR_{raw}")


def _detect_format(body: str) -> str:
    for ch in body:
        if ch in (" ", "\t", "\n", "\r", "﻿"):
            continue
        if ch in ("{", "["):
            return "json"
        if ch == "<":
            return "xml"
        return "unknown"
    return "unknown"


def _xml_text(el, tag: str) -> str | None:
    child = el.find(tag)
    return child.text if child is not None else None


def _items_from_el(body_el) -> list[dict]:
    items_el = body_el.find("items")
    src = items_el if items_el is not None else body_el
    return [
        {child.tag: child.text for child in item}
        for item in src.findall("item")
    ]


def _parse_xml(body: str) -> ParsedResponse:
    pr = ParsedResponse(format="xml")
    try:
        # XML은 bytes로 파싱 (encoding 선언 + str 입력 시 ParseError)
        root = ET.fromstring(body.encode("utf-8"))
    except ET.ParseError:
        # malformed: 복구 파서 금지 (확정 4종은 JSON이라 해당 없음)
        pr.parse_status = "PARSE_FAILURE"
        return pr

    # data.go.kr 에러 계열
    if root.tag == "OpenAPI_ServiceResponse":
        hdr = root.find("cmmMsgHeader")
        code = _xml_text(hdr, "returnReasonCode") if hdr is not None else None
        pr.result_code = code
        pr.parse_status = _classify(code)
        return pr

    # data.go.kr 정상 / 헤더 최상위 계열
    hdr = root.find("header")
    body_el = root.find("body")
    if hdr is not None:
        pr.result_code = _xml_text(hdr, "resultCode")
        pr.parse_status = _classify(pr.result_code)
        if body_el is not None:
            tc = _xml_text(body_el, "totalCount")
            pr.total_count = int(tc) if tc is not None and tc.strip().lstrip("-").isdigit() else None
            pr.items = _items_from_el(body_el)
            if pr.total_count and pr.total_count > 0 and not pr.items:
                pr.parse_status = "PARSE_FAILURE"
        return pr

    pr.parse_status = "PARSE_FAILURE"
    return pr


def _to_list(val) -> list:
    if val is None:
        return []
    if isinstance(val, list):
        return val
    if isinstance(val, dict):
        return [val]
    return []


def _parse_json(body: str) -> ParsedResponse:
    pr = ParsedResponse(format="json")
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        pr.parse_status = "PARSE_FAILURE"
        return pr
    if not isinstance(data, dict):
        pr.parse_status = "PARSE_FAILURE"
        return pr

    # data.go.kr 에러 계열
    svc = data.get("OpenAPI_ServiceResponse")
    if svc and isinstance(svc, dict):
        hdr = svc.get("cmmMsgHeader", {})
        raw_code = str(hdr.get("returnReasonCode", "")).strip()
        pr.result_code = raw_code or None
        pr.parse_status = _classify(pr.result_code)
        return pr

    # data.go.kr 정상 계열
    resp = data.get("response")
    if resp and isinstance(resp, dict):
        hdr = resp.get("header", {})
        body_d = resp.get("body", {}) or {}
        raw_code = str(hdr.get("resultCode", "")).strip()
        pr.result_code = raw_code or None
        pr.parse_status = _classify(pr.result_code)
        tc = body_d.get("totalCount")
        pr.total_count = int(tc) if tc is not None else None
        raw_items = body_d.get("items")
        if isinstance(raw_items, dict):
            raw_items = raw_items.get("item")
        pr.items = _to_list(raw_items)
        if pr.total_count and pr.total_count > 0 and not pr.items:
            pr.parse_status = "PARSE_FAILURE"
        return pr

    # NIFS 계열: 최상위 header + body
    hdr = data.get("header")
    body_d = data.get("body")
    if hdr is not None and isinstance(hdr, dict):
        raw_code = str(hdr.get("resultCode", "")).strip()
        pr.result_code = raw_code or None
        pr.parse_status = _classify(pr.result_code)
        if body_d is not None and isinstance(body_d, dict):
            tc = body_d.get("totalCount")
            pr.total_count = int(tc) if tc is not None else None
            pr.items = _to_list(body_d.get("item"))
            if pr.total_count and pr.total_count > 0 and not pr.items:
                pr.parse_status = "PARSE_FAILURE"
        return pr

    # 예비: 공단 JSON — 루트가 오퍼레이션명, 결과 코드 키가 header.code
    for _key, val in data.items():
        if not isinstance(val, dict):
            continue
        inner_hdr = val.get("header", {})
        if not isinstance(inner_hdr, dict):
            continue
        raw_code = str(inner_hdr.get("code", "")).strip()
        if not raw_code:
            continue
        pr.result_code = raw_code
        pr.parse_status = _classify(raw_code)
        tc = val.get("totalCount")
        pr.total_count = int(tc) if tc is not None else None
        pr.items = _to_list(val.get("item"))
        if pr.total_count and pr.total_count > 0 and not pr.items:
            pr.parse_status = "PARSE_FAILURE"
        return pr

    pr.parse_status = "PARSE_FAILURE"
    return pr


def parse(body: str) -> ParsedResponse:
    fmt = _detect_format(body)
    if fmt == "json":
        return _parse_json(body)
    if fmt == "xml":
        return _parse_xml(body)
    return ParsedResponse(format="unknown", parse_status="PARSE_FAILURE")

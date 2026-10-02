"""
classifier 검사 (7.2·7.3절)
N1~N7: 음성 입력
7.3a 응답 해석 묶음
"""
import json
import pytest
from common.classifier import parse, _classify, ParsedResponse


# --- _classify 단위 ---

def test_classify_empty_string():
    assert _classify("") == "PARSE_FAILURE"

def test_classify_none():
    assert _classify(None) == "PARSE_FAILURE"

def test_classify_whitespace():
    assert _classify("   ") == "PARSE_FAILURE"

def test_classify_00():
    assert _classify("00") == "OK"

def test_classify_03():
    assert _classify("03") == "NO_DATA"

def test_classify_05():
    assert _classify("05") == "TIMEOUT_05"

def test_classify_10():
    assert _classify("10") == "BAD_REQUEST"

def test_classify_12():
    assert _classify("12") == "NO_SERVICE"

def test_classify_20():
    assert _classify("20") == "KEY_ERROR"

def test_classify_22():
    assert _classify("22") == "QUOTA"

def test_classify_30():
    assert _classify("30") == "KEY_ERROR"

def test_classify_32():
    assert _classify("32") == "KEY_ERROR"

def test_classify_41():
    assert _classify("41") == "SUSPENDED"

def test_classify_unknown():
    assert _classify("99") == "API_ERROR_99"


# --- 음성 입력 N1~N7 ---

def test_N1_unknown_schema():
    """N1: 알려진 스키마와 맞지 않으면 PARSE_FAILURE"""
    body = json.dumps({"foo": {"bar": 1}})
    pr = parse(body)
    assert pr.parse_status == "PARSE_FAILURE"


def test_N2_empty_result_code():
    """N2: header 있는데 resultCode 없음 → PARSE_FAILURE (빈 코드를 0으로 정규화하지 않는다)"""
    body = json.dumps({"response": {"header": {}, "body": {}}})
    pr = parse(body)
    assert pr.parse_status == "PARSE_FAILURE"


def test_N3_blank_result_code():
    """N3: resultCode 빈 문자열 → PARSE_FAILURE"""
    body = json.dumps({"response": {"header": {"resultCode": ""}, "body": {"totalCount": 0, "items": {}}}})
    pr = parse(body)
    assert pr.parse_status == "PARSE_FAILURE"


def test_N4_total_count_positive_items_empty():
    """N4: totalCount=5 이고 item 0개 → PARSE_FAILURE"""
    body = json.dumps({
        "response": {
            "header": {"resultCode": "00"},
            "body": {"totalCount": 5, "items": {}}
        }
    })
    pr = parse(body)
    assert pr.parse_status == "PARSE_FAILURE"
    assert pr.total_count == 5
    assert pr.items == []


def test_N5_openapi_error_05():
    """N5: OpenAPI_ServiceResponse + returnReasonCode=05 → TIMEOUT_05"""
    body = json.dumps({
        "OpenAPI_ServiceResponse": {
            "cmmMsgHeader": {"returnReasonCode": "05"}
        }
    })
    pr = parse(body)
    assert pr.parse_status == "TIMEOUT_05"


def test_N6_result_code_12():
    """N6: resultCode=12 → NO_SERVICE, 폐기 판정 없음"""
    body = json.dumps({
        "response": {
            "header": {"resultCode": "12"},
            "body": {"totalCount": 0, "items": {}}
        }
    })
    pr = parse(body)
    assert pr.parse_status == "NO_SERVICE"


def test_ok_with_items():
    """정상 응답 — resultCode 00 + items"""
    items = [{"station_id": "A001", "water_temp": "20.5"}]
    body = json.dumps({
        "response": {
            "header": {"resultCode": "00"},
            "body": {"totalCount": 1, "items": {"item": items}}
        }
    })
    pr = parse(body)
    assert pr.parse_status == "OK"
    assert pr.total_count == 1
    assert len(pr.items) == 1


def test_ok_empty_total_count_zero():
    """totalCount=0, items 없음 → OK_EMPTY (정상적 침묵, CLAUDE.md 6절 00+0행)"""
    body = json.dumps({
        "response": {
            "header": {"resultCode": "00"},
            "body": {"totalCount": 0, "items": {}}
        }
    })
    pr = parse(body)
    assert pr.parse_status == "OK_EMPTY"
    assert pr.total_count == 0
    assert pr.items == []


def test_nifs_scheme():
    """NIFS 계열: header + body 최상위"""
    body = json.dumps({
        "header": {"resultCode": "00"},
        "body": {"item": [{"species": "적조생물"}]}
    })
    pr = parse(body)
    assert pr.parse_status == "OK"
    assert len(pr.items) == 1


def test_nifs_single_item_wrapped_in_list():
    """NIFS item이 1개일 때 단일 객체 → 리스트로"""
    body = json.dumps({
        "header": {"resultCode": "00"},
        "body": {"item": {"species": "적조생물"}}
    })
    pr = parse(body)
    assert pr.parse_status == "OK"
    assert isinstance(pr.items, list)
    assert len(pr.items) == 1


def test_xml_malformed_no_recovery():
    """malformed XML: 복구 파서 없이 PARSE_FAILURE"""
    body = "<response><header><resultCode>00</resultCode></header><body><items>"
    pr = parse(body)
    assert pr.parse_status == "PARSE_FAILURE"


def test_xml_openapi_error():
    """XML OpenAPI_ServiceResponse 에러 계열"""
    body = """<?xml version="1.0" encoding="UTF-8"?>
<OpenAPI_ServiceResponse>
  <cmmMsgHeader>
    <returnReasonCode>20</returnReasonCode>
  </cmmMsgHeader>
</OpenAPI_ServiceResponse>"""
    pr = parse(body)
    assert pr.parse_status == "KEY_ERROR"


def test_unknown_format():
    """알 수 없는 형식 → PARSE_FAILURE"""
    pr = parse("HELLO WORLD")
    assert pr.parse_status == "PARSE_FAILURE"
    assert pr.format == "unknown"

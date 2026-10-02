"""완전성 검사 N12, N13 (7.2절)"""
import pytest
from common.classifier import ParsedResponse
from processor.completeness import check_completeness, check_split_completeness


def _pr(total_count=None, items=None, parse_status="OK"):
    pr = ParsedResponse()
    pr.total_count = total_count
    pr.items = items or []
    pr.parse_status = parse_status
    return pr


# --- totalCount 있는 API ---

def test_total_count_match():
    pr = _pr(total_count=3)
    rows = [{}, {}, {}]
    r = check_completeness(pr, rows, "tide")
    assert r.status == "OK"

def test_total_count_mismatch():
    pr = _pr(total_count=5)
    rows = [{}, {}]
    r = check_completeness(pr, rows, "tide")
    assert r.status == "INCOMPLETE"
    assert r.expected == 5
    assert r.actual == 2


# --- N7: 필터 무시 ---

def test_N7_filter_ignored():
    """필터 창 2024년 요청, 1997년 행 반환 → FILTER_IGNORED"""
    pr = _pr()
    rows = [{"date": "19970101"}, {"date": "20240601"}]
    r = check_completeness(pr, rows, "fishery", request_window=("20240101", "20241231"))
    assert r.status == "FILTER_IGNORED"


def test_filter_all_in_window():
    pr = _pr()
    rows = [{"date": "20240601"}, {"date": "20240901"}]
    r = check_completeness(pr, rows, "fishery", request_window=("20240101", "20241231"))
    assert r.status == "OK"


# --- N12: 분할 합산 범위 불일치 ---

def test_N12_range_mismatch():
    """N12: 비교 범위가 다른 두 결과 → COMPARISON_RANGE_MISMATCH (절단·INCOMPLETE 금지)"""
    single = ("20250924", "20261231", 1000)
    splits = [("20251001", "20251031", 100), ("20251101", "20251130", 200)]
    r = check_split_completeness(single, splits)
    assert r.status == "COMPARISON_RANGE_MISMATCH"
    assert "범위" in r.message


# --- N13: 범위 일치 후 합 부족 ---

def test_N13_incomplete_after_range_match():
    """N13: 범위 맞춘 뒤 분할 합 < 단일 창 → INCOMPLETE"""
    single = ("20250901", "20250930", 1000)
    splits = [("20250901", "20250915", 300), ("20250916", "20250930", 400)]
    r = check_split_completeness(single, splits)
    assert r.status == "INCOMPLETE"
    assert r.actual == 700
    assert r.expected == 1000
    assert r.truncated_side == "SPLIT"


def test_N13_split_exceeds_single_is_single_truncation():
    """N13 ①(개정 17): 분할 합 > 단일 창 → INCOMPLETE·SINGLE — 정기 수집이 쓰는 단일 창 호출의 절단 의심"""
    single = ("20250901", "20250930", 600)
    splits = [("20250901", "20250915", 300), ("20250916", "20250930", 400)]
    r = check_split_completeness(single, splits)
    assert r.status == "INCOMPLETE" and r.truncated_side == "SINGLE"


@pytest.mark.parametrize("splits,why", [
    ([("20250901", "20250914", 300), ("20250916", "20250930", 400)], "빈틈"),
    ([("20250901", "20250916", 300), ("20250916", "20250930", 400)], "겹침"),
    ([("20250902", "20250915", 300), ("20250916", "20250930", 400)], "시작"),
    ([("20250901", "20250915", 300), ("20250916", "20250929", 400)], "끝"),
    ([], "없음"),
])
def test_N12_gap_or_overlap_is_range_mismatch(splits, why):
    """분할 창이 단일 창을 빈틈·겹침 없이 덮지 않으면 COMPARISON_RANGE_MISMATCH (개정 17)"""
    r = check_split_completeness(("20250901", "20250930", 700), splits)
    assert r.status == "COMPARISON_RANGE_MISMATCH", why


def test_split_order_does_not_matter():
    single = ("20250901", "20250930", 700)
    splits = [("20250916", "20250930", 400), ("20250901", "20250915", 300)]
    assert check_split_completeness(single, splits).status == "OK"


def test_split_ok():
    single = ("20250901", "20250930", 700)
    splits = [("20250901", "20250915", 300), ("20250916", "20250930", 400)]
    r = check_split_completeness(single, splits)
    assert r.status == "OK"

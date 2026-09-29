"""
정선관측 line 가공 어댑터 단위 테스트 (I-4)
검사: F4·F5·F6 (픽스처), N9 (합성 입력)
픽스처: fixtures/raw/sooList_depth_20260923_*.json (B v2, 10,445건)
"""
from __future__ import annotations
import json
from pathlib import Path

import pytest

from common.classifier import parse
from processor.adapters.line._adapter import (
    LineProcessorAdapter,
    _kst_to_utc,
    _parse_dtm,
    _parse_value,
    _compute_group_types,
    _assign_casts,
    _classify_group,
)

FIXTURES = Path(__file__).parents[2] / "fixtures" / "raw"
SOO_FILE = next(FIXTURES.glob("sooList_depth_*.json"), None)

_ADAPTER = LineProcessorAdapter()


# ── 픽스처 로드 헬퍼 ──────────────────────────────────────────────────────────

def _parse_fixture(path: Path):
    raw = json.loads(path.read_text("utf-8"))
    return parse(raw["body"])


def _run_fixture(path: Path) -> list[dict]:
    pr = _parse_fixture(path)
    rows = _ADAPTER.interpret(pr, {"raw_id": "test"})
    return _ADAPTER.normalize(rows)


# ── 합성 item 생성 헬퍼 ───────────────────────────────────────────────────────

def _item(gru="남해", sln="300", sta="01", obs_dtm="2026-01-01 09:00",
          wtr_dep="0", wtr_tmp="15.0", sal="33.5", dox="8.0",
          lat="35.0", lon="128.0"):
    return {
        "gru_nam": gru, "sln_cde": sln, "sta_cde": sta,
        "obs_dtm": obs_dtm, "wtr_dep": wtr_dep,
        "wtr_tmp": wtr_tmp, "sal": sal, "dox": dox,
        "lat": lat, "lon": lon,
        "qc_wtr": "2", "qc_sal": "2", "qc_dox": "2",
    }


def _make_pr(items: list[dict]):
    from common.classifier import ParsedResponse
    return ParsedResponse(
        format="json", result_code="00", parse_status="OK", items=items
    )


# ── KST→UTC 변환 ─────────────────────────────────────────────────────────────

def test_kst_to_utc_basic():
    assert _kst_to_utc("2026-01-01 09:00") == "2026-01-01T00:00:00"


def test_kst_to_utc_midnight():
    assert _kst_to_utc("2026-01-02 00:30") == "2026-01-01T15:30:00"


def test_kst_to_utc_empty():
    assert _kst_to_utc("") == ""


# ── group_type 분류 ───────────────────────────────────────────────────────────

def test_classify_P():
    assert _classify_group([0.0, 10.0, 20.0], 3) == "P"


def test_classify_Z_two_zeros():
    assert _classify_group([0.0, 0.0, 10.0], 3) == "Z"


def test_classify_S_single_zero():
    assert _classify_group([0.0], 1) == "S"


def test_classify_NO_ZERO():
    assert _classify_group([10.0, 20.0], 2) == "NO_ZERO"


def test_classify_Z_one_zero_no_positive():
    # 0m 1개, 양수 없음, 총 레코드 > 1 → Z
    assert _classify_group([0.0, None], 2) == "Z"


# ── _parse_value ─────────────────────────────────────────────────────────────

def test_parse_value_normal():
    v, m = _parse_value("15.5")
    assert v == 15.5 and m is None


def test_parse_value_blank():
    v, m = _parse_value("")
    assert v is None and m == "MISSING"


def test_parse_value_none():
    v, m = _parse_value(None)
    assert v is None and m == "MISSING"


def test_parse_value_zero():
    # 0.0은 line에서 ZERO_SENTINEL 아님 — 정상값
    v, m = _parse_value("0.0")
    assert v == 0.0 and m is None


# ── 캐스트 할당 ───────────────────────────────────────────────────────────────

def test_cast_same_group_gap_under_x():
    """간격 1분: 같은 캐스트"""
    from collections import defaultdict
    station_recs = defaultdict(list)
    key = ("남해", "300", "01")
    d1 = _parse_dtm("2026-01-01 09:00")
    d2 = _parse_dtm("2026-01-01 09:01")
    r1 = {"obs_dtm": "2026-01-01 09:00"}
    r2 = {"obs_dtm": "2026-01-01 09:01"}
    station_recs[key] = [(d1, r1), (d2, r2)]
    cmap, broken = _assign_casts(station_recs, x_min=60)
    assert cmap[(key, "2026-01-01 09:00")] == cmap[(key, "2026-01-01 09:01")]
    assert not broken


def test_cast_new_cast_over_x():
    """간격 61분: 새 캐스트"""
    from collections import defaultdict
    station_recs = defaultdict(list)
    key = ("남해", "300", "01")
    d1 = _parse_dtm("2026-01-01 09:00")
    d2 = _parse_dtm("2026-01-01 10:01")
    r1 = {"obs_dtm": "2026-01-01 09:00"}
    r2 = {"obs_dtm": "2026-01-01 10:01"}
    station_recs[key] = [(d1, r1), (d2, r2)]
    cmap, broken = _assign_casts(station_recs, x_min=60)
    assert cmap[(key, "2026-01-01 09:00")] != cmap[(key, "2026-01-01 10:01")]


def test_cast_broken_assumption_90min():
    """N9: 90분 간격 → CAST_RULE_ASSUMPTION_BROKEN"""
    from collections import defaultdict
    station_recs = defaultdict(list)
    key = ("남해", "300", "01")
    d1 = _parse_dtm("2026-01-01 09:00")
    d2 = _parse_dtm("2026-01-01 10:30")  # 90분 gap
    r1 = {"obs_dtm": "2026-01-01 09:00"}
    r2 = {"obs_dtm": "2026-01-01 10:30"}
    station_recs[key] = [(d1, r1), (d2, r2)]
    cmap, broken = _assign_casts(station_recs, x_min=60)
    # 90분 > 60분 → 새 캐스트
    assert cmap[(key, "2026-01-01 09:00")] != cmap[(key, "2026-01-01 10:30")]
    # 10 < 90 ≤ 720 → broken
    assert (key, "2026-01-01 10:30") in broken


def test_cast_no_broken_gap_10min():
    """경계: 10분은 broken 아님 (0 < 10 ≤ 10 → 포함 안 됨)"""
    from collections import defaultdict
    station_recs = defaultdict(list)
    key = ("남해", "300", "01")
    d1 = _parse_dtm("2026-01-01 09:00")
    d2 = _parse_dtm("2026-01-01 09:10")  # 정확히 10분
    r1 = {"obs_dtm": "2026-01-01 09:00"}
    r2 = {"obs_dtm": "2026-01-01 09:10"}
    station_recs[key] = [(d1, r1), (d2, r2)]
    _, broken = _assign_casts(station_recs, x_min=60)
    assert not broken  # 10분은 broken 아님


def test_cast_no_broken_gap_720min():
    """경계: 720분은 broken 포함 (10 < 720 ≤ 720)"""
    from collections import defaultdict
    station_recs = defaultdict(list)
    key = ("남해", "300", "01")
    d1 = _parse_dtm("2026-01-01 09:00")
    d2 = _parse_dtm("2026-01-01 21:00")  # 720분
    r1 = {"obs_dtm": "2026-01-01 09:00"}
    r2 = {"obs_dtm": "2026-01-01 21:00"}
    station_recs[key] = [(d1, r1), (d2, r2)]
    _, broken = _assign_casts(station_recs, x_min=60)
    # 720분 > 60 → 새 캐스트; 10 < 720 ≤ 720 → broken
    assert (key, "2026-01-01 21:00") in broken


def test_cast_no_broken_gap_721min():
    """경계: 721분은 broken 아님 (721 > 720)"""
    from collections import defaultdict
    station_recs = defaultdict(list)
    key = ("남해", "300", "01")
    d1 = _parse_dtm("2026-01-01 09:00")
    d2 = _parse_dtm("2026-01-01 21:01")  # 721분
    r1 = {"obs_dtm": "2026-01-01 09:00"}
    r2 = {"obs_dtm": "2026-01-01 21:01"}
    station_recs[key] = [(d1, r1), (d2, r2)]
    _, broken = _assign_casts(station_recs, x_min=60)
    assert not broken


# ── N9: 합성 입력 — 90분 간격 삽입 ──────────────────────────────────────────

def test_N9_cast_rule_assumption_broken():
    """
    N9: 같은 정점에 90분 간격 레코드 삽입 → CAST_RULE_ASSUMPTION_BROKEN 1건.
    broken은 (station_key, obs_dtm_str) 단위로 집계한다.
    """
    items = [
        _item(obs_dtm="2026-01-01 09:00", wtr_dep="0"),
        _item(obs_dtm="2026-01-01 09:00", wtr_dep="10"),
        _item(obs_dtm="2026-01-01 10:30", wtr_dep="0"),  # +90분
        _item(obs_dtm="2026-01-01 10:30", wtr_dep="10"),
    ]
    pr = _make_pr(items)
    rows = _ADAPTER.interpret(pr, {"raw_id": "n9"})
    broken_rows = [r for r in rows if "CAST_RULE_ASSUMPTION_BROKEN" in r.get("flags", [])]
    # 10:30 기록이 broken (3개 metric × 2 records = 6 rows)
    # broken 건수는 (station_key, obs_dtm_str) 고유 수 = 1
    broken_keys = {
        (r["station_id"], r["observed_at_utc"])
        for r in broken_rows
    }
    assert len(broken_keys) == 1


# ── 빈 값 레코드 ─────────────────────────────────────────────────────────────

def test_blank_record_stored_as_missing():
    """빈 값 레코드: wtr_tmp·sal·dox 모두 빈 → MISSING 저장"""
    items = [_item(wtr_tmp="", sal="", dox="")]
    pr = _make_pr(items)
    rows = _ADAPTER.interpret(pr, {"raw_id": "blank"})
    rows = _ADAPTER.normalize(rows)
    assert all(r["missing_reason"] == "MISSING" for r in rows)
    assert all(r["value"] is None for r in rows)


def test_blank_record_keeps_depth_and_cast():
    """빈 값 레코드도 depth_m과 cast_id를 유지한다"""
    items = [_item(wtr_tmp="", sal="", dox="", wtr_dep="5")]
    pr = _make_pr(items)
    rows = _ADAPTER.interpret(pr, {"raw_id": "blank"})
    rows = _ADAPTER.normalize(rows)
    assert all(r["depth_m"] == 5.0 for r in rows)
    assert all(r["cast_id"] is not None for r in rows)


def test_partial_blank_not_blank_record():
    """dox만 빈 문자열 → 빈 값 레코드 아님, dox는 MISSING"""
    items = [_item(wtr_tmp="15.0", sal="33.5", dox="")]
    pr = _make_pr(items)
    rows = _ADAPTER.interpret(pr, {"raw_id": "partial"})
    rows = _ADAPTER.normalize(rows)
    wt = next(r for r in rows if r["metric"] == "water_temp")
    sal = next(r for r in rows if r["metric"] == "salinity")
    dox = next(r for r in rows if r["metric"] == "dissolved_oxygen")
    assert wt["value"] == 15.0 and wt["missing_reason"] is None
    assert sal["value"] == 33.5 and sal["missing_reason"] is None
    assert dox["value"] is None and dox["missing_reason"] == "MISSING"


# ── 좌표 검증 ─────────────────────────────────────────────────────────────────

def test_coord_lat33_included():
    """lat=33.0 폐구간 포함 (남해 핵심 케이스)"""
    items = [_item(lat="33.0", lon="128.0")]
    pr = _make_pr(items)
    rows = _ADAPTER.interpret(pr, {"raw_id": "lat33"})
    assert len(rows) == 3  # 3 metrics


def test_coord_out_of_range_excluded():
    """lat=32.9 → 제외"""
    items = [_item(lat="32.9", lon="128.0")]
    pr = _make_pr(items)
    rows = _ADAPTER.interpret(pr, {"raw_id": "out"})
    assert len(rows) == 0


def test_coord_lng_out_excluded():
    """lon=123.9 → 제외"""
    items = [_item(lat="35.0", lon="123.9")]
    pr = _make_pr(items)
    rows = _ADAPTER.interpret(pr, {"raw_id": "out_lng"})
    assert len(rows) == 0


# ── metric 필드명 매핑 ────────────────────────────────────────────────────────

def test_metric_field_mapping():
    """wtr_tmp→water_temp, sal→salinity, dox→dissolved_oxygen"""
    items = [_item(wtr_tmp="15.5", sal="33.0", dox="8.5")]
    pr = _make_pr(items)
    rows = _ADAPTER.interpret(pr, {"raw_id": "m"})
    rows = _ADAPTER.normalize(rows)
    metrics = {r["metric"]: r["value"] for r in rows}
    assert metrics["water_temp"] == 15.5
    assert metrics["salinity"] == 33.0
    assert metrics["dissolved_oxygen"] == 8.5


# ── station_id 형식 ───────────────────────────────────────────────────────────

def test_station_id_format():
    items = [_item(gru="남해", sln="300", sta="01")]
    pr = _make_pr(items)
    rows = _ADAPTER.interpret(pr, {"raw_id": "sid"})
    assert all(r["station_id"] == "line:남해-300-01" for r in rows)


# ── cast_rule_version ─────────────────────────────────────────────────────────

def test_cast_rule_version():
    """cast_gap_minutes=60 → cast_rule_version='x60'"""
    items = [_item()]
    pr = _make_pr(items)
    rows = _ADAPTER.interpret(pr, {"raw_id": "crv"})
    assert all(r["cast_rule_version"] == "x60" for r in rows)


# ── F4·F5·F6: 픽스처 검사 ────────────────────────────────────────────────────

@pytest.mark.skipif(SOO_FILE is None, reason="sooList 픽스처 없음")
def test_F4_fixture_item_counts():
    """F4: 픽스처 총 10,445건, 남해 2,584건, lat=33.0(float) 레코드 포함"""
    pr = _parse_fixture(SOO_FILE)

    assert len(pr.items) == 10445, f"총 items: {len(pr.items)}"

    south_items = [r for r in pr.items if r.get("gru_nam") == "남해"]
    assert len(south_items) == 2584, f"남해 items: {len(south_items)}"

    # lat 값은 '33'으로 저장됨 — float로 비교
    def _lat33(r):
        try:
            return float(r.get("lat", "") or "") == 33.0
        except (ValueError, TypeError):
            return False

    lat33 = [r for r in south_items if _lat33(r)]
    assert len(lat33) == 523, f"lat=33.0 레코드: {len(lat33)}"

    # lat=33.0 레코드가 결과 rows에 포함돼야 한다 (폐구간 검증 통과)
    rows = _ADAPTER.interpret(pr, {"raw_id": "F4"})
    included_sids = {r["station_id"] for r in rows}
    lat33_sids = {
        f"line:{r['gru_nam']}-{r['sln_cde']}-{r['sta_cde']}"
        for r in lat33
    }
    assert lat33_sids.issubset(included_sids), "lat=33.0 정점이 결과에서 빠짐"


@pytest.mark.skipif(SOO_FILE is None, reason="sooList 픽스처 없음")
def test_F5_casts_and_blank_records():
    """
    F5: 남해 캐스트 324, 0m 정확히 1개인 캐스트 324, 빈 값 레코드 739 제외.
    캐스트 집계: non-MISSING 남해 rows의 distinct cast_id 수.
    빈 값 레코드: (station_id, observed_at_utc, depth_m) 3개 metric 모두 MISSING인 레코드.
    """
    from collections import defaultdict

    pr = _parse_fixture(SOO_FILE)
    rows = _ADAPTER.interpret(pr, {"raw_id": "F5"})
    rows = _ADAPTER.normalize(rows)

    south_rows = [r for r in rows if r["station_id"].startswith("line:남해-")]

    # 레코드 단위 집계: (station_id, observed_at_utc, depth_m) → set of metrics
    record_missing_metrics: dict[tuple, set] = defaultdict(set)
    record_valid_metrics: dict[tuple, set] = defaultdict(set)

    cast_zero_obs: dict[int, set] = defaultdict(set)  # cast_id → set of obs_utc that have depth==0

    for r in south_rows:
        rec_key = (r["station_id"], r["observed_at_utc"], r["depth_m"])
        if r["missing_reason"] == "MISSING":
            record_missing_metrics[rec_key].add(r["metric"])
        else:
            record_valid_metrics[rec_key].add(r["metric"])
            if r["depth_m"] == 0.0:
                cast_zero_obs[r["cast_id"]].add(r["observed_at_utc"])

    # 빈 값 레코드: 3개 metric 모두 MISSING이고 유효한 metric 없는 레코드
    blank_records = sum(
        1 for k in record_missing_metrics
        if len(record_missing_metrics[k]) == 3 and k not in record_valid_metrics
    )
    assert blank_records == 739, f"빈 값 레코드: {blank_records}"

    # 캐스트 집계: 유효한(non-MISSING) row가 있는 cast_id 수
    active_casts = {r["cast_id"] for r in south_rows if r["missing_reason"] is None}
    assert len(active_casts) == 324, f"남해 캐스트 수: {len(active_casts)}"

    # 0m 정확히 1개의 관측 시각을 가진 캐스트 = 324
    casts_with_exactly_one_zero = sum(
        1 for cid in active_casts if len(cast_zero_obs.get(cid, set())) == 1
    )
    assert casts_with_exactly_one_zero == 324, (
        f"0m 정확히 1개 obs인 캐스트: {casts_with_exactly_one_zero}"
    )


@pytest.mark.skipif(SOO_FILE is None, reason="sooList 픽스처 없음")
def test_F6_no_broken_assumptions():
    """F6: 픽스처에서 CAST_RULE_ASSUMPTION_BROKEN 0건"""
    pr = _parse_fixture(SOO_FILE)
    rows = _ADAPTER.interpret(pr, {"raw_id": "F6"})
    broken = [r for r in rows if "CAST_RULE_ASSUMPTION_BROKEN" in r.get("flags", [])]
    assert len(broken) == 0, f"CAST_RULE_ASSUMPTION_BROKEN {len(broken)}건"

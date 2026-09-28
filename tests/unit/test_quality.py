"""
품질 규칙 검사 Q1~Q4, Q6 (7.8절)
임계에 의존하는 것은 설정에 상대적으로 짠다
"""
import pytest
from processor.quality import apply_quality
import processor.quality._rules as _rules


_DEFS = {
    "quality": {
        "r1_salinity_min": 31.0,
        "r2_chlorophyll": {"max": 10.0, "delta": 5.0},
        "r3_water_temp_range": [0.0, 35.0],
        "r4_water_temp_delta_1h": 5.0,
    }
}

def _row(**kwargs):
    base = {"station_id": "S001", "water_temp": "20.0", "salinity": "33.0"}
    base.update(kwargs)
    return base


# --- Q1: R3 물리 범위 ---

def test_Q1_below_range():
    rows = apply_quality([_row(water_temp="-0.5")], "tide", _DEFS)
    assert rows[0]["quality_flag"] == "SENSOR_QUALITY"
    assert rows[0]["quality_rule"] == "R3"

def test_Q1_above_range():
    rows = apply_quality([_row(water_temp="35.5")], "tide", _DEFS)
    assert rows[0]["quality_flag"] == "SENSOR_QUALITY"

def test_Q1_boundary_min_ok():
    """경계값 0.0은 정상"""
    rows = apply_quality([_row(water_temp="0.0")], "tide", _DEFS)
    assert rows[0]["quality_flag"] == "OK"

def test_Q1_boundary_max_ok():
    """경계값 35.0은 정상"""
    rows = apply_quality([_row(water_temp="35.0")], "tide", _DEFS)
    assert rows[0]["quality_flag"] == "OK"

def test_Q1_normal():
    rows = apply_quality([_row(water_temp="20.0")], "tide", _DEFS)
    assert rows[0]["quality_flag"] == "OK"


# --- Q2: R4 급변 ---

def test_Q2_rapid_change():
    """1시간 변화 +5.5 → SENSOR_QUALITY"""
    prev = {_row()["station_id"]: _row(water_temp="15.0")}
    rows = apply_quality([_row(water_temp="20.5")], "tide", _DEFS, prev_hour_rows=prev)
    assert rows[0]["quality_flag"] == "SENSOR_QUALITY"
    assert rows[0]["quality_rule"] == "R4"

def test_Q2_rapid_change_typhoon_exempt():
    """태풍 특보 중에는 면제"""
    _rules._TYPHOON_ACTIVE = True
    try:
        prev = {_row()["station_id"]: _row(water_temp="15.0")}
        rows = apply_quality([_row(water_temp="20.5")], "tide", _DEFS, prev_hour_rows=prev)
        assert rows[0]["quality_flag"] == "OK"
    finally:
        _rules._TYPHOON_ACTIVE = False

def test_Q2_below_delta_ok():
    """변화 +4.9 → 정상"""
    prev = {_row()["station_id"]: _row(water_temp="15.5")}
    rows = apply_quality([_row(water_temp="20.4")], "tide", _DEFS, prev_hour_rows=prev)
    assert rows[0]["quality_flag"] == "OK"


# --- Q3: R1 생물부착 ---

def test_Q3_biofouling_line():
    """정선 염분 30.9 → SENSOR_QUALITY"""
    rows = apply_quality([_row(salinity="30.9")], "line", _DEFS)
    assert rows[0]["quality_flag"] == "SENSOR_QUALITY"
    assert rows[0]["quality_rule"] == "R1"

def test_Q3_estuary_exempt():
    """하구 예외 정점 → 면제"""
    _rules._ESTUARY_STATIONS = {"S001"}
    try:
        rows = apply_quality([_row(salinity="30.9")], "line", _DEFS)
        assert rows[0]["quality_flag"] == "OK"
    finally:
        _rules._ESTUARY_STATIONS = set()

def test_Q3_dtrecent_exempt():
    """dtRecent(tide)에는 R1 적용하지 않는다"""
    rows = apply_quality([_row(salinity="30.9")], "tide", _DEFS)
    assert rows[0]["quality_flag"] == "OK"


# --- Q4: R2 클로로필 급변 ---

def test_Q4_chlorophyll_spike():
    """10.5 & 직전 대비 +5.5 → SENSOR_QUALITY"""
    prev = {_row()["station_id"]: _row(chlorophyll="5.0")}
    rows = apply_quality([_row(chlorophyll="10.5")], "fishery", _DEFS, prev_rows=prev)
    assert rows[0]["quality_flag"] == "SENSOR_QUALITY"
    assert rows[0]["quality_rule"] == "R2"

def test_Q4_delta_not_enough():
    """10.5 & 직전 대비 +4.0 → 정상"""
    prev = {_row()["station_id"]: _row(chlorophyll="6.5")}
    rows = apply_quality([_row(chlorophyll="10.5")], "fishery", _DEFS, prev_rows=prev)
    assert rows[0]["quality_flag"] == "OK"

def test_Q4_not_over_max():
    """9.5 & +6.0 → max 미만이라 정상"""
    prev = {_row()["station_id"]: _row(chlorophyll="3.5")}
    rows = apply_quality([_row(chlorophyll="9.5")], "fishery", _DEFS, prev_rows=prev)
    assert rows[0]["quality_flag"] == "OK"


# --- R0 결측 ---

def test_R0_missing_zeros():
    rows = apply_quality([_row(water_temp="0.000", salinity="0.000", ph="0.000")], "line", _DEFS)
    assert rows[0]["quality_flag"] == "MISSING"

def test_R0_zero_row_not_dropped():
    """0.000 레코드는 버리지 않는다 — MISSING으로 저장"""
    rows = apply_quality([_row(water_temp="0.000", salinity="0.000", ph="0.000")], "line", _DEFS)
    assert len(rows) == 1

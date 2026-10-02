"""
품질 규칙 검사 Q1~Q4 (7.8절) — Q6은 test_adapter_health.py
임계에 의존하는 것은 설정에 상대적으로 짠다
입력은 어댑터 normalize() 결과와 같은 형태 — 행 하나가 metric 하나 (`metric`·`value`)
"""
import pytest
from common.config import load_definitions
from processor.quality import apply_quality


_DEFS = {
    "quality": {
        "r1_salinity_min": 31.0,
        "r2_chlorophyll": {"value": 10.0, "delta": 5.0},
        "r3_water_temp_range": [0.0, 35.0],
        "r4_water_temp_delta_1h": 5.0,
        "r4_lookback_tolerance_min": 15.4,
        "r1_estuary_stations": "<미결>",
    }
}


def _row(metric="water_temp", value=20.0, station_id="S001", **kwargs):
    base = {"station_id": station_id, "metric": metric, "value": value,
            "observed_at_utc": "2026-08-01T01:00:00", "flags": [], "missing_reason": None}
    base.update(kwargs)
    return base


def _tide_pair(prev_value, cur_value, minutes_apart=60):
    """같은 관측소 수온 두 행 — 앞 행이 minutes_apart분 전"""
    from datetime import datetime, timedelta
    t1 = datetime(2026, 8, 1, 2, 0, 0)
    t0 = t1 - timedelta(minutes=minutes_apart)
    return [
        _row(value=prev_value, observed_at_utc=t0.isoformat()),
        _row(value=cur_value, observed_at_utc=t1.isoformat()),
    ]


def _survey_pair(prev_value, cur_value, layer="S"):
    return [
        _row(metric="chlorophyll", value=prev_value, surveyed_on="2025-05-01",
             observed_at_utc="2025-05-01T00:30:00", layer=layer),
        _row(metric="chlorophyll", value=cur_value, surveyed_on="2025-06-01",
             observed_at_utc="2025-06-01T00:30:00", layer=layer),
    ]


# --- Q1: R3 물리 범위 ---

@pytest.mark.parametrize("value,expected", [
    (-0.5, "SENSOR_QUALITY"), (35.5, "SENSOR_QUALITY"),
    (0.0, "OK"), (35.0, "OK"), (20.0, "OK"),
])
def test_Q1_physical_range(value, expected):
    """앞 둘만 SENSOR_QUALITY. 경계값 0.0·35.0은 정상"""
    rows = apply_quality([_row(value=value)], "dtRecent", _DEFS)
    assert rows[0]["quality_flag"] == expected
    assert ("SENSOR_QUALITY" in rows[0]["flags"]) == (expected == "SENSOR_QUALITY")
    if expected == "SENSOR_QUALITY":
        assert rows[0]["quality_rule"] == "R3"


def test_Q1_other_metric_not_checked():
    """R3는 수온 행에만 — 염분 40.0은 R3 대상이 아님"""
    rows = apply_quality([_row(metric="salinity", value=40.0)], "dtRecent", _DEFS)
    assert rows[0]["quality_flag"] == "OK"


# --- Q2: R4 급변 ---

def test_Q2_rapid_change():
    """1시간 변화 +5.5 → SENSOR_QUALITY (같은 수집 안의 1시간 전 관측과 비교)"""
    rows = apply_quality(_tide_pair(15.0, 20.5), "dtRecent", _DEFS)
    assert rows[1]["quality_flag"] == "SENSOR_QUALITY"
    assert rows[1]["quality_rule"] == "R4"
    assert "SENSOR_QUALITY" in rows[1]["flags"]
    assert rows[0]["quality_flag"] == "OK"


def test_Q2_rapid_change_typhoon_exempt():
    """태풍 특보 중에는 면제 — 운영 조정 typhoon_active = true"""
    rows = apply_quality(_tide_pair(15.0, 20.5), "dtRecent", _DEFS,
                         operational={"typhoon_active": True})
    assert rows[1]["quality_flag"] == "OK"


def test_Q2_below_delta_ok():
    """변화 +4.9 → 정상"""
    rows = apply_quality(_tide_pair(15.5, 20.4), "dtRecent", _DEFS)
    assert rows[1]["quality_flag"] == "OK"


@pytest.mark.parametrize("minutes_apart,expected", [
    (30, "OK"),                 # 창보다 가깝다
    (60, "SENSOR_QUALITY"),     # 창 끝(t − 60분)
    (75, "SENSOR_QUALITY"),     # 창 안(t − 60분 − 15분)
    (76, "OK"),                 # 창 밖(허용 15.4분 초과)
])
def test_Q2_lookback_window(minutes_apart, expected):
    """직전 관측이 1시간 전 창 [t−60분−허용, t−60분] 밖이면 정상 — 허용에 상대적으로"""
    rows = apply_quality(_tide_pair(15.0, 20.5, minutes_apart=minutes_apart), "dtRecent", _DEFS)
    assert rows[1]["quality_flag"] == expected


def test_Q2_no_tolerance_key_no_r4():
    """quality.r4_lookback_tolerance_min이 없으면 R4를 판정하지 않는다"""
    defs = {"quality": {k: v for k, v in _DEFS["quality"].items() if k != "r4_lookback_tolerance_min"}}
    rows = apply_quality(_tide_pair(15.0, 20.5), "dtRecent", defs)
    assert rows[1]["quality_flag"] == "OK"


def test_Q2_explicit_prev_hour_value():
    """호출자가 직전 값을 주면 그것을 쓴다 (행 index → 값)"""
    rows = apply_quality([_row(value=20.5)], "dtRecent", _DEFS, prev_hour_rows={0: 15.0})
    assert rows[0]["quality_rule"] == "R4"


# --- Q3: R1 생물부착 ---

def test_Q3_biofouling_line():
    """정선 염분 30.9 → SENSOR_QUALITY"""
    rows = apply_quality([_row(metric="salinity", value=30.9)], "sooList", _DEFS)
    assert rows[0]["quality_flag"] == "SENSOR_QUALITY"
    assert rows[0]["quality_rule"] == "R1"


def test_Q3_biofouling_fishery():
    rows = apply_quality([_row(metric="salinity", value=30.9, surveyed_on="2025-06-01", layer="S")],
                         "femoSeaList", _DEFS)
    assert rows[0]["quality_rule"] == "R1"


def test_Q3_estuary_exempt():
    """하구 예외 정점 → 면제 (quality.r1_estuary_stations — 값 미결, 합성 목록으로 준다)"""
    defs = {"quality": {**_DEFS["quality"], "r1_estuary_stations": ["S001"]}}
    rows = apply_quality([_row(metric="salinity", value=30.9)], "sooList", defs)
    assert rows[0]["quality_flag"] == "OK"


def test_Q3_estuary_pending_applies_everywhere():
    """r1_estuary_stations가 <미결>이면 예외 없이 R1을 적용한다"""
    rows = apply_quality([_row(metric="salinity", value=30.9)], "sooList", _DEFS)
    assert rows[0]["quality_rule"] == "R1"


def test_Q3_dtrecent_exempt():
    """dtRecent에는 R1을 적용하지 않는다"""
    rows = apply_quality([_row(metric="salinity", value=30.9)], "dtRecent", _DEFS)
    assert rows[0]["quality_flag"] == "OK"


# --- Q4: R2 클로로필 급변 ---

@pytest.mark.parametrize("prev,cur,expected", [
    (5.0, 10.5, "SENSOR_QUALITY"),   # 10.5 & +5.5
    (6.5, 10.5, "OK"),               # 10.5 & +4.0
    (3.5, 9.5, "OK"),                # 9.5 & +6.0 — 기준값 이하
])
def test_Q4_chlorophyll(prev, cur, expected):
    rows = apply_quality(_survey_pair(prev, cur), "femoSeaList", _DEFS)
    assert rows[1]["quality_flag"] == expected
    if expected == "SENSOR_QUALITY":
        assert rows[1]["quality_rule"] == "R2"


def test_Q4_other_layer_is_not_previous():
    """직전 = 같은 정점·같은 층 — 다른 층의 조사는 직전이 아니다"""
    rows = [
        _row(metric="chlorophyll", value=5.0, surveyed_on="2025-05-01", layer="B"),
        _row(metric="chlorophyll", value=10.5, surveyed_on="2025-06-01", layer="S"),
    ]
    out = apply_quality(rows, "femoSeaList", _DEFS)
    assert out[1]["quality_flag"] == "OK"


def test_Q4_real_definitions_key():
    """실제 판정 정의(config/definitions.yaml)의 r2 키로 R2가 걸린다 — 키 이름 회귀 방지"""
    defs = load_definitions()
    v = defs["quality"]["r2_chlorophyll"]["value"]
    d = defs["quality"]["r2_chlorophyll"]["delta"]
    rows = apply_quality(_survey_pair(v - d, v + 0.5), "femoSeaList", defs)
    assert rows[1]["quality_rule"] == "R2"


def test_real_definitions_r3_r1():
    """실제 판정 정의로 R3·R1이 걸린다"""
    defs = load_definitions()
    hi = defs["quality"]["r3_water_temp_range"][1]
    lo_sal = defs["quality"]["r1_salinity_min"]
    assert apply_quality([_row(value=hi + 0.5)], "dtRecent", defs)[0]["quality_rule"] == "R3"
    assert apply_quality([_row(metric="salinity", value=lo_sal - 0.1)], "sooList", defs)[0]["quality_rule"] == "R1"


# --- R0 결측 ---

def test_R0_missing_value():
    rows = apply_quality([_row(value=None, missing_reason="ZERO_SENTINEL")], "sooList", _DEFS)
    assert rows[0]["quality_flag"] == "MISSING"
    assert rows[0]["quality_rule"] == "R0"


def test_R0_missing_row_not_dropped():
    """0.000·빈 값 레코드는 버리지 않는다 — MISSING으로 저장"""
    rows = apply_quality([_row(value=None), _row(value=20.0)], "dtRecent", _DEFS)
    assert len(rows) == 2


def test_existing_flags_kept():
    """어댑터가 단 플래그(STALE_SUSPECT 등)는 유지한다"""
    rows = apply_quality([_row(value=40.0, flags=["STALE_SUSPECT"])], "dtRecent", _DEFS)
    assert rows[0]["flags"] == ["STALE_SUSPECT", "SENSOR_QUALITY"]


def test_Q4_previous_is_by_observed_time_same_day():
    """직전 = 조사 시각 기준 (개정 14) — 같은 날 09시 5.0 → 15시 10.5는 직전 대비 +5.5"""
    rows = [
        _row(metric="chlorophyll", value=10.5, surveyed_on="2025-06-01", observed_at_utc="2025-06-01T06:00:00", layer="S"),
        _row(metric="chlorophyll", value=5.0, surveyed_on="2025-06-01", observed_at_utc="2025-06-01T00:00:00", layer="S"),
    ]
    out = apply_quality(rows, "femoSeaList", _DEFS)
    assert out[0]["quality_rule"] == "R2" and out[1]["quality_flag"] == "OK"


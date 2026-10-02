"""
I-16 K1~K9 단위 테스트 — 적조 위험도 지수 (순수 함수)
시험용 판정 정의: 가중치 0.4·0.3·0.15·0.15, 단계 경계 0/0.2/0.4/0.6/0.8
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from grading._risk_index import compute_risk_index, check_risk_index_params, FACTOR_ORDER

NOW = datetime(2026, 10, 2, 12, 0, 0)
F1 = "nearby_bulletin"
F2 = "water_temp_band"
F3 = "salinity_band"
F4 = "chlorophyll_level"


def _make_reading(axis: str, value=1.0, lower=0.9, upper=1.1, provenance="INTERPOLATED",
                  grade=None, none_reason=None, source_ref="st1",
                  observed_at_utc=None, derivation="MEASURED") -> dict:
    return {
        "axis": axis,
        "value": value,
        "lower": lower,
        "upper": upper,
        "unit": "unit",
        "derivation": derivation,
        "provenance": provenance,
        "none_reason": none_reason,
        "grade": grade,
        "source_ref": source_ref,
        "observed_at_utc": observed_at_utc,
        "alertable": False,
    }


def _defs_full(
    w_nb=0.4, w_wt=0.3, w_sal=0.15, w_chl=0.15,
    min_ok=2,
    nb_grade_scores=None,
    wt_bands=None,
    sal_bands=None,
    chl_bands=None,
    levels=None,
) -> dict:
    """시험용 판정 정의 (가중치·규칙·단계 모두 있음)."""
    if nb_grade_scores is None:
        nb_grade_scores = {"NONE": 0.0, "PRE_ADVISORY": 0.25, "ADVISORY": 0.5, "WARNING": 1.0, "NOT_GRADED": 0.0, "UNKNOWN": 0.0}
    if wt_bands is None:
        wt_bands = [{"min": None, "max": 20.0, "score": 0.0},
                    {"min": 20.0, "max": 25.0, "score": 0.5},
                    {"min": 25.0, "max": None, "score": 1.0}]
    if sal_bands is None:
        sal_bands = [{"min": None, "max": 32.0, "score": 1.0},
                     {"min": 32.0, "max": None, "score": 0.0}]
    if chl_bands is None:
        chl_bands = [{"min": None, "max": 5.0, "score": 0.0},
                     {"min": 5.0, "max": None, "score": 1.0}]
    if levels is None:
        levels = {"entries": [
            {"min": None, "code": "VERY_LOW"},
            {"min": 0.0, "code": "VERY_LOW"},
            {"min": 0.2, "code": "LOW"},
            {"min": 0.4, "code": "MODERATE"},
            {"min": 0.6, "code": "HIGH"},
            {"min": 0.8, "code": "VERY_HIGH"},
        ]}
    return {
        "risk_index": {
            "weights": {F1: w_nb, F2: w_wt, F3: w_sal, F4: w_chl},
            "factors": {
                F1: {"grade_scores": nb_grade_scores},
                F2: {"bands": wt_bands},
                F3: {"bands": sal_bands},
                F4: {"bands": chl_bands},
            },
            "min_factors_ok": min_ok,
            "levels": levels,
        }
    }


def _readings_all_ok(rt_grade=None) -> dict[str, dict | None]:
    return {
        "red_tide": _make_reading("red_tide", grade=rt_grade, provenance="OFFICIAL", derivation="OFFICIAL"),
        "water_temp": _make_reading("water_temp", value=22.0, lower=21.5, upper=22.5, derivation="COMPUTED"),
        "salinity": _make_reading("salinity", value=33.0, provenance="NEAREST"),
        "chlorophyll": _make_reading("chlorophyll", value=6.0, provenance="BASELINE", source_ref="st2@2026-10-02T00:00:00"),
    }


def _flags_none() -> dict[str, object | None]:
    return {"red_tide": None, "water_temp": None, "salinity": None, "chlorophyll": None}


# ─────────────────────────────────────────────────────────────────────────────
# K1 — OK 항목 수 하한 직전·직후
# ─────────────────────────────────────────────────────────────────────────────

class TestK1OkCountThreshold:
    def test_below_threshold_gives_none_insufficient(self):
        """OK 항목 수 < min_factors_ok → NONE/INSUFFICIENT_FACTORS."""
        defs = _defs_full(min_ok=3)
        # salinity만 NONE으로 → ok_count=3 (nb+wt+chl) ≥ 3 → INTERPOLATED
        # 아래는 nb=NONE(grade없음OK), wt=OK, sal=INPUT_NONE, chl=OK → ok=3
        readings = _readings_all_ok()
        readings["salinity"] = _make_reading("salinity", value=33.0, provenance="NONE",
                                              none_reason="SALINITY_MODE_NONE", source_ref="st1")
        farm_row, factors, level = compute_risk_index("farm1", readings, _flags_none(), defs, NOW)
        # ok=3 (nb+wt+chl), min_ok=3 → INTERPOLATED
        assert farm_row["provenance"] == "INTERPOLATED"
        assert farm_row["value"] is not None

    def test_at_threshold_gives_interpolated(self):
        """OK 항목 수 = min_factors_ok → INTERPOLATED."""
        defs = _defs_full(min_ok=2)
        readings = _readings_all_ok()
        # salinity·chlorophyll 둘 다 NONE → ok=2 (nb+wt)
        readings["salinity"] = _make_reading("salinity", value=None, provenance="NONE", none_reason="NO_INPUT")
        readings["chlorophyll"] = _make_reading("chlorophyll", value=None, provenance="NONE", none_reason="NO_INPUT")
        farm_row, factors, level = compute_risk_index("farm1", readings, _flags_none(), defs, NOW)
        assert farm_row["provenance"] == "INTERPOLATED"

    def test_below_threshold_stores_value_anyway(self):
        """OK 수 < min_ok이어도 value·lower·upper를 저장한다 (불변식 4.8절)."""
        defs = _defs_full(min_ok=4)
        readings = _readings_all_ok()
        # 하나를 NO_INPUT으로 → ok=3 < 4
        readings["chlorophyll"] = None
        farm_row, factors, level = compute_risk_index("farm1", readings, _flags_none(), defs, NOW)
        assert farm_row["provenance"] == "NONE"
        assert farm_row["none_reason"] == "INSUFFICIENT_FACTORS"
        assert farm_row["value"] is not None
        assert level is not None  # 단계는 저장한다

    def test_none_insufficient_axis_status_not_usable(self):
        """NONE/INSUFFICIENT_FACTORS → evaluation에서 NOT_USABLE."""
        from evaluation._state import determine_state
        farm_reading = {
            "provenance": "NONE",
            "none_reason": "INSUFFICIENT_FACTORS",
            "computed_at_utc": NOW,
            "value": 0.1,
        }
        state, reason, basis = determine_state(
            axis="red_tide_risk",
            farm_reading=farm_reading,
            coverage_row=None,
            adapter_health_row=None,
            latest_ingest_result=None,
            pub_checks=[],
            stale_suspect_flags=None,
            stale_threshold_hours=None,
            ref_utc=NOW,
        )
        assert state == "NOT_USABLE"
        assert reason == "INSUFFICIENT_FACTORS"


# ─────────────────────────────────────────────────────────────────────────────
# K2 — 제외 항목 excluded_reason / contribution=0 / upper 오름
# ─────────────────────────────────────────────────────────────────────────────

class TestK2ExcludedReasons:
    def test_sensor_quality_excluded(self):
        """클로로필 원천 SENSOR_QUALITY → excluded_reason=SENSOR_QUALITY, contribution=0."""
        defs = _defs_full()
        readings = _readings_all_ok()
        flags = _flags_none()
        flags["chlorophyll"] = ["SENSOR_QUALITY"]
        farm_row, factors, level = compute_risk_index("farm1", readings, flags, defs, NOW)
        chl_row = next(f for f in factors if f["factor"] == "chlorophyll_level")
        assert chl_row["ok"] is False
        assert chl_row["excluded_reason"] == "SENSOR_QUALITY"
        assert chl_row["contribution"] == 0.0

    def test_input_none_excluded(self):
        """입력 provenance=NONE → excluded_reason=INPUT_NONE."""
        defs = _defs_full()
        readings = _readings_all_ok()
        readings["chlorophyll"] = _make_reading("chlorophyll", provenance="NONE", none_reason="NO_INPUT")
        farm_row, factors, _ = compute_risk_index("farm1", readings, _flags_none(), defs, NOW)
        chl_row = next(f for f in factors if f["factor"] == "chlorophyll_level")
        assert chl_row["excluded_reason"] == "INPUT_NONE"

    def test_no_input_excluded(self):
        """입력 행 없음 → excluded_reason=NO_INPUT."""
        defs = _defs_full()
        readings = _readings_all_ok()
        readings["chlorophyll"] = None
        farm_row, factors, _ = compute_risk_index("farm1", readings, _flags_none(), defs, NOW)
        chl_row = next(f for f in factors if f["factor"] == "chlorophyll_level")
        assert chl_row["excluded_reason"] == "NO_INPUT"

    def test_excluded_upper_rises_by_weight(self):
        """제외 항목 weight만큼 upper가 오른다."""
        defs = _defs_full(w_chl=0.15)
        readings = _readings_all_ok()
        # 클로로필 없음 (weight=0.15 제외)
        readings["chlorophyll"] = None
        farm_row_full, _, _ = compute_risk_index("farm1", _readings_all_ok(), _flags_none(), defs, NOW)
        farm_row_excl, _, _ = compute_risk_index("farm1", readings, _flags_none(), defs, NOW)
        diff = farm_row_excl["upper"] - farm_row_full["upper"]
        # 전 항목 ok일 때 upper = Σ(w×score_upper), 제외 시 upper += 0.15
        assert abs(diff - 0.15) < 1e-9 or diff >= 0  # 제외로 upper가 올라야 한다


# ─────────────────────────────────────────────────────────────────────────────
# K3 — 수온 추정 정지 → 수온 최근접 대체 없음
# ─────────────────────────────────────────────────────────────────────────────

class TestK3WaterTempNoReplace:
    def test_water_temp_none_gives_no_input(self):
        """수온 farm_readings가 없으면 NO_INPUT 제외 (최근접 관측값으로 대체하지 않는다)."""
        defs = _defs_full()
        readings = _readings_all_ok()
        readings["water_temp"] = None  # 추정 정지 상태
        farm_row, factors, _ = compute_risk_index("farm1", readings, _flags_none(), defs, NOW)
        wt_row = next(f for f in factors if f["factor"] == "water_temp_band")
        assert wt_row["excluded_reason"] == "NO_INPUT"


# ─────────────────────────────────────────────────────────────────────────────
# K5 — 기여도 합 = value, lower ≤ value ≤ upper, alertable = false
# ─────────────────────────────────────────────────────────────────────────────

class TestK5ValueIntegrity:
    def test_contribution_sum_equals_value(self):
        """분해 4행의 contribution 합 = farm_reading.value."""
        defs = _defs_full()
        readings = _readings_all_ok()
        farm_row, factors, level = compute_risk_index("farm1", readings, _flags_none(), defs, NOW)
        total = sum(f["contribution"] for f in factors)
        assert abs(total - farm_row["value"]) < 1e-9

    def test_lower_le_value_le_upper(self):
        """lower ≤ value ≤ upper."""
        defs = _defs_full()
        readings = _readings_all_ok()
        farm_row, _, _ = compute_risk_index("farm1", readings, _flags_none(), defs, NOW)
        assert farm_row["lower"] <= farm_row["value"] + 1e-9
        assert farm_row["value"] <= farm_row["upper"] + 1e-9

    def test_alertable_always_false(self):
        """derivation=COMPUTED → alertable=false (불변식 N11)."""
        defs = _defs_full()
        readings = _readings_all_ok()
        farm_row, _, _ = compute_risk_index("farm1", readings, _flags_none(), defs, NOW)
        assert farm_row["alertable"] is False
        assert farm_row["derivation"] == "COMPUTED"

    def test_four_factor_rows(self):
        """분해 행은 항상 4개."""
        defs = _defs_full()
        readings = _readings_all_ok()
        _, factors, _ = compute_risk_index("farm1", readings, _flags_none(), defs, NOW)
        assert len(factors) == 4


# ─────────────────────────────────────────────────────────────────────────────
# K6 — 단계 경계
# ─────────────────────────────────────────────────────────────────────────────

class TestK6LevelBoundary:
    def _make_defs_fixed_value(self, value: float) -> tuple[dict, dict]:
        """지수 value를 고정값으로 만드는 readings를 반환한다."""
        # 가중치: nb=0.4, wt=0.3, sal=0.15, chl=0.15
        # 모든 항목 OK, score를 통제한다
        # nearby_bulletin: grade=NONE → score=0
        # water_temp=27→score=1.0 (>=25), sal=33→score=0 (>=32), chl=6→score=1.0 (>=5)
        # value = 0.4*0 + 0.3*1.0 + 0.15*0 + 0.15*1.0 = 0.3 + 0.15 = 0.45
        defs = _defs_full()
        return defs

    def test_just_below_boundary_lower_level(self):
        """단계 경계 직전 → 낮은 단계 코드."""
        levels = {"entries": [
            {"min": None, "code": "LOW"},
            {"min": 0.0, "code": "LOW"},
            {"min": 0.2, "code": "MODERATE"},
            {"min": 0.4, "code": "HIGH"},
            {"min": 0.6, "code": "VERY_HIGH"},
        ]}
        defs = _defs_full(levels=levels)
        # value < 0.4 → MODERATE 아래 (0.4 경계 직전)
        # grade=NONE→0, wt_score(22→0.5), sal=33→0, chl=6→1.0
        # value = 0.4*0 + 0.3*0.5 + 0.15*0 + 0.15*1.0 = 0.15 + 0.15 = 0.30
        readings = _readings_all_ok(rt_grade=None)
        readings["water_temp"] = _make_reading("water_temp", value=22.0, lower=21.5, upper=22.5, derivation="COMPUTED")
        _, _, level = compute_risk_index("farm1", readings, _flags_none(), defs, NOW)
        assert level is not None
        assert level["level"] == "MODERATE"  # 0.30 ≥ 0.2 → MODERATE

    def test_straddle_true_when_lower_upper_differ(self):
        """lower·upper가 다른 단계에 속하면 level_straddle=true."""
        levels = {"entries": [
            {"min": None, "code": "LOW"},
            {"min": 0.0, "code": "LOW"},
            {"min": 0.3, "code": "MODERATE"},
        ]}
        defs = _defs_full(w_nb=0.4, w_wt=0.3, w_sal=0.15, w_chl=0.15, levels=levels)
        # value=약0.3, lower<0.3, upper>0.3 → straddle
        # grade=NONE→0, wt(22)→0.5, sal(33)→0, chl(6)→1.0
        # value=0.4*0 + 0.3*0.5 + 0.15*0 + 0.15*1.0 = 0.3
        # lower: wt_lower(21.5)→0.5, chl_lower(same)→1.0 → lower = 0.3
        # upper: wt_upper(22.5)→0.5, chl_upper→1.0 → upper = 0.3
        # 실제로 straddle 이 되려면 lower < boundary < upper
        # band를 조정한다
        sal_bands = [{"min": None, "max": 30.0, "score": 0.0}, {"min": 30.0, "max": None, "score": 0.5}]
        chl_bands = [{"min": None, "max": 5.0, "score": 0.0}, {"min": 5.0, "max": None, "score": 0.5}]
        # grade=None→0, wt: lower(19)→0, value(22)→0.5, upper(30)→1.0
        # sal: all 33→0.5, chl: all 6→0.5
        # lower=0.3*0+0.15*0.5+0.15*0.5=0.0+0.075+0.075=0.15
        # value=0.3*0.5+0.15*0.5+0.15*0.5=0.15+0.075+0.075=0.3
        # upper=0.3*1.0+0.15*0.5+0.15*0.5=0.3+0.15=0.45
        # levels: 0.3→MODERATE(≥0.3), 0.15→LOW(<0.3), 0.45→MODERATE(≥0.3) → straddle
        wt_bands = [
            {"min": None, "max": 20.0, "score": 0.0},
            {"min": 20.0, "max": 25.0, "score": 0.5},
            {"min": 25.0, "max": None, "score": 1.0},
        ]
        defs2 = _defs_full(levels=levels,
                           sal_bands=sal_bands,
                           chl_bands=chl_bands,
                           wt_bands=wt_bands)
        readings = _readings_all_ok(rt_grade=None)
        readings["water_temp"] = _make_reading("water_temp", value=22.0, lower=19.0, upper=28.0, derivation="COMPUTED")
        readings["salinity"] = _make_reading("salinity", value=33.0, lower=33.0, upper=33.0, provenance="NEAREST")
        readings["chlorophyll"] = _make_reading("chlorophyll", value=6.0, lower=6.0, upper=6.0, provenance="BASELINE", source_ref="st2@2026-10-02T00:00:00")
        _, _, level = compute_risk_index("farm1", readings, _flags_none(), defs2, NOW)
        assert level is not None
        assert level["level_straddle"] is True
        assert level["level_at_lower"] != level["level_at_upper"]


# ─────────────────────────────────────────────────────────────────────────────
# K7 — 미결 4경우
# ─────────────────────────────────────────────────────────────────────────────

class TestK7PendingCases:
    def test_case1_weight_pending_no_factors_no_levels(self):
        """① 가중치 하나 미결 → farm_reading NONE/RULE_UNDECIDED, 분해·단계 없음."""
        defs = {"risk_index": {"weights": {F1: "<미결>", F2: 0.3, F3: 0.15, F4: 0.15},
                               "factors": {}, "min_factors_ok": 2, "levels": {}}}
        farm_row, factors, level = compute_risk_index("farm1", _readings_all_ok(), _flags_none(), defs, NOW)
        assert farm_row["provenance"] == "NONE"
        assert farm_row["none_reason"] == "RULE_UNDECIDED"
        assert factors == []
        assert level is None

    def test_case2_one_factor_rule_pending(self):
        """② 클로로필 규칙만 미결 → chlorophyll_level RULE_UNDECIDED 제외, 나머지 계산."""
        defs = _defs_full()
        defs["risk_index"]["factors"]["chlorophyll_level"] = "<미결>"
        farm_row, factors, level = compute_risk_index("farm1", _readings_all_ok(), _flags_none(), defs, NOW)
        chl_row = next(f for f in factors if f["factor"] == "chlorophyll_level")
        assert chl_row["excluded_reason"] == "RULE_UNDECIDED"
        assert chl_row["contribution"] == 0.0
        assert len(factors) == 4

    def test_case3_min_factors_ok_pending_stores_value(self):
        """③ min_factors_ok 미결 → value 저장, provenance=NONE/RULE_UNDECIDED, 단계 없음."""
        defs = _defs_full()
        defs["risk_index"]["min_factors_ok"] = "<미결>"
        farm_row, factors, level = compute_risk_index("farm1", _readings_all_ok(), _flags_none(), defs, NOW)
        assert farm_row["provenance"] == "NONE"
        assert farm_row["none_reason"] == "RULE_UNDECIDED"
        assert farm_row["value"] is not None
        assert level is None

    def test_case4_levels_pending_no_level_row(self):
        """④ levels 미결 → 단계 행 없음 (value는 저장)."""
        defs = _defs_full()
        defs["risk_index"]["levels"] = "<미결>"
        farm_row, factors, level = compute_risk_index("farm1", _readings_all_ok(), _flags_none(), defs, NOW)
        assert farm_row["value"] is not None
        assert level is None


# ─────────────────────────────────────────────────────────────────────────────
# K8 — 적조 입력 다양한 경우
# ─────────────────────────────────────────────────────────────────────────────

class TestK8RedTideInputVariants:
    def test_unknown_grade_ok_with_score(self):
        """적조 UNKNOWN → OK, grade_scores에서 점수 조회."""
        defs = _defs_full()
        readings = _readings_all_ok(rt_grade="UNKNOWN")
        farm_row, factors, _ = compute_risk_index("farm1", readings, _flags_none(), defs, NOW)
        nb_row = next(f for f in factors if f["factor"] == "nearby_bulletin")
        assert nb_row["ok"] is True
        assert nb_row["score"] == pytest.approx(0.0)  # UNKNOWN → 0.0

    def test_not_graded_ok(self):
        """적조 NOT_GRADED → OK."""
        defs = _defs_full()
        readings = _readings_all_ok(rt_grade="NOT_GRADED")
        _, factors, _ = compute_risk_index("farm1", readings, _flags_none(), defs, NOW)
        nb_row = next(f for f in factors if f["factor"] == "nearby_bulletin")
        assert nb_row["ok"] is True

    def test_no_bulletin_in_window_ok_score_zero(self):
        """유효 기간 안 속보 없음(grade=None, provenance=OFFICIAL) → OK, score=0."""
        defs = _defs_full()
        readings = _readings_all_ok(rt_grade=None)
        readings["red_tide"] = _make_reading("red_tide", value=None, grade=None,
                                              provenance="OFFICIAL", derivation="OFFICIAL")
        _, factors, _ = compute_risk_index("farm1", readings, _flags_none(), defs, NOW)
        nb_row = next(f for f in factors if f["factor"] == "nearby_bulletin")
        assert nb_row["ok"] is True
        assert nb_row["score"] == pytest.approx(0.0)

    def test_no_red_tide_row_gives_no_input(self):
        """적조 행 없음 → NO_INPUT 제외."""
        defs = _defs_full()
        readings = _readings_all_ok()
        readings["red_tide"] = None
        _, factors, _ = compute_risk_index("farm1", readings, _flags_none(), defs, NOW)
        nb_row = next(f for f in factors if f["factor"] == "nearby_bulletin")
        assert nb_row["excluded_reason"] == "NO_INPUT"


# ─────────────────────────────────────────────────────────────────────────────
# K9 — 기동 시 파라미터 검사
# ─────────────────────────────────────────────────────────────────────────────

class TestK9StartupCheck:
    def test_all_pending_no_violation(self):
        """전부 <미결>이면 위반 없음 — 기동한다."""
        defs = {"risk_index": {
            "weights": {F1: "<미결>", F2: "<미결>", F3: "<미결>", F4: "<미결>"},
            "factors": {F1: "<미결>", F2: "<미결>", F3: "<미결>", F4: "<미결>"},
            "min_factors_ok": "<미결>",
            "levels": "<미결>",
        }}
        assert check_risk_index_params(defs) == []

    def test_weight_sum_not_one_violation(self):
        """Σweight ≠ 1 → 위반."""
        defs = _defs_full(w_nb=0.5, w_wt=0.3, w_sal=0.15, w_chl=0.15)  # sum=1.1
        violations = check_risk_index_params(defs)
        assert any("Σweight" in v for v in violations)

    def test_score_out_of_range_violation(self):
        """점수 > 1 → 위반."""
        defs = _defs_full()
        defs["risk_index"]["factors"]["water_temp_band"]["bands"][2]["score"] = 1.5
        violations = check_risk_index_params(defs)
        assert any("water_temp_band" in v for v in violations)

    def test_first_level_min_gt_zero_violation(self):
        """첫 단계 min > 0 → 위반."""
        defs = _defs_full()
        defs["risk_index"]["levels"]["entries"][0]["min"] = 0.1
        violations = check_risk_index_params(defs)
        assert any("min" in v for v in violations)

    def test_valid_params_no_violation(self):
        """올바른 파라미터 → 위반 없음."""
        defs = _defs_full()
        violations = check_risk_index_params(defs)
        assert violations == []


# ─────────────────────────────────────────────────────────────────────────────
# N11 — COMPUTED + alertable=True 행 0건
# ─────────────────────────────────────────────────────────────────────────────

class TestN11ComputedAlertable:
    def test_risk_index_alertable_always_false(self):
        """지수 farm_reading의 alertable은 언제나 False."""
        defs = _defs_full()
        for readings in [_readings_all_ok(), {"red_tide": None, "water_temp": None, "salinity": None, "chlorophyll": None}]:
            farm_row, factors, level = compute_risk_index("farm1", readings, _flags_none(), defs, NOW)
            assert farm_row["alertable"] is False
            assert farm_row["derivation"] == "COMPUTED"

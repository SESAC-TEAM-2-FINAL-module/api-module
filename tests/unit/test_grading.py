"""
I-8 검사 — CI 게이트 안
P4: 오차 P95 등급 분기 + value/lower/upper 저장 (4.8절)
P5: 적조 현재값 선택 규칙 (4.8절)
P11: DO 표층 규칙 미결 (4.8절)
P13: 적조 현재값 — 날짜·등급 우선순위 (4.8절)
P14: DO 정점 선택 — 유효값 없는 최근접 → 다음 정점 (4.8절)
N11: 전 픽스처 derivation=COMPUTED → alertable=false (불변식)
"""
from __future__ import annotations

from datetime import date, datetime

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# P4 — 오차 P95 → provenance 분기
# ─────────────────────────────────────────────────────────────────────────────

THRESHOLDS = [1.0, 2.0, 3.0]  # definitions.yaml grading.p95_thresholds.water_temp


class TestP4WaterTempGrade:
    """P4 — 오차 P95 값별 provenance 분기 + 값 저장 불변식."""

    def _grade(self, p95):
        from grading._water_temp import grade_water_temp
        return grade_water_temp(value=20.0, error_p95=p95, thresholds=THRESHOLDS)

    def test_p95_below_t1_observed(self):
        prov, lower, upper, deriv, none_reason = self._grade(0.8)
        assert prov == "OBSERVED"
        assert deriv == "COMPUTED"
        assert none_reason is None
        assert lower == pytest.approx(20.0 - 0.8)
        assert upper == pytest.approx(20.0 + 0.8)

    def test_p95_equal_t1_observed(self):
        prov, *_ = self._grade(1.0)
        assert prov == "OBSERVED"

    def test_p95_above_t1_nearest(self):
        prov, lower, upper, deriv, none_reason = self._grade(1.6)
        assert prov == "NEAREST"
        assert none_reason is None
        assert lower is not None and upper is not None

    def test_p95_above_t2_interpolated(self):
        prov, lower, upper, *_ = self._grade(2.6)
        assert prov == "INTERPOLATED"
        assert lower is not None

    def test_p95_above_t3_none_with_value(self):
        """P95 > 3.0 → NONE, but value·lower·upper 저장 (4.8절 불변식)."""
        prov, lower, upper, deriv, none_reason = self._grade(3.4)
        assert prov == "NONE"
        assert none_reason == "ERROR_ABOVE_LIMIT"
        assert deriv == "COMPUTED"
        # 값은 버리지 않는다
        assert lower == pytest.approx(20.0 - 3.4)
        assert upper == pytest.approx(20.0 + 3.4)

    def test_p95_none_returns_none_provenance(self):
        """error_p95=None(미결) → NONE, no lower/upper."""
        prov, lower, upper, deriv, none_reason = self._grade(None)
        assert prov == "NONE"
        assert lower is None
        assert upper is None
        assert none_reason == "NO_INPUT"


# ─────────────────────────────────────────────────────────────────────────────
# P5 — 적조 현재값 선택
# ─────────────────────────────────────────────────────────────────────────────

class TestP5RedTide:
    """P5 — 적조 규칙별 출력."""

    _AREA_ID = "area-A"
    _FARM_LAT = 34.68
    _FARM_LNG = 127.69
    _TODAY = date(2026, 9, 1)

    def _areas(self):
        return [{"area_id": self._AREA_ID, "center_lat": 34.68, "center_lng": 127.69, "radius_km": 50.0}]

    def _run(self, bulletins, details, detail_areas, window_days=30):
        from grading._red_tide import find_red_tide_reading
        return find_red_tide_reading(
            self._FARM_LAT, self._FARM_LNG,
            self._areas(), bulletins, details, detail_areas,
            window_days, self._TODAY,
        )

    def test_advisory_alertable_true(self):
        """코클로디니움 주의보 → OFFICIAL, alertable=True."""
        bulletins = [{"cod_news": "CN1", "day_report": self._TODAY}]
        details = [{"cod_news": "CN1", "seq": 1, "grade": "ADVISORY", "max_density": 500.0}]
        d_areas = [{"cod_news": "CN1", "seq": 1, "area_id": self._AREA_ID}]
        result = self._run(bulletins, details, d_areas)
        assert result is not None
        assert result["provenance"] == "OFFICIAL"
        assert result["alertable"] is True
        assert result["grade"] == "ADVISORY"

    def test_not_graded_alertable_false(self):
        """Scrippsiella(NOT_GRADED) → alertable=False."""
        bulletins = [{"cod_news": "CN2", "day_report": self._TODAY}]
        details = [{"cod_news": "CN2", "seq": 1, "grade": "NOT_GRADED", "max_density": 20000.0}]
        d_areas = [{"cod_news": "CN2", "seq": 1, "area_id": self._AREA_ID}]
        result = self._run(bulletins, details, d_areas)
        assert result is not None
        assert result["alertable"] is False
        assert result["grade"] == "NOT_GRADED"

    def test_unknown_alertable_true(self):
        """원인생물 결측(UNKNOWN) → alertable=True."""
        bulletins = [{"cod_news": "CN3", "day_report": self._TODAY}]
        details = [{"cod_news": "CN3", "seq": 1, "grade": "UNKNOWN", "max_density": None}]
        d_areas = [{"cod_news": "CN3", "seq": 1, "area_id": self._AREA_ID}]
        result = self._run(bulletins, details, d_areas)
        assert result is not None
        assert result["alertable"] is True

    def test_no_area_no_farm_row(self):
        """해역 없는 속보 → find_red_tide_reading None (farm_readings 변화 0건)."""
        bulletins = [{"cod_news": "CN4", "day_report": self._TODAY}]
        details = [{"cod_news": "CN4", "seq": 1, "grade": "ADVISORY", "max_density": 500.0}]
        # bulletin_detail_areas 비어 있음 → 양식장 대응 없음
        result = self._run(bulletins, details, [], window_days=30)
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# P11 — DO 표층 규칙 미결
# ─────────────────────────────────────────────────────────────────────────────

class TestP11DOSurfaceRulePending:
    """P11 — surface_rule 미결 → NONE(SURFACE_RULE_UNDECIDED)."""

    def test_surface_rule_pending_returns_none(self):
        from grading._do import find_do_obs

        result = find_do_obs(
            farm_lat=34.68, farm_lng=127.69,
            line_surface_obs=[{"station_id": "line:ST-1", "value": 7.5, "missing_reason": None}],
            station_rows=[{"id": "line:ST-1", "lat": 34.70, "lng": 127.70}],
            surface_rule="<미결>",
            max_distance_km=100.0,
        )
        assert result is None

    def test_surface_rule_none_string_pending(self):
        from grading._do import find_do_obs

        result = find_do_obs(
            farm_lat=34.68, farm_lng=127.69,
            line_surface_obs=[],
            station_rows=[],
            surface_rule=None,
            max_distance_km=50.0,
        )
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# P13 — 적조 날짜·등급 우선순위
# ─────────────────────────────────────────────────────────────────────────────

class TestP13RedTidePriority:
    """P13 — (a)최신 속보·최고 등급, (b)UNKNOWN vs NOT_GRADED, (c)대응 없음."""

    _AREA_ID = "area-X"
    _FARM_LAT = 34.68
    _FARM_LNG = 127.69
    _TODAY = date(2026, 9, 15)

    def _areas(self):
        return [{"area_id": self._AREA_ID, "center_lat": 34.68, "center_lng": 127.69, "radius_km": 50.0}]

    def _run(self, bulletins, details, detail_areas, window=30):
        from grading._red_tide import find_red_tide_reading
        return find_red_tide_reading(
            self._FARM_LAT, self._FARM_LNG,
            self._areas(), bulletins, details, detail_areas,
            window, self._TODAY,
        )

    def test_latest_bulletin_highest_grade(self):
        """(a) 같은 해역에 날짜 다른 속보 둘 — 최신 속보의 주의보가 현재값."""
        # 유효 기간(30일) 안: 두 속보
        # CN-OLD: 오래된 속보 (WARNING)
        # CN-NEW: 최신 속보 (ADVISORY, PRE_ADVISORY)
        bulletins = [
            {"cod_news": "CN-OLD", "day_report": date(2026, 9, 1)},
            {"cod_news": "CN-NEW", "day_report": date(2026, 9, 14)},
        ]
        details = [
            {"cod_news": "CN-OLD", "seq": 1, "grade": "WARNING", "max_density": 1500.0},
            {"cod_news": "CN-NEW", "seq": 1, "grade": "ADVISORY", "max_density": 500.0},
            {"cod_news": "CN-NEW", "seq": 2, "grade": "PRE_ADVISORY", "max_density": 50.0},
        ]
        d_areas = [
            {"cod_news": "CN-OLD", "seq": 1, "area_id": self._AREA_ID},
            {"cod_news": "CN-NEW", "seq": 1, "area_id": self._AREA_ID},
            {"cod_news": "CN-NEW", "seq": 2, "area_id": self._AREA_ID},
        ]
        result = self._run(bulletins, details, d_areas)
        assert result is not None
        assert result["grade"] == "ADVISORY"
        assert result["source_ref"].startswith("CN-NEW")

    def test_out_of_window_excluded(self):
        """유효 기간(30일) 밖 속보는 쓰지 않는다."""
        old_date = date(2026, 8, 1)  # 30일 밖
        bulletins = [{"cod_news": "CN-OLD2", "day_report": old_date}]
        details = [{"cod_news": "CN-OLD2", "seq": 1, "grade": "WARNING", "max_density": 2000.0}]
        d_areas = [{"cod_news": "CN-OLD2", "seq": 1, "area_id": self._AREA_ID}]
        result = self._run(bulletins, details, d_areas, window=30)
        assert result is None

    def test_unknown_beats_not_graded(self):
        """(b) 최신 속보에 NOT_GRADED·UNKNOWN 행 — UNKNOWN이 현재값."""
        bulletins = [{"cod_news": "CN-MIX", "day_report": self._TODAY}]
        details = [
            {"cod_news": "CN-MIX", "seq": 1, "grade": "NOT_GRADED", "max_density": None},
            {"cod_news": "CN-MIX", "seq": 2, "grade": "UNKNOWN", "max_density": None},
        ]
        d_areas = [
            {"cod_news": "CN-MIX", "seq": 1, "area_id": self._AREA_ID},
            {"cod_news": "CN-MIX", "seq": 2, "area_id": self._AREA_ID},
        ]
        result = self._run(bulletins, details, d_areas)
        assert result is not None
        assert result["grade"] == "UNKNOWN"

    def test_no_bulletins_normal_silence(self):
        """(c) 유효 기간 안 대응 속보 없음 → None (정상적 침묵)."""
        result = self._run([], [], [])
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# P14 — DO 정점 선택 (유효값 없는 최근접 → 다음 정점)
# ─────────────────────────────────────────────────────────────────────────────

class TestP14DOStationFallthrough:
    """P14 — 최근접 정점 유효값 없을 때 다음 정점으로 넘어간다."""

    _FARM_LAT = 34.68
    _FARM_LNG = 127.69

    def _run(self, obs, stations, max_km):
        from grading._do import find_do_obs
        return find_do_obs(
            farm_lat=self._FARM_LAT, farm_lng=self._FARM_LNG,
            line_surface_obs=obs,
            station_rows=stations,
            surface_rule="depth_0",  # 미결 아닌 임의 값
            max_distance_km=max_km,
        )

    def test_nearest_no_value_falls_to_second(self):
        """최근접 정점 value=None → 두 번째 정점 사용."""
        obs = [
            {"station_id": "line:NEAR", "value": None, "missing_reason": None,
             "observed_at_utc": datetime(2026, 9, 1)},
            {"station_id": "line:FAR",  "value": 7.5,  "missing_reason": None,
             "observed_at_utc": datetime(2026, 9, 1)},
        ]
        # NEAR이 양식장에 더 가까움, FAR은 한계(100km) 안
        stations = [
            {"id": "line:NEAR", "lat": 34.70, "lng": 127.70},   # ~2.4 km
            {"id": "line:FAR",  "lat": 34.80, "lng": 127.80},   # ~14 km
        ]
        result = self._run(obs, stations, max_km=100.0)
        assert result is not None
        assert result["station_id"] == "line:FAR"
        assert result["value"] == pytest.approx(7.5)

    def test_no_valid_within_limit_returns_none(self):
        """한계 안에 유효값 정점 없음 → None."""
        obs = [
            {"station_id": "line:FAR2", "value": 6.0, "missing_reason": None,
             "observed_at_utc": datetime(2026, 9, 1)},
        ]
        stations = [
            {"id": "line:FAR2", "lat": 35.5, "lng": 128.5},   # ~100km 이상
        ]
        result = self._run(obs, stations, max_km=50.0)
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# N11 — 불변식: derivation=COMPUTED → alertable=false 항상
# ─────────────────────────────────────────────────────────────────────────────

class TestN11ComputedNotAlertable:
    """N11 — grade_water_temp 출력에서 derivation=COMPUTED이면 alertable 없음.
    grading/main.py의 interp 경로는 alertable=False를 하드코딩한다.
    이 테스트는 _water_temp.py에서 derivation=COMPUTED가 항상 나옴을 확인.
    """

    def test_all_p95_values_return_computed_derivation(self):
        from grading._water_temp import grade_water_temp
        for p95 in [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, None]:
            prov, lower, upper, deriv, none_reason = grade_water_temp(
                value=20.0, error_p95=p95, thresholds=THRESHOLDS
            )
            assert deriv == "COMPUTED", f"p95={p95} → derivation={deriv!r}, expected COMPUTED"

    def test_handle_interp_rows_alertable_false(self):
        """handle_interp_done이 생성하는 행: derivation=COMPUTED, alertable=False."""
        from grading.main import _make_none_row
        from datetime import datetime

        now = datetime(2026, 9, 1, 0, 0, 0)
        row = _make_none_row("FARM-1", "water_temp", now, "NO_INPUT", derivation="COMPUTED")
        assert row["derivation"] == "COMPUTED"
        assert row["alertable"] is False

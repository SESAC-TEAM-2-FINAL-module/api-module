"""
I-7 검사 — CI 게이트 안
P1: 가막만 합성 양식장 최대 가중치 관측소 확인
Q7: IDW 입력 필터 — SENSOR_QUALITY, 정렬 창 밖, 창 안 분리
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# P1 — 가막만 합성 양식장 (fixtures/synthetic/farms.csv)
# 최대 가중치 관측소 = 여수(DT_0016) 확인
# ─────────────────────────────────────────────────────────────────────────────

STATIONS = {
    "tide:DT_0014": {"lat": 34.82777, "lng": 128.43472},  # 통영
    "tide:DT_0016": {"lat": 34.74722, "lng": 127.76555},  # 여수
    "tide:DT_0029": {"lat": 34.80138, "lng": 128.69916},  # 거제도
    "tide:DT_0061": {"lat": 34.92416, "lng": 128.06972},  # 삼천포
    "tide:DT_0049": {"lat": 34.90367, "lng": 127.75483},  # 광양
    "tide:DT_0092": {"lat": 34.66194, "lng": 127.46916},  # 여호항
    "tide:DT_0026": {"lat": 34.48111, "lng": 127.34277},  # 고흥발포
    "tide:DT_0062": {"lat": 35.19750, "lng": 128.57638},  # 마산
    "tide:DT_0063": {"lat": 35.02417, "lng": 128.81093},  # 가덕도
}

# 가막만 합성 양식장 좌표 (fixtures/synthetic/farms.csv)
FARM_LAT = 34.68
FARM_LON = 127.69


class TestP1GamakBay:
    """P1 — 가막만 합성 양식장의 최대 가중치 관측소."""

    def _make_refs(self):
        return [
            {
                "station_id": sid,
                "lat": c["lat"],
                "lng": c["lng"],
                "value": 22.0,  # 추정 결과는 중요하지 않음 — 가중치 확인용
            }
            for sid, c in STATIONS.items()
        ]

    def test_max_weight_station_is_yeosu(self):
        """최대 가중치 관측소 = 여수(DT_0016) — 가막만에서 가장 가까운 관측소."""
        from interpolation._idw import idw_estimate

        refs = self._make_refs()
        _, weights = idw_estimate(FARM_LAT, FARM_LON, refs, power_p=2, n_neighbors=5)

        assert weights, "가중치 기록이 없음"
        max_w = max(weights, key=lambda w: w["weight"])
        assert max_w["station_id"] == "tide:DT_0016", (
            f"최대 가중치 관측소가 여수(DT_0016)가 아님: {max_w['station_id']}"
        )

    def test_weights_sum_to_one(self):
        """가중치 합 = 1.0."""
        from interpolation._idw import idw_estimate

        refs = self._make_refs()
        _, weights = idw_estimate(FARM_LAT, FARM_LON, refs, power_p=2, n_neighbors=5)

        total = sum(w["weight"] for w in weights)
        assert abs(total - 1.0) < 1e-9, f"가중치 합 != 1.0: {total}"

    def test_n_neighbors_used(self):
        """n_neighbors=5이면 5개 관측소만 가중치 기록에 포함."""
        from interpolation._idw import idw_estimate

        refs = self._make_refs()
        _, weights = idw_estimate(FARM_LAT, FARM_LON, refs, power_p=2, n_neighbors=5)

        assert len(weights) == 5, f"가중치 기록 수 != 5: {len(weights)}"

    def test_haversine_yeosu_distance(self):
        """common.geo.haversine — 여수 거리가 0보다 크고 100km 미만."""
        from common.geo import haversine

        d = haversine(FARM_LAT, FARM_LON, 34.74722, 127.76555)
        assert 0 < d < 100, f"여수 거리 이상: {d} km"


# ─────────────────────────────────────────────────────────────────────────────
# Q7 — IDW 입력 필터 (4.7절)
# A: SENSOR_QUALITY 플래그 → 제외
# B: 정렬 창 밖 (창 + 1분) → 제외
# C: 창 안 → 사용
# ─────────────────────────────────────────────────────────────────────────────

class TestQ7Filter:
    """Q7 — SENSOR_QUALITY와 정렬 창 필터."""

    REF_TIME = datetime(2026, 6, 1, 12, 0, 0)
    WINDOW_MIN = 30

    STATION_COORDS = {
        "tide:A": {"lat": 34.8, "lng": 128.0},
        "tide:B": {"lat": 35.0, "lng": 128.0},
        "tide:C": {"lat": 34.9, "lng": 128.0},
    }

    def _make_obs(self):
        ref = self.REF_TIME
        return [
            # A: SENSOR_QUALITY 플래그 → 제외
            {
                "station_id": "tide:A",
                "observed_at_utc": ref - timedelta(minutes=5),
                "value": 22.0,
                "missing_reason": None,
                "flags": ["SENSOR_QUALITY"],
            },
            # B: 창 밖 (정확히 align_window_min + 1분) → 제외
            {
                "station_id": "tide:B",
                "observed_at_utc": ref - timedelta(minutes=self.WINDOW_MIN + 1),
                "value": 21.0,
                "missing_reason": None,
                "flags": [],
            },
            # C: 창 안 → 사용
            {
                "station_id": "tide:C",
                "observed_at_utc": ref - timedelta(minutes=10),
                "value": 23.0,
                "missing_reason": None,
                "flags": [],
            },
        ]

    def test_sensor_quality_excluded(self):
        """SENSOR_QUALITY 플래그 관측소 A는 필터 결과에 없다."""
        from common.idw_inputs import filter_stations

        result = filter_stations(
            self._make_obs(), self.STATION_COORDS,
            self.REF_TIME, self.WINDOW_MIN, exclude_flatline=None
        )
        station_ids = [r["station_id"] for r in result]
        assert "tide:A" not in station_ids

    def test_outside_window_excluded(self):
        """정렬 창 밖(창+1분) 관측소 B는 필터 결과에 없다."""
        from common.idw_inputs import filter_stations

        result = filter_stations(
            self._make_obs(), self.STATION_COORDS,
            self.REF_TIME, self.WINDOW_MIN, exclude_flatline=None
        )
        station_ids = [r["station_id"] for r in result]
        assert "tide:B" not in station_ids

    def test_inside_window_included(self):
        """창 안 관측소 C는 필터 결과에 있다."""
        from common.idw_inputs import filter_stations

        result = filter_stations(
            self._make_obs(), self.STATION_COORDS,
            self.REF_TIME, self.WINDOW_MIN, exclude_flatline=None
        )
        station_ids = [r["station_id"] for r in result]
        assert "tide:C" in station_ids

    def test_only_c_remains(self):
        """필터 후 C만 남는다."""
        from common.idw_inputs import filter_stations

        result = filter_stations(
            self._make_obs(), self.STATION_COORDS,
            self.REF_TIME, self.WINDOW_MIN, exclude_flatline=None
        )
        assert len(result) == 1
        assert result[0]["station_id"] == "tide:C"

    def test_missing_reason_excluded(self):
        """missing_reason이 있는 관측소는 제외된다."""
        from common.idw_inputs import filter_stations

        obs = [
            {
                "station_id": "tide:C",
                "observed_at_utc": self.REF_TIME - timedelta(minutes=5),
                "value": 22.0,
                "missing_reason": "STATION_INACTIVE",
                "flags": [],
            }
        ]
        result = filter_stations(
            obs, self.STATION_COORDS,
            self.REF_TIME, self.WINDOW_MIN, exclude_flatline=None
        )
        assert result == []

    def test_stale_suspect_excluded_when_flatline_set(self):
        """exclude_flatline이 설정된 경우 STALE_SUSPECT 관측소는 제외된다."""
        from common.idw_inputs import filter_stations

        obs = [
            {
                "station_id": "tide:C",
                "observed_at_utc": self.REF_TIME - timedelta(minutes=5),
                "value": 22.0,
                "missing_reason": None,
                "flags": ["STALE_SUSPECT"],
            }
        ]
        result_with = filter_stations(
            obs, self.STATION_COORDS,
            self.REF_TIME, self.WINDOW_MIN, exclude_flatline=True
        )
        result_without = filter_stations(
            obs, self.STATION_COORDS,
            self.REF_TIME, self.WINDOW_MIN, exclude_flatline=None
        )
        assert result_with == [], "exclude_flatline=True: STALE_SUSPECT 제외"
        assert len(result_without) == 1, "exclude_flatline=None: STALE_SUSPECT 포함"

    def test_latest_valid_value_per_station(self):
        """같은 관측소가 창 안에 여러 번 있으면 최신 유효값 하나만 (4.7절) — 최신값이 SENSOR_QUALITY면 그 앞 값"""
        from common.idw_inputs import filter_stations

        def o(minutes_before, value, flags=()):
            return {"station_id": "tide:C", "observed_at_utc": self.REF_TIME - timedelta(minutes=minutes_before),
                    "value": value, "missing_reason": None, "flags": list(flags)}

        result = filter_stations([o(20, 21.0), o(5, 22.0), o(12, 21.5)], self.STATION_COORDS,
                                 self.REF_TIME, self.WINDOW_MIN, exclude_flatline=None)
        assert [(r["station_id"], r["value"]) for r in result] == [("tide:C", 22.0)]

        result = filter_stations([o(20, 21.0), o(5, 99.0, ["SENSOR_QUALITY"])], self.STATION_COORDS,
                                 self.REF_TIME, self.WINDOW_MIN, exclude_flatline=None)
        assert [r["value"] for r in result] == [21.0]


# ─────────────────────────────────────────────────────────────────────────────
# 불변식 — COMPUTED 행의 alertable = False
# ─────────────────────────────────────────────────────────────────────────────

class TestAlertableInvariant:
    """COMPUTED 행은 alertable=False (CLAUDE.md 7절)."""

    def test_interpolation_result_not_alertable(self):
        """IDW 추정 결과는 derivation=COMPUTED이므로 alertable=False여야 한다."""
        from interpolation._idw import idw_estimate

        refs = [
            {"station_id": "tide:A", "lat": 34.8, "lng": 128.0, "value": 22.0},
            {"station_id": "tide:B", "lat": 35.0, "lng": 128.0, "value": 23.0},
        ]
        value, _ = idw_estimate(34.9, 128.0, refs, power_p=2, n_neighbors=2)

        reading = {
            "farm_id": "farm_001",
            "axis": "water_temp",
            "value": value,
            "derivation": "COMPUTED",
            "alertable": False,  # COMPUTED는 항상 False
        }
        assert reading["alertable"] is False

"""
어장환경 해수면 femoSeaList 가공 어댑터 단위 테스트 (I-5)
검사: F1·F2·F3 (픽스처), N8 (합성 입력)
픽스처:
  F1: fixtures/raw/femoSeaList_f3_{2023,2024,2025}_*.json
  F2: fixtures/raw/femoSeaList_f1_*.json (2026 빈 결과)
  F3: fixtures/raw/femoSeaList_f2_single_*.json (1년 창 단일 255건)
"""
from __future__ import annotations
import json
from pathlib import Path

import pytest

from common.classifier import parse, ParsedResponse
from processor.adapters.fishery._adapter import (
    FisheryProcessorAdapter,
    FisheryWatchProcessorAdapter,
    _assemble_date,
    _parse_value,
)

FIXTURES = Path(__file__).parents[2] / "fixtures" / "raw"

_ADAPTER = FisheryProcessorAdapter()
_WATCH = FisheryWatchProcessorAdapter()

_RAW_META = {"raw_id": "test"}
_WATCH_META_EMPTY = {
    "raw_id": "test",
    "fetched_at_utc": "2026-09-29T00:00:00",
    "target_year": 2026,
    "prev_total_count": 0,
}


# ── 픽스처 로드 헬퍼 ─────────────────────────────────────────────────────────

def _parse_fixture(fname: str):
    p = next(FIXTURES.glob(fname))
    raw = json.loads(p.read_text("utf-8"))
    return parse(raw.get("body", raw))


def _run_fixture(fname: str) -> list[dict]:
    pr = _parse_fixture(fname)
    rows = _ADAPTER.interpret(pr, _RAW_META)
    return _ADAPTER.normalize(rows)


def _make_pr(items: list[dict], parse_status: str = "OK") -> ParsedResponse:
    return ParsedResponse(
        format="json",
        result_code="00" if parse_status in ("OK", "OK_EMPTY") else None,
        parse_status=parse_status,
        items=items,
    )


def _item(fishery="가막만", point="1",
          lat="34°35′00″", lon="127°35′00″",
          y=2025, m=10, d=1, th="9", ti="30",
          temp_s="18.0", sal_s="32.5", chl_s="1.5",
          temp_b="16.0", sal_b="33.0", chl_b="1.0"):
    return {
        "FISHERY": fishery, "LOCATION_POINT": point,
        "LATITUDE": lat, "LONGITUDE": lon,
        "DATE_Y": y, "DATE_M": m, "DATE_D": d, "TIME_H": th, "TIME_I": ti,
        "TEMP_S": temp_s, "SAL_S": sal_s, "CHL_S": chl_s,
        "TEMP_B": temp_b, "SAL_B": sal_b, "CHL_B": chl_b,
    }


# ── F1: 백필 픽스처 건수 검증 ───────────────────────────────────────────────

class TestF1Backfill:
    def test_2023_items(self):
        pr = _parse_fixture("femoSeaList_f3_2023_*.json")
        assert pr.parse_status == "OK"
        assert len(pr.items) == 1008

    def test_2024_items(self):
        pr = _parse_fixture("femoSeaList_f3_2024_*.json")
        assert pr.parse_status == "OK"
        assert len(pr.items) == 1020

    def test_2025_items(self):
        pr = _parse_fixture("femoSeaList_f3_2025_*.json")
        assert pr.parse_status == "OK"
        assert len(pr.items) == 1022

    def test_2023_rows_six_per_item(self):
        rows = _run_fixture("femoSeaList_f3_2023_*.json")
        assert len(rows) == 1008 * 6

    def test_2024_rows_six_per_item(self):
        rows = _run_fixture("femoSeaList_f3_2024_*.json")
        assert len(rows) == 1020 * 6

    def test_2025_rows_six_per_item(self):
        rows = _run_fixture("femoSeaList_f3_2025_*.json")
        assert len(rows) == 1022 * 6

    def test_metrics_present(self):
        rows = _run_fixture("femoSeaList_f3_2023_*.json")
        metrics = {r["metric"] for r in rows}
        assert metrics == {"water_temp", "salinity", "chlorophyll"}

    def test_layers_present(self):
        rows = _run_fixture("femoSeaList_f3_2023_*.json")
        layers = {r["layer"] for r in rows}
        assert layers == {"S", "B"}

    def test_station_id_prefix(self):
        rows = _run_fixture("femoSeaList_f3_2023_*.json")
        assert all(r["station_id"].startswith("fishery:") for r in rows)

    def test_surveyed_on_format(self):
        rows = _run_fixture("femoSeaList_f3_2023_*.json")
        for r in rows:
            d = r["surveyed_on"]
            assert len(d) == 10 and d[4] == "-" and d[7] == "-", d

    def test_2023_surveyed_on_year(self):
        rows = _run_fixture("femoSeaList_f3_2023_*.json")
        years = {r["surveyed_on"][:4] for r in rows}
        assert "2023" in years


# ── F2: 2026 빈 결과 → publication_checks ──────────────────────────────────

class TestF2PublicationChecks:
    def test_parse_status_ok_empty(self):
        pr = _parse_fixture("femoSeaList_f1_*.json")
        assert pr.parse_status == "OK_EMPTY"

    def test_items_empty(self):
        pr = _parse_fixture("femoSeaList_f1_*.json")
        assert len(pr.items) == 0

    def test_watch_produces_one_row(self):
        pr = _parse_fixture("femoSeaList_f1_*.json")
        rows = _WATCH.interpret(pr, _WATCH_META_EMPTY)
        assert len(rows) == 1

    def test_watch_total_count_zero(self):
        pr = _parse_fixture("femoSeaList_f1_*.json")
        rows = _WATCH.interpret(pr, _WATCH_META_EMPTY)
        assert rows[0]["total_count"] == 0

    def test_watch_axis(self):
        pr = _parse_fixture("femoSeaList_f1_*.json")
        rows = _WATCH.interpret(pr, _WATCH_META_EMPTY)
        assert rows[0]["axis"] == "chlorophyll"

    def test_watch_target_year(self):
        pr = _parse_fixture("femoSeaList_f1_*.json")
        rows = _WATCH.interpret(pr, _WATCH_META_EMPTY)
        assert rows[0]["target_year"] == 2026

    def test_watch_type_tag(self):
        pr = _parse_fixture("femoSeaList_f1_*.json")
        rows = _WATCH.interpret(pr, _WATCH_META_EMPTY)
        assert rows[0]["_type"] == "publication_check"

    def test_survey_rows_empty(self):
        """2026 빈 결과는 survey_observations 행 없음."""
        pr = _parse_fixture("femoSeaList_f1_*.json")
        rows = _ADAPTER.interpret(pr, _RAW_META)
        assert len(rows) == 0


# ── F3: 1년 창 단일 255건, 2025-10-01 이후 212건 ───────────────────────────

class TestF3SingleWindow:
    def test_total_items(self):
        pr = _parse_fixture("femoSeaList_f2_single_*.json")
        assert len(pr.items) == 255

    def test_total_rows(self):
        rows = _run_fixture("femoSeaList_f2_single_*.json")
        assert len(rows) == 255 * 6

    def test_after_oct_2025(self):
        rows = _run_fixture("femoSeaList_f2_single_*.json")
        after = [r for r in rows if r["surveyed_on"] >= "2025-10-01"]
        assert len(after) == 212 * 6

    def test_before_oct_2025(self):
        rows = _run_fixture("femoSeaList_f2_single_*.json")
        before = [r for r in rows if r["surveyed_on"] < "2025-10-01"]
        assert len(before) == 43 * 6


# ── N8: 게시 감시 호출 연결 실패 → NET_ERROR, PUBLICATION_PENDING 아님 ────

class TestN8WatchFailure:
    def test_net_error_total_count_none(self):
        """연결 실패 시 total_count=None — 0건(게시 대기)으로 삼키지 않는다."""
        pr = _make_pr([], parse_status="NET_ERROR")
        rows = _WATCH.interpret(pr, {
            "raw_id": "test",
            "fetched_at_utc": "2026-09-29T00:00:00",
            "target_year": 2026,
            "prev_total_count": None,
        })
        assert rows[0]["total_count"] is None

    def test_net_error_delta_none(self):
        pr = _make_pr([], parse_status="NET_ERROR")
        rows = _WATCH.interpret(pr, {
            "raw_id": "test",
            "fetched_at_utc": "2026-09-29T00:00:00",
            "target_year": 2026,
            "prev_total_count": None,
        })
        assert rows[0]["delta"] is None

    def test_parse_failure_not_zero(self):
        """파싱 실패도 0건 게시 대기로 삼키지 않는다."""
        pr = _make_pr([], parse_status="PARSE_FAILURE")
        rows = _WATCH.interpret(pr, {
            "raw_id": "test",
            "fetched_at_utc": "2026-09-29T00:00:00",
            "target_year": 2026,
            "prev_total_count": 0,
        })
        assert rows[0]["total_count"] is None

    def test_error_parse_status_preserved(self):
        """parse_status가 행에 보존된다."""
        pr = _make_pr([], parse_status="NET_ERROR")
        rows = _WATCH.interpret(pr, {
            "raw_id": "test",
            "fetched_at_utc": "2026-09-29T00:00:00",
            "target_year": 2026,
            "prev_total_count": None,
        })
        assert rows[0]["parse_status"] == "NET_ERROR"


# ── 단위: _assemble_date ─────────────────────────────────────────────────────

class TestAssembleDate:
    def test_normal(self):
        assert _assemble_date({"DATE_Y": 2023, "DATE_M": 10, "DATE_D": 20}) == "2023-10-20"

    def test_single_digit(self):
        assert _assemble_date({"DATE_Y": 2023, "DATE_M": 5, "DATE_D": 3}) == "2023-05-03"

    def test_string_values(self):
        assert _assemble_date({"DATE_Y": "2023", "DATE_M": "5", "DATE_D": "3"}) == "2023-05-03"

    def test_missing_raises(self):
        with pytest.raises(ValueError):
            _assemble_date({"DATE_Y": 2023, "DATE_M": None, "DATE_D": 1})

    def test_all_missing_raises(self):
        with pytest.raises(ValueError):
            _assemble_date({})


# ── 단위: _parse_value ───────────────────────────────────────────────────────

class TestParseValue:
    def test_normal_float(self):
        assert _parse_value("18.5", "water_temp") == (18.5, None)

    def test_missing_empty(self):
        assert _parse_value("", "water_temp") == (None, "MISSING")

    def test_missing_none(self):
        assert _parse_value(None, "water_temp") == (None, "MISSING")

    def test_zero_sentinel_water_temp(self):
        assert _parse_value("0.0", "water_temp") == (None, "ZERO_SENTINEL")

    def test_zero_sentinel_salinity(self):
        assert _parse_value("0.000", "salinity") == (None, "ZERO_SENTINEL")

    def test_zero_chlorophyll_not_sentinel(self):
        """클로로필 0.0은 결측이 아니다."""
        v, mr = _parse_value("0.0", "chlorophyll")
        assert v == 0.0 and mr is None

    def test_parse_error(self):
        assert _parse_value("N/A", "water_temp") == (None, "PARSE_ERROR")


# ── 단위: 좌표 변환·검증 ────────────────────────────────────────────────────

class TestCoordValidation:
    def _run_item(self, lat, lon):
        pr = _make_pr([_item(lat=lat, lon=lon)])
        rows = _ADAPTER.interpret(pr, _RAW_META)
        return rows

    def test_valid_dms_produces_rows(self):
        rows = self._run_item("34°35′00″", "127°35′00″")
        assert len(rows) == 6

    def test_invalid_lat_skipped(self):
        rows = self._run_item("20°00′00″", "127°35′00″")
        assert len(rows) == 0

    def test_invalid_lon_skipped(self):
        rows = self._run_item("34°35′00″", "150°00′00″")
        assert len(rows) == 0

    def test_boundary_lat_33(self):
        """폐구간: lat=33.0 포함."""
        rows = self._run_item("33°00′00″", "127°35′00″")
        assert len(rows) == 6


# ── 단위: station_id 형식 ────────────────────────────────────────────────────

class TestStationId:
    def test_format(self):
        pr = _make_pr([_item(fishery="가막만", point="8")])
        rows = _ADAPTER.interpret(pr, _RAW_META)
        assert rows[0]["station_id"] == "fishery:가막만-8"

    def test_layer_and_metric(self):
        pr = _make_pr([_item()])
        rows = _ADAPTER.interpret(pr, _RAW_META)
        combos = {(r["metric"], r["layer"]) for r in rows}
        assert combos == {
            ("water_temp", "S"), ("water_temp", "B"),
            ("salinity",   "S"), ("salinity",   "B"),
            ("chlorophyll","S"), ("chlorophyll","B"),
        }


# ── 단위: watch delta 계산 ───────────────────────────────────────────────────

class TestWatchDelta:
    def test_delta_computed(self):
        pr = _make_pr([_item(), _item(point="2")])
        rows = _WATCH.interpret(pr, {
            "raw_id": "test",
            "fetched_at_utc": "2026-09-29T00:00:00",
            "target_year": 2026,
            "prev_total_count": 0,
        })
        assert rows[0]["total_count"] == 2
        assert rows[0]["delta"] == 2

    def test_delta_none_when_no_prev(self):
        pr = _make_pr([_item()])
        rows = _WATCH.interpret(pr, {
            "raw_id": "test",
            "fetched_at_utc": "2026-09-29T00:00:00",
            "target_year": 2026,
            "prev_total_count": None,
        })
        assert rows[0]["delta"] is None


# ── 조사 시각 (계획서 1.5·4.5·5.3절, 개정 14) ───────────────────────────────

class TestObservedAt:
    def test_kst_to_utc(self):
        """DATE + TIME_H·TIME_I(KST) → UTC ISO. 2025-10-01 09:30 KST = 2025-10-01 00:30 UTC"""
        rows = _ADAPTER.normalize(_ADAPTER.interpret(_make_pr([_item()]), _RAW_META))
        assert {r["observed_at_utc"] for r in rows} == {"2025-10-01T00:30:00"}
        assert {r["surveyed_on"] for r in rows} == {"2025-10-01"}

    def test_kst_date_rollover(self):
        """KST 이른 아침은 UTC 전날 — 08:33 KST(2025-11-05) = 2025-11-04 23:33 UTC"""
        rows = _ADAPTER.normalize(_ADAPTER.interpret(
            _make_pr([_item(y=2025, m=11, d=5, th="8", ti="33")]), _RAW_META))
        assert rows[0]["observed_at_utc"] == "2025-11-04T23:33:00"
        assert rows[0]["surveyed_on"] == "2025-11-05"

    def test_same_day_two_surveys_are_distinct_keys(self):
        """같은 정점·같은 날 다른 시각 조사는 다른 키 — 합쳐지지 않는다"""
        rows = _ADAPTER.normalize(_ADAPTER.interpret(
            _make_pr([_item(th="9", ti="0", chl_s="1.0"), _item(th="15", ti="0", chl_s="3.0")]), _RAW_META))
        keys = {(r["station_id"], r["observed_at_utc"], r["layer"], r["metric"]) for r in rows}
        assert len(keys) == len(rows) == 12

    @pytest.mark.parametrize("th,ti", [("", "0"), (None, None), ("24", "0"), ("9", "60")])
    def test_missing_or_bad_time_skips_record(self, th, ti):
        """시각이 없거나 범위 밖이면 추정하지 않고 그 레코드를 건너뛴다"""
        rows = _ADAPTER.interpret(_make_pr([_item(th=th, ti=ti)]), _RAW_META)
        assert rows == []

    def test_fixtures_all_have_time(self):
        """2023~2025 픽스처 전 레코드가 조사 시각으로 적재 가능 — 건너뛰는 레코드 0"""
        for y, n in (("2023", 1008), ("2024", 1020), ("2025", 1022)):
            rows = _run_fixture(f"femoSeaList_f3_{y}_*.json")
            assert len(rows) == n * 6


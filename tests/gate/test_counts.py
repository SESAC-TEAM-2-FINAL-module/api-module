"""
② 건수 보존 — 계획서 7.7절.
저장소 안 원문 픽스처(F1~F10)를 파이프라인에 통과시키고 단계마다 건수를 대조.
기준값: ci/gate/expected.yaml counts 섹션.

실행: pytest tests/gate/test_counts.py -v
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

FIXTURES = Path(__file__).parents[2] / "fixtures" / "raw"
EXPECTED_PATH = Path(__file__).parents[2] / "ci" / "gate" / "expected.yaml"

# 어댑터 상수 — 각 관측 레코드당 생성되는 metric 행 수
_FISHERY_METRICS_PER_OBS = 6   # TEMP_S/B · SAL_S/B · CHL_S/B
_LINE_METRICS_PER_REC = 3       # wtr_tmp · sal · dox


@pytest.fixture(scope="module")
def expected() -> dict:
    return yaml.safe_load(EXPECTED_PATH.read_text(encoding="utf-8"))["counts"]


def _parse_body(fname_glob: str):
    from common.classifier import parse

    path = next(FIXTURES.glob(fname_glob))
    raw = json.loads(path.read_text("utf-8"))
    return parse(raw.get("body", raw))


def _fishery_rows(fname_glob: str) -> tuple[object, list[dict]]:
    """(ParsedResponse, normalize된 행 목록) 반환."""
    from processor.adapters.fishery._adapter import FisheryProcessorAdapter

    pr = _parse_body(fname_glob)
    adapter = FisheryProcessorAdapter()
    rows_i = adapter.interpret(pr, {"raw_id": "gate"})
    return pr, adapter.normalize(rows_i)


def _line_rows() -> tuple[object, list[dict]]:
    """(ParsedResponse, normalize된 행 목록) 반환."""
    from processor.adapters.line._adapter import LineProcessorAdapter

    pr = _parse_body("sooList_depth_*.json")
    adapter = LineProcessorAdapter()
    rows_i = adapter.interpret(pr, {"raw_id": "gate"})
    return pr, adapter.normalize(rows_i)


# ── 어장환경 건수 ─────────────────────────────────────────────────────────────


class TestFemoCountsYear:
    """femo_2023·2024·2025 — raw(원문 항목 수) == stored(좌표·날짜 검증 통과 관측 수)."""

    @pytest.mark.parametrize("year,key", [
        ("2023", "femo_2023"),
        ("2024", "femo_2024"),
        ("2025", "femo_2025"),
    ])
    def test_raw_count(self, year: str, key: str, expected: dict):
        pr, _ = _fishery_rows(f"femoSeaList_f3_{year}_*.json")
        assert len(pr.items) == expected[key]["raw"], (
            f"{key}: raw 기대={expected[key]['raw']}, 실제={len(pr.items)}"
        )

    @pytest.mark.parametrize("year,key", [
        ("2023", "femo_2023"),
        ("2024", "femo_2024"),
        ("2025", "femo_2025"),
    ])
    def test_stored_obs_count(self, year: str, key: str, expected: dict):
        """좌표·날짜 검증 통과 후 적재 관측 수 = normalize 행수 ÷ _FISHERY_METRICS_PER_OBS."""
        _, rows = _fishery_rows(f"femoSeaList_f3_{year}_*.json")
        stored = len(rows) // _FISHERY_METRICS_PER_OBS
        assert stored == expected[key]["stored"], (
            f"{key}: stored 기대={expected[key]['stored']}, 실제={stored}"
        )

    @pytest.mark.parametrize("year,key", [
        ("2023", "femo_2023"),
        ("2024", "femo_2024"),
        ("2025", "femo_2025"),
    ])
    def test_raw_equals_stored(self, year: str, key: str, expected: dict):
        exp = expected[key]
        assert exp["raw"] == exp["stored"], (
            f"{key}: raw({exp['raw']}) != stored({exp['stored']}) — 기준 문서 자체 확인"
        )


class TestFemo2026Empty:
    """femo_2026 — OK_EMPTY + publication_check_rows=1."""

    @pytest.fixture(scope="class")
    def pr_2026(self):
        from common.classifier import parse

        path = next(FIXTURES.glob("femoSeaList_f1_*.json"))
        raw = json.loads(path.read_text("utf-8"))
        return parse(raw.get("body", raw))

    def test_status_ok_empty(self, pr_2026):
        assert pr_2026.parse_status == "OK_EMPTY", (
            f"기대=OK_EMPTY, 실제={pr_2026.parse_status}"
        )

    def test_raw_zero(self, pr_2026, expected: dict):
        assert len(pr_2026.items) == expected["femo_2026"]["raw"]

    def test_publication_check_rows(self, pr_2026, expected: dict):
        """게시 감시 픽스처 — 1행 생성 (FisheryWatchProcessorAdapter)."""
        from processor.adapters.fishery._adapter import FisheryWatchProcessorAdapter

        adapter = FisheryWatchProcessorAdapter()
        rows = adapter.interpret(pr_2026, {
            "raw_id": "gate",
            "fetched_at_utc": "2026-01-01T00:00:00",
            "target_year": 2026,
            "prev_total_count": 0,
        })
        result = adapter.normalize(rows)
        pub_checks = [r for r in result if r.get("_type") == "publication_check"]
        assert len(pub_checks) == expected["femo_2026"]["publication_check_rows"]


# ── 적조 건수 ─────────────────────────────────────────────────────────────────


def _bulletin_rows(fname_glob: str) -> list[dict]:
    from processor.adapters.bulletin._adapter import BulletinProcessorAdapter

    path = next(FIXTURES.glob(fname_glob))
    raw = json.loads(path.read_text("utf-8"))
    from common.classifier import parse

    pr = parse(raw.get("body", raw))
    adapter = BulletinProcessorAdapter()
    rows = adapter.interpret(pr, {"raw_id": "gate"})
    return adapter.normalize(rows)


def _by_type(rows: list[dict], t: str) -> list[dict]:
    return [r for r in rows if r.get("_type") == t]


class TestRedtideR1:
    """redtide_r1 — 51 속보, 50 세부 행, 45 코클로디니움, item2 없는 속보 1건."""

    @pytest.fixture(scope="class")
    def rows(self):
        return _bulletin_rows("redtideList_r1_*.json")

    def test_bulletins_count(self, rows, expected: dict):
        exp = expected["redtide_r1"]
        bulletins = _by_type(rows, "bulletin")
        assert len(bulletins) == exp["stored_bulletins"], (
            f"bulletins: 기대={exp['stored_bulletins']}, 실제={len(bulletins)}"
        )

    def test_outer_count(self, rows, expected: dict):
        exp = expected["redtide_r1"]
        bulletins = _by_type(rows, "bulletin")
        assert len(bulletins) == exp["outer"]

    def test_details_count(self, rows, expected: dict):
        exp = expected["redtide_r1"]
        details = _by_type(rows, "bulletin_detail")
        assert len(details) == exp["details"]

    def test_cochlodinium_count(self, rows, expected: dict):
        exp = expected["redtide_r1"]
        from processor.adapters.bulletin._adapter import SC_TARGET

        coch = [
            d for d in _by_type(rows, "bulletin_detail")
            if d.get("species_class") == SC_TARGET
        ]
        assert len(coch) == exp["cochlodinium"]

    def test_item2_missing_unknown(self, rows, expected: dict):
        exp = expected["redtide_r1"]
        no_detail = [
            b for b in _by_type(rows, "bulletin")
            if b.get("detail_count", 0) == 0
        ]
        assert len(no_detail) == exp["item2_missing_unknown"]


class TestRedtideR3:
    """redtide_r3 — 15 속보, 10 NOT_GRADED, 20 detail_area_parts."""

    @pytest.fixture(scope="class")
    def rows(self):
        return _bulletin_rows("redtideList_r3_*.json")

    def test_outer_count(self, rows, expected: dict):
        exp = expected["redtide_r3"]
        bulletins = _by_type(rows, "bulletin")
        assert len(bulletins) == exp["outer"]

    def test_not_graded_count(self, rows, expected: dict):
        exp = expected["redtide_r3"]
        from processor.adapters.bulletin._adapter import SC_NON_TARGET

        not_graded = [
            d for d in _by_type(rows, "bulletin_detail")
            if d.get("species_class") == SC_NON_TARGET
        ]
        assert len(not_graded) == exp["not_graded"]

    def test_detail_area_parts(self, rows, expected: dict):
        exp = expected["redtide_r3"]
        areas = _by_type(rows, "bulletin_detail_area")
        assert len(areas) == exp["detail_area_parts"]


class TestRedtideAll:
    """redtide_all — R1 + R3 합산 unique_day_report."""

    def test_unique_day_report(self, expected: dict):
        r1 = _bulletin_rows("redtideList_r1_*.json")
        r3 = _bulletin_rows("redtideList_r3_*.json")
        all_bulletins = _by_type(r1, "bulletin") + _by_type(r3, "bulletin")
        unique_days = len({b["day_report"] for b in all_bulletins})
        assert unique_days == expected["redtide_all"]["unique_day_report"]


# ── 정선 건수 ─────────────────────────────────────────────────────────────────


class TestSooV2:
    """soo_v2 — 10445 raw, 523 lat33 kept, 1029 coord_excluded.

    남해/empty_dropped 집계는 어댑터가 _region 메타를 미노출 — 계획서 반영 후보.
    """

    @pytest.fixture(scope="class")
    def soo(self):
        return _line_rows()   # (pr, rows)

    def test_raw_total(self, soo, expected: dict):
        pr, _ = soo
        exp = expected["soo_v2"]
        assert len(pr.items) == exp["raw"], (
            f"soo_v2 raw: 기대={exp['raw']}, 실제={len(pr.items)}"
        )

    def test_south_count(self, soo, expected: dict):
        """어댑터가 _region 메타를 제공하지 않아 건너뜀 — 계획서 반영 후보."""
        pytest.skip("어댑터가 _region 메타를 제공하지 않음 — 계획서 반영 후보")

    def test_south_lat33_kept(self, soo, expected: dict):
        """lat==33.0 이고 좌표 검증 통과 레코드 수 — pr.items에서 직접 집계."""
        from common.geo import validate_coords_closed
        from common.config import load_definitions

        pr, _ = soo
        exp = expected["soo_v2"]
        defs = load_definitions()
        lat_range = tuple(defs["geo"]["lat_range"])
        lng_range = tuple(defs["geo"]["lng_range"])

        count = 0
        for r in pr.items:
            try:
                lat = float(r.get("lat") or "")
                lng = float(r.get("lon") or "")
            except (ValueError, TypeError):
                continue
            if abs(lat - 33.0) < 1e-9 and validate_coords_closed(lat, lng, lat_range, lng_range):
                count += 1

        assert count == exp["south_lat33_kept"], (
            f"lat33_kept: 기대={exp['south_lat33_kept']}, 실제={count}"
        )

    def test_empty_value_dropped(self, soo, expected: dict):
        """남해 한정 집계 — 어댑터가 _region 미노출로 건너뜀 — 계획서 반영 후보."""
        pytest.skip("어댑터가 _region 메타를 제공하지 않음 — 계획서 반영 후보")

    def test_coord_excluded(self, soo, expected: dict):
        """좌표 범위 밖 레코드 수 = raw - (normalize 행수 ÷ _LINE_METRICS_PER_REC)."""
        pr, rows = soo
        exp = expected["soo_v2"]
        coord_excluded = len(pr.items) - len(rows) // _LINE_METRICS_PER_REC
        assert coord_excluded == exp["coord_excluded"], (
            f"coord_excluded: 기대={exp['coord_excluded']}, 실제={coord_excluded}"
        )

"""
bulletin 가공 어댑터 단위 테스트 (I-3)
검사: F7·F8·F9·F10·N10 (SKILL.md ⑥)
픽스처: fixtures/raw/redtideList_r1_* (51건) · _r3_* (15건)
"""
from __future__ import annotations
import json
from pathlib import Path

import pytest

from processor.adapters.bulletin._adapter import (
    BulletinProcessorAdapter,
    SC_TARGET,
    SC_NON_TARGET,
    SC_MISSING,
    _is_target_species,
    _determine_grade,
    _normalize_txt_seas_1_3,
    _split_txt_seas_4_5,
    _parse_density,
)

FIXTURES = Path(__file__).parents[2] / "fixtures" / "raw"
R1 = FIXTURES / "redtideList_r1_1790125808264.json"
R3 = FIXTURES / "redtideList_r3_1790125809859.json"


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────


def _parse_fixture(path: Path):
    from common.classifier import parse
    raw = json.loads(path.read_text("utf-8"))
    return parse(raw["body"])


def _run(path: Path) -> list[dict]:
    adapter = BulletinProcessorAdapter()
    pr = _parse_fixture(path)
    rows = adapter.interpret(pr, {"raw_id": "test"})
    return adapter.normalize(rows)


def _by_type(rows: list[dict], t: str) -> list[dict]:
    return [r for r in rows if r["_type"] == t]


# ── F7: R1 기본 건수·item2 없는 속보 ─────────────────────────────────────────


class TestF7:
    @pytest.fixture(scope="class")
    def rows(self):
        return _run(R1)

    def test_bulletins_count(self, rows):
        assert len(_by_type(rows, "bulletin")) == 51

    def test_bulletin_details_count(self, rows):
        assert len(_by_type(rows, "bulletin_detail")) == 50

    def test_item2_missing_bulletin_preserved(self, rows):
        """item2 없는 속보(20250924-001)가 bulletins에 1행 보관됨."""
        no_detail = [
            b for b in _by_type(rows, "bulletin")
            if b["detail_count"] == 0
        ]
        assert len(no_detail) == 1
        assert no_detail[0]["cod_news"] == "20250924-001"

    def test_item2_missing_grade_unknown(self, rows):
        """item2 없는 속보 grade=UNKNOWN (SKILL.md ③-4 1단계)."""
        b = next(
            b for b in _by_type(rows, "bulletin")
            if b["cod_news"] == "20250924-001"
        )
        assert b["grade"] == "UNKNOWN"


# ── F8: R1 종별·등급 카운트 ──────────────────────────────────────────────────


class TestF8:
    @pytest.fixture(scope="class")
    def rows(self):
        return _run(R1)

    def test_species_class_target_count(self, rows):
        details = _by_type(rows, "bulletin_detail")
        assert len([d for d in details if d["species_class"] == SC_TARGET]) == 45

    def test_species_class_non_target_count(self, rows):
        """Scrippsiella 2 · Akashiwo 2 · Mesodinium 1 = 5건 NON_TARGET."""
        details = _by_type(rows, "bulletin_detail")
        assert len([d for d in details if d["species_class"] == SC_NON_TARGET]) == 5

    def test_cochlodinium_pre_advisory(self, rows):
        """코클로디니움: 10~99 → PRE_ADVISORY 10건."""
        cochl = [
            d for d in _by_type(rows, "bulletin_detail")
            if d["species_class"] == SC_TARGET
        ]
        assert len([d for d in cochl if d["grade"] == "PRE_ADVISORY"]) == 10

    def test_cochlodinium_advisory(self, rows):
        """코클로디니움: 100~999 → ADVISORY 2건."""
        cochl = [
            d for d in _by_type(rows, "bulletin_detail")
            if d["species_class"] == SC_TARGET
        ]
        assert len([d for d in cochl if d["grade"] == "ADVISORY"]) == 2

    def test_cochlodinium_warning(self, rows):
        """코클로디니움: 1000+ → WARNING 1건."""
        cochl = [
            d for d in _by_type(rows, "bulletin_detail")
            if d["species_class"] == SC_TARGET
        ]
        assert len([d for d in cochl if d["grade"] == "WARNING"]) == 1


# ── F9: R3 건수·NOT_GRADED·지점 분리 ─────────────────────────────────────────


class TestF9:
    @pytest.fixture(scope="class")
    def rows(self):
        return _run(R3)

    def test_bulletins_count(self, rows):
        assert len(_by_type(rows, "bulletin")) == 15

    def test_chattonella_not_graded(self, rows):
        """Chattonella 10건 전부 NOT_GRADED."""
        chattonella = [
            d for d in _by_type(rows, "bulletin_detail")
            if "Chattonella" in d["nam_biology"]
        ]
        assert len(chattonella) == 10
        assert all(d["grade"] == "NOT_GRADED" for d in chattonella)

    def test_detail_areas_total(self, rows):
        """bulletin_detail_areas 합계 20행."""
        assert len(_by_type(rows, "bulletin_detail_area")) == 20

    def test_split_two_parts(self, rows):
        """'및'·'~' 포함 5건(20240731·0801·0807·0808·0809) 각 2행."""
        split_day_reports = {"20240731", "20240801", "20240807", "20240808", "20240809"}
        bulletins = _by_type(rows, "bulletin")
        details = _by_type(rows, "bulletin_detail")
        areas = _by_type(rows, "bulletin_detail_area")

        dr_by_cod_news = {b["cod_news"]: b["day_report"] for b in bulletins}

        for detail in details:
            day_report = dr_by_cod_news[detail["cod_news"]]
            detail_areas = [
                a for a in areas
                if a["cod_news"] == detail["cod_news"] and a["seq"] == detail["seq"]
            ]
            if day_report in split_day_reports:
                assert len(detail_areas) == 2, (
                    f"{day_report} 분리 기대 2행, 실제 {len(detail_areas)}행"
                )
            else:
                assert len(detail_areas) == 1, (
                    f"{day_report} 분리 기대 1행, 실제 {len(detail_areas)}행"
                )


# ── F10: R1+R3 고유 day_report · "전남 여수" 1종 ─────────────────────────────


class TestF10:
    @pytest.fixture(scope="class")
    def all_rows(self):
        return _run(R1) + _run(R3)

    def test_unique_day_report(self, all_rows):
        bulletins = _by_type(all_rows, "bulletin")
        unique_dr = {b["day_report"] for b in bulletins}
        assert len(unique_dr) == 66

    def test_yeosu_normalized_one_kind(self, all_rows):
        """'전남 여수 '(공백) 등이 정규화 후 '전남 여수' 1종으로 통일."""
        details = _by_type(all_rows, "bulletin_detail")
        yeosu_keys = {
            d["txt_seas_key"] for d in details
            if d.get("txt_seas_key") == "전남 여수"
        }
        assert len(yeosu_keys) == 1


# ── N10: Margalefidinium 밀도 150 → 주의보(ADVISORY) ─────────────────────────


class TestN10:
    def _make_row(self, nam_biology: str, max_density) -> list[dict]:
        adapter = BulletinProcessorAdapter()
        rows = [
            {"_type": "bulletin", "cod_news": "TEST-001", "day_report": "20260928",
             "detail_count": 1, "grade": None, "raw_id": "r"},
            {"_type": "bulletin_detail", "cod_news": "TEST-001", "seq": 1,
             "nam_biology": nam_biology, "txt_seas_raw": "전남 여수",
             "txt_seas_key": None, "min_density": None,
             "max_density": _parse_density(str(max_density)),
             "min_watertemp": None, "max_watertemp": None,
             "min_salt": None, "max_salt": None,
             "species_class": None, "grade": None},
        ]
        return adapter.normalize(rows)

    def test_margalefidinium_density_150_advisory(self):
        """Margalefidinium polykrikoides 밀도 150 → ADVISORY (주의보)."""
        rows = self._make_row("Margalefidinium polykrikoides", 150)
        detail = next(r for r in rows if r["_type"] == "bulletin_detail")
        assert detail["species_class"] == SC_TARGET
        assert detail["grade"] == "ADVISORY"


# ── 단위 함수 테스트 ──────────────────────────────────────────────────────────


class TestIsTargetSpecies:
    def test_cochlodinium_exact(self):
        assert _is_target_species(
            "Cochlodinium polykrikoides", ["Cochlodinium polykrikoides"]
        )

    def test_margalefidinium(self):
        assert _is_target_species(
            "Margalefidinium polykrikoides",
            ["Cochlodinium polykrikoides", "Margalefidinium polykrikoides"],
        )

    def test_case_insensitive(self):
        assert _is_target_species(
            "cochlodinium polykrikoides", ["Cochlodinium polykrikoides"]
        )

    def test_prefix_match(self):
        """앞부분 일치 — 변종 학명 처리."""
        assert _is_target_species(
            "Cochlodinium polykrikoides var. catenatum",
            ["Cochlodinium polykrikoides"],
        )

    def test_non_target(self):
        assert not _is_target_species("Chattonella marina", ["Cochlodinium polykrikoides"])

    def test_empty(self):
        assert not _is_target_species("", ["Cochlodinium polykrikoides"])


class TestDetermineGrade:
    """thresholds=[10, 100, 1000]"""

    def test_none_below_10(self):
        assert _determine_grade(5.0, [10, 100, 1000]) == "NONE"

    def test_pre_advisory_10(self):
        assert _determine_grade(10.0, [10, 100, 1000]) == "PRE_ADVISORY"

    def test_pre_advisory_99(self):
        assert _determine_grade(99.0, [10, 100, 1000]) == "PRE_ADVISORY"

    def test_advisory_100(self):
        assert _determine_grade(100.0, [10, 100, 1000]) == "ADVISORY"

    def test_advisory_999(self):
        assert _determine_grade(999.0, [10, 100, 1000]) == "ADVISORY"

    def test_warning_1000(self):
        assert _determine_grade(1000.0, [10, 100, 1000]) == "WARNING"

    def test_warning_over_1000(self):
        assert _determine_grade(5000.0, [10, 100, 1000]) == "WARNING"


class TestNormalizeTxtSeas:
    def test_strip_whitespace(self):
        assert _normalize_txt_seas_1_3("전남 여수 ", {}) == "전남 여수"

    def test_strip_crlf(self):
        assert _normalize_txt_seas_1_3("경남 남해군 미조~상주면\r\n", {}) == "경남 남해군 미조~상주면"

    def test_sido_abbrev(self):
        assert _normalize_txt_seas_1_3("충청남도 천수만", {}) == "충남 천수만"

    def test_sido_abbrev_with_haeyok(self):
        assert _normalize_txt_seas_1_3("충청남도 천수만 해역", {}) == "충남 천수만"

    def test_haeyok_removed(self):
        assert _normalize_txt_seas_1_3("충남 천수만 해역", {}) == "충남 천수만"

    def test_haeyok_with_suffix(self):
        """'해역(내측)' 제거."""
        assert _normalize_txt_seas_1_3("충남 서산 창리 해역(내측)", {}) == "충남 서산 창리"

    def test_alias_not_applied_in_normalize(self):
        """aliases는 post-split area_id 조회에만 쓴다 — normalize 단계는 치환하지 않는다."""
        aliases = {"충천남도 천수만": "충남_chunnam"}
        result = _normalize_txt_seas_1_3("충천남도 천수만 해역", aliases)
        assert result == "충천남도 천수만"

    def test_no_change_needed(self):
        assert _normalize_txt_seas_1_3("전남 여수", {}) == "전남 여수"


class TestSplitTxtSeas:
    def test_no_split(self):
        assert _split_txt_seas_4_5("충남 천수만") == ["충남 천수만"]

    def test_and_split(self):
        result = _split_txt_seas_4_5("충남 서산 창리 및 태안 황도")
        assert result == ["충남 서산 창리", "태안 황도"]

    def test_tilde_split(self):
        result = _split_txt_seas_4_5("경남 남해군 미조~상주")
        assert result == ["경남 남해군 미조", "상주"]

    def test_tilde_no_prefix(self):
        """좌측 부분 없는 '~' — 빈 파트 제거."""
        result = _split_txt_seas_4_5("~상주")
        assert result == ["상주"]

    def test_multiple_and_splits(self):
        result = _split_txt_seas_4_5("A 및 B 및 C")
        assert result == ["A", "B", "C"]


class TestParseDensity:
    def test_empty_string_none(self):
        assert _parse_density("") is None

    def test_zero_string_zero(self):
        """"0"은 None이 아닌 0.0 — 0과 빈 값 구분."""
        assert _parse_density("0") == 0.0

    def test_numeric_string(self):
        assert _parse_density("150") == 150.0

    def test_none_input(self):
        assert _parse_density(None) is None

    def test_float_string(self):
        assert _parse_density("3.5") == 3.5


# ── C11 — 별칭·해역 시드가 없거나 깨지면 빈 값으로 대체하지 않고 멈춘다 ──────────

class TestSeedsStopInsteadOfEmpty:
    @staticmethod
    def _seed_dir(tmp_path, monkeypatch, text: str | None, filename: str = "area_aliases.yaml"):
        import common.seeds as seeds_mod
        import processor.adapters.bulletin._adapter as ad
        import processor.adapters.bulletin._seed as sd
        if text is not None:
            (tmp_path / filename).write_text(text, "utf-8")
        monkeypatch.setattr(seeds_mod, "_SEEDS_DIR", tmp_path)
        return ad, sd

    @pytest.mark.parametrize("text", [None, "", "aliases: []\n", "other: 1\n",
                                      "aliases:\n  - alias_key: 경남 통영\n"])
    def test_alias_seed_missing_empty_or_malformed_stops(self, tmp_path, monkeypatch, text):
        ad, _ = self._seed_dir(tmp_path, monkeypatch, text)
        with pytest.raises(RuntimeError):
            ad._load_area_aliases()
        with pytest.raises(RuntimeError):
            ad.BulletinProcessorAdapter().configure({}, {})

    def test_alias_seed_valid(self, tmp_path, monkeypatch):
        ad, _ = self._seed_dir(tmp_path, monkeypatch,
                               "aliases:\n  - alias_key: 경남 통영\n    area_id: gyeongnam_tongyeong\n")
        assert ad._load_area_aliases() == {"경남 통영": "gyeongnam_tongyeong"}

    def test_real_seed_loads(self):
        from processor.adapters.bulletin._adapter import _load_area_aliases
        assert _load_area_aliases()

    def test_db_seed_loader_stops_on_missing_file(self, tmp_path, monkeypatch):
        _, sd = self._seed_dir(tmp_path, monkeypatch, None)

        class _Repo:
            def __getattr__(self, name):
                return lambda rows: None

        with pytest.raises(RuntimeError):
            sd.load_seeds(_Repo())

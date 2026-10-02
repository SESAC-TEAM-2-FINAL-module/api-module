"""
적조정보 가공 어댑터 (I-3)
- outer·item2 두 층 해석 → bulletins·bulletin_details·bulletin_detail_areas 행
- 등급 판정: UNKNOWN·NOT_GRADED·공식 4단계 (SKILL.md ③-4 5단계 순서)
- txt_seas 정규화 5단계 + 지점 분리 → bulletin_detail_areas
- unmapped_locations: `_type = unmapped_location` 행으로 낸다 — kind는 PARSE_FAILED만(OUT_OF_SCOPE 판별 규칙 없음). 적재는 processor (I-12)
"""
from __future__ import annotations
import re
import sys

import yaml

from common.classifier import ParsedResponse
from common.config import load_definitions
from common.seeds import load_area_aliases_dict as _load_area_aliases

API_ID = "redtideList"

# 시도명 전체 → 약칭 (정규화 3단계)
_SIDO_ABBREV: dict[str, str] = {
    "경상남도": "경남", "경상북도": "경북",
    "전라남도": "전남", "전라북도": "전북",
    "충청남도": "충남", "충청북도": "충북",
    "강원도": "강원", "경기도": "경기",
    "제주도": "제주", "제주특별자치도": "제주",
    "부산광역시": "부산", "인천광역시": "인천",
    "울산광역시": "울산", "대구광역시": "대구",
    "광주광역시": "광주", "대전광역시": "대전",
}

# species_class 코드 상수 (DB ENUM 미사용 — CLAUDE.md 3절)
SC_TARGET = "TARGET"
SC_NON_TARGET = "NON_TARGET"
SC_MISSING = "MISSING"

# unmapped_locations kind 상수
KIND_PARSE_FAILED = "PARSE_FAILED"
KIND_OUT_OF_SCOPE = "OUT_OF_SCOPE"


class BulletinProcessorAdapter:
    api_id = API_ID

    def configure(self, definitions: dict, operational: dict) -> None:
        """기동 시 별칭 시드 검사 — 깨졌으면 processor가 기동하지 않는다"""
        _load_area_aliases()

    def interpret(self, pr: ParsedResponse, raw_meta: dict) -> list[dict]:
        """outer items → bulletins + bulletin_details rows."""
        rows: list[dict] = []
        raw_id = raw_meta.get("raw_id", "")

        for outer in pr.items:
            cod_news = outer.get("cod_news", "")
            day_report = outer.get("day_report", "")
            item2: list[dict] = outer.get("item2") or []

            rows.append({
                "_type": "bulletin",
                "cod_news": cod_news,
                "day_report": day_report,
                "detail_count": len(item2),
                "grade": None,
                "raw_id": raw_id,
            })

            for seq, sub in enumerate(item2, start=1):
                txt_seas_raw = sub.get("txt_seas", "") or ""
                rows.append({
                    "_type": "bulletin_detail",
                    "cod_news": cod_news,
                    "seq": seq,
                    "nam_biology": (sub.get("nam_biology") or "").strip(),
                    "txt_seas_raw": txt_seas_raw,
                    "txt_seas_key": None,
                    "min_density": _parse_density(sub.get("min_density")),
                    "max_density": _parse_density(sub.get("max_density")),
                    "min_watertemp": _parse_float(sub.get("min_watertemp")),
                    "max_watertemp": _parse_float(sub.get("max_watertemp")),
                    "min_salt": _parse_float(sub.get("min_salt")),
                    "max_salt": _parse_float(sub.get("max_salt")),
                    "species_class": None,
                    "grade": None,
                })

        return rows

    def normalize(self, rows: list[dict]) -> list[dict]:
        """등급 판정, txt_seas 정규화, bulletin_detail_areas 생성."""
        defs = load_definitions()
        species_allow: list[str] = defs.get("bulletin", {}).get("species_allow", [])
        grade_thresholds: list[int] = defs.get("bulletin", {}).get("grade_thresholds", [10, 100, 1000])
        aliases = _load_area_aliases()

        # item2 없는 속보 판별: bulletin_detail 행이 존재하는 cod_news 집합
        detail_cod_news: set[str] = {
            r["cod_news"] for r in rows if r["_type"] == "bulletin_detail"
        }

        result: list[dict] = []

        for row in rows:
            if row["_type"] == "bulletin":
                # item2 없는 속보 → grade=UNKNOWN (SKILL.md ③-4 1단계)
                if row["cod_news"] not in detail_cod_news:
                    row["grade"] = "UNKNOWN"
                result.append(row)

            elif row["_type"] == "bulletin_detail":
                nam_bio = row["nam_biology"]

                # 등급 판정 순서 (SKILL.md ③-4)
                if not nam_bio:                                        # 2단계: 빈 nam_biology
                    row["species_class"] = SC_MISSING
                    row["grade"] = "UNKNOWN"
                elif not _is_target_species(nam_bio, species_allow):   # 3단계: 비대상 종
                    row["species_class"] = SC_NON_TARGET
                    row["grade"] = "NOT_GRADED"
                else:
                    row["species_class"] = SC_TARGET
                    max_density = row["max_density"]
                    if max_density is None or max_density == 0:        # 4단계: 밀도 0·결측
                        row["grade"] = "UNKNOWN"
                    else:                                              # 5단계: 공식 4단계
                        row["grade"] = _determine_grade(max_density, grade_thresholds)

                # txt_seas 정규화 (1~3단계) → txt_seas_key
                txt_seas_key = _normalize_txt_seas_1_3(row["txt_seas_raw"], aliases)
                row["txt_seas_key"] = txt_seas_key

                result.append(row)

                # 4~5단계 분리 → bulletin_detail_areas 행 생성
                parts = _split_txt_seas_4_5(txt_seas_key)
                for part_no, area_key in enumerate(parts, start=1):
                    area_id = aliases.get(area_key)
                    if area_id is None:
                        # 검토 큐 행 — processor 적재가 unmapped_locations에 쓴다 (4.3절, I-12)
                        result.append({
                            "_type": "unmapped_location",
                            "area_key": area_key,
                            "kind": KIND_PARSE_FAILED,
                            "raw_sample": row["txt_seas_raw"],
                        })
                    result.append({
                        "_type": "bulletin_detail_area",
                        "cod_news": row["cod_news"],
                        "seq": row["seq"],
                        "part_no": part_no,
                        "area_key": area_key,
                        "area_id": area_id,
                    })

        return result


# ── 등급 판정 ─────────────────────────────────────────────────────────────────

def _is_target_species(nam_bio: str, species_allow: list[str]) -> bool:
    """대소문자·공백 무시 앞부분 일치로 대상 종 판별 (SKILL.md ③-4)."""
    bio_norm = nam_bio.lower().replace(" ", "")
    for s in species_allow:
        s_norm = s.lower().replace(" ", "")
        if bio_norm.startswith(s_norm):
            return True
    return False


def _determine_grade(max_density: float, thresholds: list[int]) -> str:
    """thresholds=[10,100,1000] → NONE/PRE_ADVISORY/ADVISORY/WARNING."""
    t0, t1, t2 = thresholds[0], thresholds[1], thresholds[2]
    if max_density < t0:
        return "NONE"
    if max_density < t1:
        return "PRE_ADVISORY"
    if max_density < t2:
        return "ADVISORY"
    return "WARNING"


# ── txt_seas 정규화 ────────────────────────────────────────────────────────────

def _normalize_txt_seas_1_3(raw: str, aliases: dict[str, str]) -> str:
    """1단계 strip → 2단계 (예약) → 3단계 시도명 약칭 + 해역 접미 제거.
    aliases는 4단계 이후 area_id 조회에만 쓴다(post-split). 2단계는 미사용.
    """
    s = raw.strip().replace("\r", "").replace("\n", "")
    for full, abbr in _SIDO_ABBREV.items():
        if s.startswith(full):
            s = abbr + s[len(full):]
            break
    s = re.sub(r"\s*해역(\([^)]*\))?$", "", s).strip()
    return s


def _split_txt_seas_4_5(key: str) -> list[str]:
    """4단계 '및' 분리, 5단계 '~' 구간 → 양 끝 지점."""
    parts = [p.strip() for p in key.split("및")]
    result: list[str] = []
    for part in parts:
        if "~" in part:
            ends = part.split("~", 1)
            left, right = ends[0].strip(), ends[1].strip()
            if left:
                result.append(left)
            if right:
                result.append(right)
        else:
            if part:
                result.append(part)
    return result


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────

def _parse_density(val) -> float | None:
    """빈 값 → None, 숫자 문자열 → float (0과 빈 값 구분 — SKILL.md ③-3)."""
    if val is None:
        return None
    s = str(val).strip()
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _parse_float(val) -> float | None:
    if val is None:
        return None
    s = str(val).strip()
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None




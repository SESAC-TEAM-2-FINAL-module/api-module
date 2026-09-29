"""
적조 현재값 산출 (4.8절 · bulletin skill).
양식장 좌표 → 대응 해역 → 유효 기간 안 최신 속보 → 등급 최고 세부 행.
"""
from __future__ import annotations

from datetime import date, timedelta

from common.geo import haversine

# 등급 순서 (높을수록 숫자 큼) — *(제안)*
_GRADE_ORDER = {
    "WARNING": 6,
    "ADVISORY": 5,
    "PRE_ADVISORY": 4,
    "UNKNOWN": 3,
    "NONE": 2,
    "NOT_GRADED": 1,
}


def _is_pending(val: object) -> bool:
    return val is None or str(val).strip() in ("<미결>", "")


def _grade_rank(grade: str | None) -> int:
    return _GRADE_ORDER.get(grade or "NOT_GRADED", 0)


def find_red_tide_reading(
    farm_lat: float,
    farm_lng: float,
    areas: list[dict],
    bulletins: list[dict],
    bulletin_details: list[dict],
    bulletin_detail_areas: list[dict],
    current_window_days: object,
    ref_date: date,
) -> dict | None:
    """
    Returns farm_readings 행 일부 또는 None (해당 속보 없음).
    None이면 value=None, provenance=OFFICIAL, none_reason=None (정상적 침묵).

    current_window_days 미결 → window_days = None → 유효 기간 미적용 (모든 속보 포함).
    """
    window_days = None if _is_pending(current_window_days) else int(current_window_days)

    # 양식장이 반경 안에 드는 area_id 목록
    matched_area_ids: set[str] = set()
    for area in areas:
        try:
            dist = haversine(
                farm_lat, farm_lng,
                float(area["center_lat"]), float(area["center_lng"]),
            )
            if dist <= float(area["radius_km"]):
                matched_area_ids.add(str(area["area_id"]))
        except (KeyError, TypeError, ValueError):
            continue

    if not matched_area_ids:
        return None

    # 대응 세부 행이 있는 cod_news 목록 (bulletin_detail_areas → area_id)
    # bulletin_detail_areas.area_id 는 이미 alias 해소된 값
    matched_cod_seq: set[tuple[str, int]] = set()
    for bda in bulletin_detail_areas:
        if str(bda.get("area_id", "")) in matched_area_ids:
            matched_cod_seq.add((str(bda["cod_news"]), int(bda["seq"])))

    if not matched_cod_seq:
        return None

    # 유효 기간 안 속보 필터
    def _in_window(b: dict) -> bool:
        if window_days is None:
            return True
        try:
            day_report = b["day_report"]
            if isinstance(day_report, str):
                day_report = date.fromisoformat(day_report)
            return day_report >= ref_date - timedelta(days=window_days)
        except (KeyError, TypeError, ValueError):
            return False

    valid_cod_news = {b["cod_news"] for b in bulletins if _in_window(b)}

    # 해당 세부 행 중 유효 기간 + 대응 해역 필터
    # 부모 속보의 day_report 별로 그룹, 최신 속보 우선
    cod_to_day: dict[str, date] = {}
    for b in bulletins:
        try:
            dr = b["day_report"]
            if isinstance(dr, str):
                dr = date.fromisoformat(dr)
            cod_to_day[b["cod_news"]] = dr
        except (KeyError, TypeError, ValueError):
            pass

    candidate_details: list[dict] = []
    for det in bulletin_details:
        cod = det.get("cod_news")
        seq = det.get("seq")
        if cod not in valid_cod_news:
            continue
        if (str(cod), int(seq)) not in matched_cod_seq:
            continue
        candidate_details.append(det)

    if not candidate_details:
        return None

    # 최신 day_report 속보 먼저, 같으면 등급 최고 행
    candidate_details.sort(
        key=lambda d: (
            cod_to_day.get(d["cod_news"], date.min),
            _grade_rank(d.get("grade")),
        ),
        reverse=True,
    )
    chosen = candidate_details[0]

    grade = chosen.get("grade")
    max_density = chosen.get("max_density")
    source_ref = f"{chosen['cod_news']}#{chosen['seq']}"

    # 예비특보 이상 OR UNKNOWN → alertable (4.8절 명시)
    alertable = grade == "UNKNOWN" or _grade_rank(grade) >= _GRADE_ORDER["PRE_ADVISORY"]

    return {
        "value": float(max_density) if max_density is not None else None,
        "grade": grade,
        "provenance": "OFFICIAL",
        "derivation": "OFFICIAL",
        "alertable": alertable,
        "source_ref": source_ref,
        "none_reason": None,
    }

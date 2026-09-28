"""
품질 규칙 R0~R7 (4.6절)
기준값은 판정 정의 quality.*에서 읽는다 — 코드에 박지 않는다
R6(QC 플래그) 폐기 — 정선 QC 필드가 전건 2라 정보 없음
적용 원천(scope)이 규칙마다 다르다
"""
from __future__ import annotations

# 하구 예외 정점 목록: 미결(11절) — 테스트는 합성 목록으로 주입
_ESTUARY_STATIONS: set[str] = set()
# 태풍 특보 플래그: 미결(11절) — 테스트는 합성 플래그로 주입
_TYPHOON_ACTIVE: bool = False


def _r0_missing(row: dict, api: str) -> bool:
    """R0: tide·line·fishery — 수온·염분·pH 모두 0.000 또는 수온·염분·DO 모두 빈 문자열"""
    if api not in ("tide", "line", "fishery"):
        return False
    wt, sal, ph, do_ = (
        row.get("water_temp"), row.get("salinity"),
        row.get("ph"), row.get("dissolved_oxygen"),
    )
    if wt == "0.000" and sal == "0.000" and ph == "0.000":
        return True
    if wt == "" and sal == "" and do_ == "":
        return True
    return False


def _r1_biofouling(row: dict, api: str, definitions: dict) -> bool:
    """R1: line·fishery — 염분 < r1_salinity_min (하구 예외 제외)"""
    if api in ("tide",):  # dtRecent에 R1 적용하지 않는다
        return False
    sal = row.get("salinity")
    if sal is None or sal == "":
        return False
    try:
        sal_f = float(sal)
    except (ValueError, TypeError):
        return False
    threshold = definitions.get("quality", {}).get("r1_salinity_min")
    if threshold is None:
        return False
    if row.get("station_id", "") in _ESTUARY_STATIONS:
        return False
    return sal_f < threshold


def _r2_chlorophyll(row: dict, prev_row: dict | None, definitions: dict) -> bool:
    """R2: fishery — 클로로필 > max 이고 직전 대비 증가 > delta"""
    chl = row.get("chlorophyll")
    if chl is None or chl == "":
        return False
    try:
        chl_f = float(chl)
    except (ValueError, TypeError):
        return False
    limits = definitions.get("quality", {}).get("r2_chlorophyll", {})
    max_val = limits.get("max")
    delta = limits.get("delta")
    if max_val is None or delta is None:
        return False
    if chl_f <= max_val:
        return False
    if prev_row is None:
        return False
    prev_chl = prev_row.get("chlorophyll")
    if prev_chl is None or prev_chl == "":
        return False
    try:
        return (chl_f - float(prev_chl)) > delta
    except (ValueError, TypeError):
        return False


def _r3_physical(row: dict, definitions: dict) -> bool:
    """R3: 전부 — 수온 < lo 또는 > hi (경계값 포함이 정상)"""
    wt = row.get("water_temp")
    if wt is None or wt == "":
        return False
    try:
        wt_f = float(wt)
    except (ValueError, TypeError):
        return False
    rng = definitions.get("quality", {}).get("r3_water_temp_range")
    if not rng or len(rng) < 2:
        return False
    return wt_f < rng[0] or wt_f > rng[1]


def _r4_rapid_change(row: dict, prev_hour_row: dict | None, definitions: dict) -> bool:
    """R4: tide — 수온 1시간 변화 절댓값 > r4_water_temp_delta_1h (태풍 특보 중 면제)"""
    if _TYPHOON_ACTIVE:
        return False
    if prev_hour_row is None:
        return False
    wt, prev_wt = row.get("water_temp"), prev_hour_row.get("water_temp")
    if wt is None or prev_wt is None:
        return False
    try:
        diff = abs(float(wt) - float(prev_wt))
    except (ValueError, TypeError):
        return False
    delta = definitions.get("quality", {}).get("r4_water_temp_delta_1h")
    if delta is None:
        return False
    return diff > delta


def apply_quality(
    rows: list[dict],
    api: str,
    definitions: dict | None = None,
    prev_rows: dict[str, dict] | None = None,
    prev_hour_rows: dict[str, dict] | None = None,
) -> list[dict]:
    """
    각 row에 quality_flag, quality_rule을 추가해 반환한다.
    0.000·빈 값 레코드는 버리지 않는다 — MISSING으로 저장.
    """
    if definitions is None:
        definitions = {}
    if prev_rows is None:
        prev_rows = {}
    if prev_hour_rows is None:
        prev_hour_rows = {}

    out = []
    for row in rows:
        r = dict(row)
        sid = r.get("station_id", "")

        if _r0_missing(r, api):
            r["quality_flag"] = "MISSING"
            r["quality_rule"] = "R0"
        elif _r3_physical(r, definitions):
            r["quality_flag"] = "SENSOR_QUALITY"
            r["quality_rule"] = "R3"
        elif api == "tide" and _r4_rapid_change(r, prev_hour_rows.get(sid), definitions):
            r["quality_flag"] = "SENSOR_QUALITY"
            r["quality_rule"] = "R4"
        elif api in ("line", "fishery") and _r1_biofouling(r, api, definitions):
            r["quality_flag"] = "SENSOR_QUALITY"
            r["quality_rule"] = "R1"
        elif api == "fishery" and _r2_chlorophyll(r, prev_rows.get(sid), definitions):
            r["quality_flag"] = "SENSOR_QUALITY"
            r["quality_rule"] = "R2"
        else:
            r["quality_flag"] = "OK"
            r["quality_rule"] = None
        out.append(r)

    return out

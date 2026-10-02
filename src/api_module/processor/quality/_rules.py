"""
품질 규칙 R0~R7 (4.6절)
기준값은 판정 정의 quality.*에서 읽는다 — 코드에 박지 않는다
R6(QC 플래그) 폐기 — 정선 QC 필드가 전건 2라 정보 없음
적용 원천(scope)이 규칙마다 다르다
R7(파싱 실패)은 classifier가 판정한다 — 행이 만들어지지 않는다

입력 행은 어댑터 normalize() 결과 — 행 하나가 metric 하나다 (`metric`·`value`).
SENSOR_QUALITY는 `flags`에 남긴다 — 하류(interpolation 사용 관측소 필터, 4.7절)가 이 목록을 읽는다.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from common.sources import source_of

_PLACEHOLDER = "<미결>"


# R4 "1시간 전" 관측을 찾는 창 — [t − 60분 − 허용, t − 60분] (4.6절). 허용은 quality.r4_lookback_tolerance_min
_R4_LOOKBACK = timedelta(minutes=60)


def _source(api: str) -> str:
    """api_id → 규칙 적용 원천 (4.6절 "적용 원천" 열). 원천 이름을 직접 받아도 된다"""
    return source_of(api) or api


def _num(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _parse_ts(s) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s))
    except ValueError:
        return None


def _estuary_stations(definitions: dict) -> set[str]:
    """
    R1 하구 예외 정점 — 판정 정의 quality.r1_estuary_stations (4.6절).
    값이 <미결>이면 예외 없이 모든 정점에 R1을 적용한다 (게이트가 미결로 경고).
    grading.estuary_stations(조위관측소 염분 영역 판정, 4.8절)와 다른 목록이다
    """
    v = definitions.get("quality", {}).get("r1_estuary_stations")
    if v is None or v == _PLACEHOLDER:
        return set()
    return set(v)


def _r0_missing(row: dict, src: str) -> bool:
    """R0: tide·line·fishery — 값 없음(0.000 결측·빈 값). 어댑터가 value=None·missing_reason을 채운다"""
    if src not in ("tide", "line", "fishery"):
        return False
    return _num(row.get("value")) is None


def _r1_biofouling(row: dict, src: str, definitions: dict) -> bool:
    """R1: line·fishery — 염분 < r1_salinity_min (하구 예외 제외). dtRecent에는 적용하지 않는다"""
    if src not in ("line", "fishery") or row.get("metric") != "salinity":
        return False
    sal = _num(row.get("value"))
    threshold = definitions.get("quality", {}).get("r1_salinity_min")
    if sal is None or threshold is None:
        return False
    if row.get("station_id", "") in _estuary_stations(definitions):
        return False
    return sal < threshold


def _r2_chlorophyll(row: dict, prev_value: float | None, definitions: dict) -> bool:
    """R2: fishery — 클로로필 > value 이고 직전 대비 증가 > delta"""
    if row.get("metric") != "chlorophyll":
        return False
    chl = _num(row.get("value"))
    limits = definitions.get("quality", {}).get("r2_chlorophyll", {})
    max_val = limits.get("value")
    delta = limits.get("delta")
    if chl is None or max_val is None or delta is None or prev_value is None:
        return False
    return chl > max_val and (chl - prev_value) > delta


def _r3_physical(row: dict, definitions: dict) -> bool:
    """R3: 전부 — 수온 < lo 또는 > hi (경계값 포함이 정상)"""
    if row.get("metric") != "water_temp":
        return False
    wt = _num(row.get("value"))
    rng = definitions.get("quality", {}).get("r3_water_temp_range")
    if wt is None or not rng or len(rng) < 2:
        return False
    return wt < rng[0] or wt > rng[1]


def _r4_rapid_change(row: dict, prev_value: float | None, definitions: dict, typhoon_active: bool) -> bool:
    """R4: tide — 수온 1시간 변화 절댓값 > r4_water_temp_delta_1h (태풍 특보 중 면제)"""
    if typhoon_active or row.get("metric") != "water_temp":
        return False
    wt = _num(row.get("value"))
    delta = definitions.get("quality", {}).get("r4_water_temp_delta_1h")
    if wt is None or prev_value is None or delta is None:
        return False
    return abs(wt - prev_value) > delta


def _prev_hour_values(rows: list[dict], definitions: dict) -> dict[int, float]:
    """
    R4 직전 값 — 같은 관측소 수온 중 관측 시각이 [t-60분-허용, t-60분]인 가장 늦은 유효값 (4.6절).
    허용 = quality.r4_lookback_tolerance_min. 없으면 R4를 판정하지 않는다(빈 결과).
    같은 수집(전 페이지) 안에서 찾는다 — 적재된 DB 조회는 I-12 이후(4.6·11절). 반환: 행 index → 직전 값
    """
    tol_min = definitions.get("quality", {}).get("r4_lookback_tolerance_min")
    if tol_min is None:
        return {}
    tolerance = timedelta(minutes=float(tol_min))
    series: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
    for r in rows:
        if r.get("metric") != "water_temp":
            continue
        ts, v = _parse_ts(r.get("observed_at_utc")), _num(r.get("value"))
        if ts is not None and v is not None:
            series[r.get("station_id", "")].append((ts, v))
    for s in series.values():
        s.sort()

    out: dict[int, float] = {}
    for i, r in enumerate(rows):
        if r.get("metric") != "water_temp":
            continue
        ts = _parse_ts(r.get("observed_at_utc"))
        if ts is None:
            continue
        hi, lo = ts - _R4_LOOKBACK, ts - _R4_LOOKBACK - tolerance
        best = None
        for t, v in series.get(r.get("station_id", ""), []):
            if lo <= t <= hi:
                best = v
            elif t > hi:
                break
        if best is not None:
            out[i] = best
    return out


def _prev_survey_values(rows: list[dict]) -> dict[int, float]:
    """
    R2 직전 값 — 같은 정점·같은 층 클로로필의 바로 이전 조사(조사 시각 observed_at_utc) 유효값 (4.6절 R2 "직전" 정의).
    같은 수집 안에서 찾는다 — 적재된 DB 조회는 I-12 이후(4.6·11절). 반환: 행 index → 직전 값
    """
    series: dict[tuple, list[tuple[str, int]]] = defaultdict(list)
    for i, r in enumerate(rows):
        if r.get("metric") == "chlorophyll":
            when = r.get("observed_at_utc") or r.get("surveyed_on", "")   # 조사 시각 기준 (개정 14)
            series[(r.get("station_id", ""), r.get("layer"))].append((str(when), i))
    out: dict[int, float] = {}
    for entries in series.values():
        entries.sort()
        prev_val = None
        for _, i in entries:
            if prev_val is not None:
                out[i] = prev_val
            v = _num(rows[i].get("value"))
            if v is not None:
                prev_val = v
    return out


def apply_quality(
    rows: list[dict],
    api: str,
    definitions: dict | None = None,
    prev_rows: dict[int, float] | None = None,
    prev_hour_rows: dict[int, float] | None = None,
    operational: dict | None = None,
) -> list[dict]:
    """
    각 row에 quality_flag, quality_rule을 추가해 반환한다. SENSOR_QUALITY는 flags에도 남긴다.
    0.000·빈 값 레코드는 버리지 않는다 — MISSING으로 저장.
    prev_rows(R2)·prev_hour_rows(R4)는 행 index → 직전 값. 주지 않으면 같은 수집 안에서 찾는다.
    """
    if definitions is None:
        definitions = {}
    src = _source(api)
    if prev_hour_rows is None:
        prev_hour_rows = _prev_hour_values(rows, definitions) if src == "tide" else {}
    if prev_rows is None:
        prev_rows = _prev_survey_values(rows) if src == "fishery" else {}
    typhoon_active = bool((operational or {}).get("typhoon_active", False))

    out = []
    for i, row in enumerate(rows):
        r = dict(row)
        r["flags"] = list(r.get("flags") or [])

        rule = None
        if _r0_missing(r, src):
            r["quality_flag"], rule = "MISSING", "R0"
        elif _r3_physical(r, definitions):
            rule = "R3"
        elif src == "tide" and _r4_rapid_change(r, prev_hour_rows.get(i), definitions, typhoon_active):
            rule = "R4"
        elif _r1_biofouling(r, src, definitions):
            rule = "R1"
        elif src == "fishery" and _r2_chlorophyll(r, prev_rows.get(i), definitions):
            rule = "R2"

        if rule is None:
            r["quality_flag"] = "OK"
        elif rule != "R0":
            r["quality_flag"] = "SENSOR_QUALITY"
            if "SENSOR_QUALITY" not in r["flags"]:
                r["flags"].append("SENSOR_QUALITY")
        r["quality_rule"] = rule
        out.append(r)

    return out

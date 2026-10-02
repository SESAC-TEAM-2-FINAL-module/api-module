"""
적조 위험도 지수 계산 — 순수 함수 모듈 (4.10절, 개정 20).
DB 접근 없음. 호출자가 입력 축 farm_readings와 원천 flags를 전달한다.

미결 처리 4경우 (4.10절):
① 가중치 하나라도 <미결> → farm_reading NONE/RULE_UNDECIDED, 분해·단계 행 없음
② 개별 인자 규칙만 <미결> → 그 인자만 RULE_UNDECIDED 제외
③ min_factors_ok <미결> → value/lower/upper 저장, provenance NONE/RULE_UNDECIDED, 단계 없음
④ levels <미결> → 단계 행 없음 (기존 행 삭제)
"""
from __future__ import annotations

from datetime import datetime


# 인자 → 입력 축 매핑
_FACTOR_INPUT_AXIS: dict[str, str] = {
    "nearby_bulletin": "red_tide",
    "water_temp_band": "water_temp",
    "salinity_band": "salinity",
    "chlorophyll_level": "chlorophyll",
}

FACTOR_ORDER = ("nearby_bulletin", "water_temp_band", "salinity_band", "chlorophyll_level")


def _is_pending(val: object) -> bool:
    return val is None or str(val).strip() in ("<미결>", "")


def _ri_cfg(defs: dict) -> dict:
    return defs.get("risk_index") or {}


def _get_weight(ri_cfg: dict, factor: str) -> float | None:
    val = (ri_cfg.get("weights") or {}).get(factor)
    return None if _is_pending(val) else float(val)


def _factor_rule_pending(ri_cfg: dict, factor: str) -> bool:
    return _is_pending((ri_cfg.get("factors") or {}).get(factor))


def _has_sensor_quality(flags: object) -> bool:
    if isinstance(flags, dict):
        return bool(flags.get("SENSOR_QUALITY"))
    if isinstance(flags, list):
        return "SENSOR_QUALITY" in flags
    return False


def _check_ok_conditions(
    factor: str,
    reading: dict | None,
    flags: object | None,
    ri_cfg: dict,
) -> tuple[bool, str | None]:
    """OK 조건 1~4 순서대로 판정. (ok, excluded_reason)을 반환한다."""
    # ① 입력 행 있음
    if reading is None:
        return (False, "NO_INPUT")
    # ② provenance ≠ NONE
    if reading.get("provenance") == "NONE":
        return (False, "INPUT_NONE")
    # ③ 원천 flags에 SENSOR_QUALITY 없음
    if factor == "salinity_band" or factor == "chlorophyll_level":
        if _has_sensor_quality(flags):
            return (False, "SENSOR_QUALITY")
    # nearby_bulletin: grade 존재 판단 — 유효 기간 안 속보 없음도 OK(score=0)
    # water_temp_band: COMPUTED — flags 없음
    # ④ 인자 규칙이 <미결>이 아님
    if _factor_rule_pending(ri_cfg, factor):
        return (False, "RULE_UNDECIDED")
    return (True, None)


def _apply_score(factor: str, ri_cfg: dict, reading: dict) -> tuple[float, float, float]:
    """규칙을 적용해 (score, score_lower, score_upper)를 계산한다."""
    rule = (ri_cfg.get("factors") or {}).get(factor)

    if factor == "nearby_bulletin":
        # grade_scores 맵 사용 — grade=None은 "유효 기간 안 속보 없음"(score=0)
        grade_scores = (rule or {}).get("grade_scores") or {}
        grade = reading.get("grade")
        key = grade if grade is not None else "NONE"
        score = float(grade_scores.get(key, grade_scores.get("NONE", 0.0)))
        return (score, score, score)

    # 띠 기반 (water_temp_band, salinity_band, chlorophyll_level)
    bands = (rule or {}).get("bands") or (rule or {}).get("thresholds") or []

    def _band_score(v: object) -> float:
        if v is None:
            return 0.0
        v = float(v)
        for b in bands:
            lo = b.get("min")
            hi = b.get("max")
            if (lo is None or v >= float(lo)) and (hi is None or v < float(hi)):
                return float(b["score"])
        return 0.0

    return (
        _band_score(reading.get("value")),
        _band_score(reading.get("lower")),
        _band_score(reading.get("upper")),
    )


def _determine_level(value: float | None, levels_cfg: dict) -> str:
    """value로 단계 코드를 결정한다. (min ≤ x인 것 중 min이 가장 큰 코드)"""
    entries = levels_cfg.get("entries") or []
    if not entries:
        return ""
    if value is None:
        return entries[0].get("code", "")
    best_code = entries[0].get("code", "")
    best_min: float = float("-inf")
    for e in entries:
        lo = e.get("min")
        if lo is None:
            lo = float("-inf")
        else:
            lo = float(lo)
        if lo <= float(value) and lo >= best_min:
            best_min = lo
            best_code = e.get("code", "")
    return best_code


def compute_risk_index(
    farm_id: str,
    input_readings: dict[str, dict | None],
    input_flags: dict[str, object | None],
    defs: dict,
    now: datetime,
) -> tuple[dict, list[dict], dict | None]:
    """
    적조 위험도 지수를 계산한다.

    Parameters
    ----------
    farm_id: str
    input_readings: {axis: farm_reading 행 | None} — 4개 입력 축
    input_flags: {axis: flags 값 | None} — salinity·chlorophyll 원천 obs flags
    defs: 판정 정의 dict
    now: 산출 시각 (UTC naive)

    Returns
    -------
    (farm_reading_row, factor_rows, level_row)
    factor_rows: 가중치 ① 미결이면 빈 리스트
    level_row: 단계 ④ 미결이면 None
    """
    ri_cfg = _ri_cfg(defs)

    # ①: 가중치 하나라도 <미결>
    weights = {f: _get_weight(ri_cfg, f) for f in FACTOR_ORDER}
    if any(w is None for w in weights.values()):
        farm_row = _make_farm_row(farm_id, None, None, None, "NONE", "RULE_UNDECIDED", now)
        return farm_row, [], None

    # 인자별 계산
    factor_rows: list[dict] = []
    total_value = 0.0
    total_lower = 0.0
    total_upper = 0.0
    ok_count = 0
    earliest_obs: datetime | None = None

    for factor in FACTOR_ORDER:
        input_axis = _FACTOR_INPUT_AXIS[factor]
        weight = weights[factor]
        reading = input_readings.get(input_axis)
        flags = input_flags.get(input_axis)

        ok, excluded_reason = _check_ok_conditions(factor, reading, flags, ri_cfg)

        if ok:
            score, score_lower, score_upper = _apply_score(factor, ri_cfg, reading)
            contribution = weight * score
            total_value += weight * score
            total_lower += weight * score_lower
            total_upper += weight * score_upper
            ok_count += 1
            obs_at = reading.get("observed_at_utc") if reading else None
            if obs_at is not None:
                if earliest_obs is None or obs_at < earliest_obs:
                    earliest_obs = obs_at
        else:
            score = score_lower = score_upper = None
            contribution = 0.0
            # 제외 항목: 불확실성을 upper에 더함 (재정규화하지 않음)
            total_upper += weight

        factor_rows.append({
            "farm_id": farm_id,
            "factor": factor,
            "input_axis": input_axis,
            "input_value": reading.get("value") if reading else None,
            "input_lower": reading.get("lower") if reading else None,
            "input_upper": reading.get("upper") if reading else None,
            "input_unit": reading.get("unit") if reading else None,
            "input_grade": reading.get("grade") if reading else None,
            "input_baseline": None,
            "score": score,
            "score_lower": score_lower,
            "score_upper": score_upper,
            "weight": weight,
            "contribution": contribution,
            "ok": ok,
            "excluded_reason": excluded_reason if not ok else None,
            "input_none_reason": (reading.get("none_reason") if reading else None) if not ok else None,
            "source_ref": reading.get("source_ref") if reading else None,
            "observed_at_utc": reading.get("observed_at_utc") if reading else None,
            "computed_at_utc": now,
        })

    # ③: min_factors_ok <미결>
    min_ok_val = ri_cfg.get("min_factors_ok")
    if _is_pending(min_ok_val):
        farm_row = _make_farm_row(
            farm_id, total_value, total_lower, total_upper,
            "NONE", "RULE_UNDECIDED", now, observed_at_utc=earliest_obs,
        )
        return farm_row, factor_rows, None

    min_ok = int(min_ok_val)
    if ok_count >= min_ok:
        prov = "INTERPOLATED"
        none_reason = None
    else:
        prov = "NONE"
        none_reason = "INSUFFICIENT_FACTORS"

    farm_row = _make_farm_row(
        farm_id, total_value, total_lower, total_upper,
        prov, none_reason, now, observed_at_utc=earliest_obs,
    )

    # ④: levels <미결>
    levels_cfg = ri_cfg.get("levels")
    if _is_pending(levels_cfg):
        return farm_row, factor_rows, None

    # 단계 판정
    level = _determine_level(total_value, levels_cfg)
    level_at_lower = _determine_level(total_lower, levels_cfg)
    level_at_upper = _determine_level(total_upper, levels_cfg)
    level_straddle = level_at_lower != level_at_upper

    level_row = {
        "farm_id": farm_id,
        "level": level,
        "level_at_lower": level_at_lower,
        "level_at_upper": level_at_upper,
        "level_straddle": level_straddle,
        "computed_at_utc": now,
    }

    return farm_row, factor_rows, level_row


def _make_farm_row(
    farm_id: str,
    value: float | None,
    lower: float | None,
    upper: float | None,
    provenance: str,
    none_reason: str | None,
    now: datetime,
    observed_at_utc: datetime | None = None,
) -> dict:
    """red_tide_risk farm_readings 행을 만든다."""
    return {
        "farm_id": farm_id,
        "axis": "red_tide_risk",
        "value": value,
        "lower": lower,
        "upper": upper,
        "unit": None,
        "derivation": "COMPUTED",
        "provenance": provenance,
        "none_reason": none_reason,
        "validated_scope": None,
        "grade": None,
        "alertable": False,  # 불변식 N11: derivation=COMPUTED → alertable=false
        "source_ref": None,
        "distance_km": None,
        "observed_at_utc": observed_at_utc,
        "computed_at_utc": now,
    }


def check_risk_index_params(defs: dict) -> list[str]:
    """
    K9 기동 시 검사 — 값이 정해진 키만 검사한다.
    반환: 위반 메시지 목록 (빈 리스트면 OK)
    """
    ri_cfg = _ri_cfg(defs)
    violations: list[str] = []

    # 가중치 합산 검사 — 하나라도 <미결>이면 건너뜀
    weights = {f: _get_weight(ri_cfg, f) for f in FACTOR_ORDER}
    if all(w is not None for w in weights.values()):
        total = sum(weights.values())
        if abs(total - 1.0) > 1e-9:
            violations.append(f"Σweight = {total:.10f} ≠ 1 (허용 오차 1e-9)")

    # 인자별 점수 범위 [0, 1] 검사
    for factor in FACTOR_ORDER:
        rule = (ri_cfg.get("factors") or {}).get(factor)
        if _is_pending(rule):
            continue
        if factor == "nearby_bulletin":
            grade_scores = (rule or {}).get("grade_scores") or {}
            for k, v in grade_scores.items():
                if v is None:
                    continue
                sv = float(v)
                if not (0.0 <= sv <= 1.0):
                    violations.append(f"risk_index.factors.{factor}.grade_scores.{k} = {sv} 범위 밖 [0, 1]")
        else:
            bands = (rule or {}).get("bands") or (rule or {}).get("thresholds") or []
            for b in bands:
                sv = float(b.get("score", 0))
                if not (0.0 <= sv <= 1.0):
                    violations.append(f"risk_index.factors.{factor} band score = {sv} 범위 밖 [0, 1]")

    # levels 첫 min ≤ 0 검사
    levels_cfg = ri_cfg.get("levels")
    if not _is_pending(levels_cfg):
        entries = (levels_cfg or {}).get("entries") or []
        if entries:
            first_min = entries[0].get("min")
            if first_min is not None and float(first_min) > 0:
                violations.append(f"risk_index.levels.entries[0].min = {first_min} > 0")

    return violations

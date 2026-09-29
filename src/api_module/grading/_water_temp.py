"""
수온 출처 등급 산출 (4.8절).
오늘의 오차 P95 → provenance, lower/upper.
derivation = COMPUTED → alertable = false (불변식 N11).
"""
from __future__ import annotations


def grade_water_temp(
    value: float,
    error_p95: float | None,
    thresholds: list[float],
) -> tuple[str, float | None, float | None, str, str | None]:
    """
    Returns (provenance, lower, upper, derivation, none_reason).
    값은 provenance=NONE이어도 저장 (4.8절 불변식).
    error_p95 None → provenance=NONE, none_reason=NO_INPUT.
    """
    t1, t2, t3 = thresholds[0], thresholds[1], thresholds[2]

    if error_p95 is None:
        # error_window_days 미결 → 오차 없음
        return ("NONE", None, None, "COMPUTED", "NO_INPUT")

    lower = value - error_p95
    upper = value + error_p95

    if error_p95 <= t1:
        prov = "OBSERVED"
    elif error_p95 <= t2:
        prov = "NEAREST"
    elif error_p95 <= t3:
        prov = "INTERPOLATED"
    else:
        prov = "NONE"

    none_reason = "ERROR_ABOVE_LIMIT" if prov == "NONE" else None
    return (prov, lower, upper, "COMPUTED", none_reason)

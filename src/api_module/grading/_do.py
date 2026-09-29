"""
DO 정선 표층 값 선택 (4.8절 · line skill).
거리 한계 안 최근 표층 유효값. 한계 <미결> → NONE(NO_INPUT).
surface_rule <미결> → NONE(SURFACE_RULE_UNDECIDED).
"""
from __future__ import annotations

from common.geo import haversine


def _is_pending(val: object) -> bool:
    return val is None or str(val).strip() in ("<미결>", "")


def find_do_obs(
    farm_lat: float,
    farm_lng: float,
    line_surface_obs: list[dict],
    station_rows: list[dict],
    surface_rule: object,
    max_distance_km: object,
) -> dict | None:
    """
    Returns obs_row + distance_km, or None.
    None이면 호출자가 provenance/none_reason을 결정한다.

    surface_rule 미결 → None (SURFACE_RULE_UNDECIDED 처리는 main.py).
    max_distance_km 미결 → None (NO_INPUT).
    """
    if _is_pending(surface_rule):
        return None  # 호출자가 SURFACE_RULE_UNDECIDED 처리

    if _is_pending(max_distance_km):
        return None  # 호출자가 NO_INPUT 처리

    max_dist = float(max_distance_km)
    station_map = {r["id"]: r for r in station_rows}

    # 거리순 정렬 후 유효 표층값 있는 정점 선택
    obs_with_dist: list[tuple[float, dict]] = []
    for obs in line_surface_obs:
        sid = obs.get("station_id")
        st = station_map.get(sid)
        if st is None:
            continue
        try:
            dist = haversine(farm_lat, farm_lng, float(st["lat"]), float(st["lng"]))
        except (TypeError, ValueError):
            continue
        obs_with_dist.append((dist, obs))

    obs_with_dist.sort(key=lambda x: x[0])

    for dist, obs in obs_with_dist:
        if dist > max_dist:
            break
        if obs.get("value") is not None and obs.get("missing_reason") is None:
            return {**obs, "distance_km": dist}

    return None

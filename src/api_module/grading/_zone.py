"""
제외 구역 판단 (4.7·4.8절).
excluded_zones: <미결> — 값이 정해질 때까지 항상 False.
"""
from __future__ import annotations

from common.geo import haversine


def _is_pending(val: object) -> bool:
    return val is None or str(val).strip() in ("<미결>", "")


def is_in_excluded_zone(
    lat: float,
    lng: float,
    excluded_zones: object,
) -> bool:
    """
    excluded_zones: 판정 정의 grading.excluded_zones.
    <미결>이면 항상 False — 제외하지 않는다.
    형식: [{center_lat, center_lng, radius_km}, ...]
    """
    if _is_pending(excluded_zones):
        return False
    if not isinstance(excluded_zones, list):
        return False
    for zone in excluded_zones:
        try:
            dist = haversine(lat, lng, float(zone["center_lat"]), float(zone["center_lng"]))
            if dist <= float(zone["radius_km"]):
                return True
        except (KeyError, TypeError, ValueError):
            continue
    return False

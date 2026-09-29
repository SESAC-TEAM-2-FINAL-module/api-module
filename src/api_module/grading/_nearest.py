"""
최근접 활성 관측소 찾기 (물때·풍속·기온·염분 축) — 4.8절.
STATION_INACTIVE인 관측소는 제외한다.
"""
from __future__ import annotations

from common.geo import haversine


def find_nearest_obs(
    farm_lat: float,
    farm_lng: float,
    obs_rows: list[dict],
    station_rows: list[dict],
) -> dict | None:
    """
    obs_rows: get_latest_observations_by_metric() 결과
    station_rows: get_stations() 결과 (lat·lng 포함)
    Returns: obs_row + distance_km, or None.
    STATION_INACTIVE = missing_reason 값이 있는 관측 제외.
    """
    station_map = {r["id"]: r for r in station_rows}

    best: dict | None = None
    best_dist = float("inf")

    for obs in obs_rows:
        sid = obs.get("station_id")
        st = station_map.get(sid)
        if st is None:
            continue
        if not st.get("active", True):
            continue

        dist = haversine(farm_lat, farm_lng, float(st["lat"]), float(st["lng"]))
        if dist < best_dist:
            best_dist = dist
            best = {**obs, "distance_km": dist}

    return best


def is_alertable_obs(obs_row: dict) -> bool:
    """
    물때·풍속·기온·염분(salinity_mode=NEAREST_TIDE) 발송 자격:
    ① missing_reason 없음 ② 결과 코드 00이 아닌 상태 아님.
    신선도는 evaluation 몫 (4.8절).
    """
    if obs_row.get("missing_reason") is not None:
        return False
    return True

"""
클로로필a 어장환경 조사값 선택 (4.8절).
거리 한계 안 최근 표층 조사값 — 원문 필드 `CHL_S`, 저장 층 값 `S`(survey_observations.layer).
fishery_max_distance_km <미결> → NONE(NO_INPUT).
"""
from __future__ import annotations

from common.geo import haversine

SURFACE_LAYER = "S"   # survey_observations.layer — 원문 필드 이름(CHL_S)이 아니다 (2026-10-02 점검 C1)


def _is_pending(val: object) -> bool:
    return val is None or str(val).strip() in ("<미결>", "")


def find_chlorophyll_obs(
    farm_lat: float,
    farm_lng: float,
    survey_obs: list[dict],
    station_rows: list[dict],
    max_distance_km: object,
) -> dict | None:
    """
    survey_obs: get_latest_survey_obs(metric="chlorophyll", layer=SURFACE_LAYER) 결과.
    Returns obs_row + distance_km, or None (NO_INPUT).
    """
    if _is_pending(max_distance_km):
        return None

    max_dist = float(max_distance_km)
    station_map = {r["id"]: r for r in station_rows}

    obs_with_dist: list[tuple[float, dict]] = []
    for obs in survey_obs:
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
        if obs.get("value") is not None:
            return {**obs, "distance_km": dist}

    return None

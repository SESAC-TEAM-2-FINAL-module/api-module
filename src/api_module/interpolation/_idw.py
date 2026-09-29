"""IDW 추정 본체 — $SRC_IDW/stage3_idw.py::idw() 이식."""
from __future__ import annotations

from typing import Optional

from common.geo import haversine


def idw_estimate(
    target_lat: float,
    target_lon: float,
    refs: list[dict],  # {station_id, lat, lng, value}
    power_p: float,
    n_neighbors: int,
) -> tuple[Optional[float], list[dict]]:
    """
    IDW 추정값 + 가중치 기록.
    거리 순으로 n_neighbors개 관측소를 사용.
    반환: (추정값 or None, [{station_id, distance_km, weight}, ...])
    """
    if not refs:
        return None, []

    sorted_refs = sorted(
        refs,
        key=lambda r: haversine(target_lat, target_lon, r["lat"], r["lng"])
    )
    top = sorted_refs[:n_neighbors]

    dist_w_list = []
    for ref in top:
        d = haversine(target_lat, target_lon, ref["lat"], ref["lng"])
        if d == 0.0:
            return ref["value"], [
                {"station_id": ref["station_id"], "distance_km": 0.0, "weight": 1.0}
            ]
        dist_w_list.append({"ref": ref, "d": d, "w": 1.0 / (d ** power_p)})

    total_w = sum(dw["w"] for dw in dist_w_list)
    if total_w == 0:
        return None, []

    value = sum(dw["w"] * dw["ref"]["value"] for dw in dist_w_list) / total_w
    weight_records = [
        {
            "station_id": dw["ref"]["station_id"],
            "distance_km": dw["d"],
            "weight": dw["w"] / total_w,
        }
        for dw in dist_w_list
    ]
    return value, weight_records

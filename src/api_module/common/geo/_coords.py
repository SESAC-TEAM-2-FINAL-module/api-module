"""
이식: $SRC_IDW/src/normalizer.py validate_coords_closed()
폐구간 [33.0, 39.0] × [124.0, 132.0] — lat==33.0, lng==124.0 포함
범위는 판정 정의 geo.lat_range / geo.lng_range에서 읽고 코드에 박지 않는다
"""
from __future__ import annotations


def validate_coords_closed(
    lat: float,
    lng: float,
    lat_range: tuple[float, float] = (33.0, 39.0),
    lng_range: tuple[float, float] = (124.0, 132.0),
) -> bool:
    return lat_range[0] <= lat <= lat_range[1] and lng_range[0] <= lng <= lng_range[1]

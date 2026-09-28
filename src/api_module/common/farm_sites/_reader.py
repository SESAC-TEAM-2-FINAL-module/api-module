"""
양식장 좌표 읽기 (1.6절)
읽기만 한다 — 쓰거나 고치지 않는다
좌표 검증은 common/geo/ 폐구간 검증 (INVALID_COORDS → provenance=NONE은 grading 몫)
"""
from __future__ import annotations
from dataclasses import dataclass

from common.geo import validate_coords_closed


@dataclass(frozen=True)
class FarmSite:
    farm_id: str
    lat: float
    lng: float
    active: bool
    updated_at_utc: str
    valid_coords: bool


def load_farm_sites(rows: list[dict], lat_range=(33.0, 39.0), lng_range=(124.0, 132.0)) -> list[FarmSite]:
    """
    rows: DB 접근 계층에서 읽은 farm_sites 행 목록
    좌표 검증 실패 시 valid_coords=False — 행은 버리지 않는다
    """
    sites = []
    for row in rows:
        try:
            lat = float(row["lat"])
            lng = float(row["lng"])
            valid = validate_coords_closed(lat, lng, lat_range, lng_range)
        except (TypeError, ValueError, KeyError):
            lat = lng = 0.0
            valid = False
        sites.append(FarmSite(
            farm_id=str(row["farm_id"]),
            lat=lat,
            lng=lng,
            active=bool(row.get("active", True)),
            updated_at_utc=str(row.get("updated_at_utc", "")),
            valid_coords=valid,
        ))
    return sites

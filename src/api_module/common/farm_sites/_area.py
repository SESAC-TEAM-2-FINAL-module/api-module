"""
양식장 해역 판정 (계획서 1.6·4.9절, 개정 15)

웹 서비스의 양식장 좌표 계약(1.6절)에는 해역이 없다 — 어업자가 해역 경계를 알 수 없고, 해역의 모양은
구역마다 다르다. 그래서 **모듈이 정해서 알려준다**(결과 테이블 `farm_areas`).
규칙: 양식장 좌표가 반경 안에 드는 해역(`areas`, 시드) 중 **중심이 가장 가까운 하나**. 거리가 같으면 area_id 순.
반경 안에 드는 해역이 없으면 해역 없음(None) — 커버리지·계절 선언을 적용하지 않는다(4.9절 "선언"이 없는 것).
원천 값이 IoT 실측이 아닌 조사·속보라 해역 하나를 고르는 근사로 충분하다(사용자 결정 2026-10-01).
적조 현재값의 해역 대응(4.8절)은 반경 안의 해역을 **모두** 쓴다 — 이 함수와 다르다.
"""
from __future__ import annotations

from common.geo import haversine

RULE = "NEAREST_CENTER_WITHIN_RADIUS"


def assign_area(lat: float, lng: float, areas: list[dict]) -> dict | None:
    """반환: {"area_id", "distance_km"} 또는 None (반경 안 해역 없음·좌표 불량)"""
    best: tuple[float, str] | None = None
    for a in areas:
        try:
            d = haversine(float(lat), float(lng), float(a["center_lat"]), float(a["center_lng"]))
            r = float(a["radius_km"])
        except (TypeError, ValueError, KeyError):
            continue
        if d <= r:
            cand = (d, str(a["area_id"]))
            if best is None or cand < best:
                best = cand
    if best is None:
        return None
    return {"area_id": best[1], "distance_km": round(best[0], 3)}

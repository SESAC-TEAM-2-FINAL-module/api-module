"""
양식장 해역 판정 — 모듈이 정해 알린다 (계획서 1.6·4.9절, 개정 15)
규칙: 반경 안에 드는 해역 중 중심이 가장 가까운 하나, 거리가 같으면 area_id 순
"""
from common.farm_sites import assign_area

_AREAS = [
    {"area_id": "b_far", "center_lat": 34.70, "center_lng": 127.80, "radius_km": 30},
    {"area_id": "a_near", "center_lat": 34.69, "center_lng": 127.70, "radius_km": 10},
    {"area_id": "c_out", "center_lat": 35.50, "center_lng": 129.00, "radius_km": 5},
]


def test_nearest_center_within_radius():
    hit = assign_area(34.68, 127.69, _AREAS)
    assert hit["area_id"] == "a_near"
    assert 0 < hit["distance_km"] < 10


def test_outside_every_radius_is_none():
    assert assign_area(36.5, 126.0, _AREAS) is None


def test_tie_breaks_by_area_id():
    areas = [{"area_id": "z", "center_lat": 34.0, "center_lng": 128.0, "radius_km": 50},
             {"area_id": "m", "center_lat": 34.0, "center_lng": 128.0, "radius_km": 50}]
    assert assign_area(34.0, 128.0, areas)["area_id"] == "m"


def test_bad_area_rows_are_skipped():
    areas = [{"area_id": "x", "center_lat": None, "center_lng": 1, "radius_km": 1}] + _AREAS
    assert assign_area(34.68, 127.69, areas)["area_id"] == "a_near"


def test_real_seed_assigns_synthetic_farm():
    """시드 areas로 합성 양식장(가막만 34.68N·127.69E)이 해역 하나를 받는다"""
    from pathlib import Path
    import yaml
    seeds = yaml.safe_load((Path(__file__).parents[2] / "seeds" / "areas.yaml").read_text("utf-8"))["areas"]
    hit = assign_area(34.68, 127.69, seeds)
    assert hit is not None

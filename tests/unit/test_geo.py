"""geo 모듈 검사 — 폐구간 좌표 검증, 도분초 변환"""
import pytest
from common.geo import validate_coords_closed, dms_to_decimal

# 판정 정의에서 읽는 범위 — 테스트는 명시 주입 (기본값 없음)
_LAT = (33.0, 39.0)
_LNG = (124.0, 132.0)


# --- 폐구간 좌표 검증 ---

def test_boundary_south():
    """위도 33.0 포함 (개구간이었을 때 523행 누락 사례 방지)"""
    assert validate_coords_closed(33.0, 128.0, _LAT, _LNG) is True

def test_boundary_west():
    """경도 124.0 포함"""
    assert validate_coords_closed(36.0, 124.0, _LAT, _LNG) is True

def test_boundary_north():
    assert validate_coords_closed(39.0, 128.0, _LAT, _LNG) is True

def test_boundary_east():
    assert validate_coords_closed(36.0, 132.0, _LAT, _LNG) is True

def test_inside():
    assert validate_coords_closed(35.0, 128.0, _LAT, _LNG) is True

def test_out_south():
    assert validate_coords_closed(32.9, 128.0, _LAT, _LNG) is False

def test_out_north():
    assert validate_coords_closed(39.1, 128.0, _LAT, _LNG) is False

def test_out_west():
    assert validate_coords_closed(36.0, 123.9, _LAT, _LNG) is False

def test_out_east():
    assert validate_coords_closed(36.0, 132.1, _LAT, _LNG) is False


# --- 도분초 변환 ---

def test_dms_normal():
    result = dms_to_decimal("35°09´54˝")
    assert result is not None
    assert abs(result - 35.165) < 0.001

def test_dms_none():
    assert dms_to_decimal(None) is None

def test_dms_empty():
    assert dms_to_decimal("") is None

def test_dms_decimal_passthrough():
    """이미 십진도인 경우 그대로"""
    result = dms_to_decimal("35.5")
    assert result == 35.5

def test_dms_out_of_range():
    """범위 밖 값 (30 < abs < 140 밖) → None"""
    assert dms_to_decimal("200.0") is None

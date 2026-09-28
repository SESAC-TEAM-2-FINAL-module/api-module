"""
B6: 운영 조정 기동 검사 (7.6절)
- ConfigMap 없음 / 키 누락 / 모르는 키 / 미결 자리 표시 / 버전 불일치 → 기동 멈춤
- operational.initial.yaml이나 기본값으로 조용히 떠오르면 실패
"""
import os
import textwrap
import pytest
from pathlib import Path
from common.config._operational import load_operational


def _write_cfg(tmp_path: Path, content: str) -> str:
    p = tmp_path / "operational.yaml"
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return str(p)


def test_B6_no_config_path():
    """OPERATIONAL_CONFIG_PATH 미설정 → 멈춤"""
    env_backup = os.environ.pop("OPERATIONAL_CONFIG_PATH", None)
    try:
        with pytest.raises(SystemExit):
            load_operational(path=None)
    finally:
        if env_backup:
            os.environ["OPERATIONAL_CONFIG_PATH"] = env_backup


def test_B6_file_not_found(tmp_path):
    """파일 없음 → 멈춤"""
    with pytest.raises(SystemExit):
        load_operational(path=str(tmp_path / "nonexistent.yaml"))


def test_B6_schema_version_mismatch(tmp_path):
    """schema 버전 불일치 → 멈춤"""
    p = _write_cfg(tmp_path, """
        schema: operational-v2
        tide:
          flatline_minutes: 30
        stale_threshold_hours:
          water_temp: 3
        evaluation:
          interpolation_stale_minutes: 60
          grading_stale_minutes: 30
        water_temp: 3
        red_tide_bulletin: 72
    """)
    with pytest.raises(SystemExit):
        load_operational(path=p)


def test_B6_placeholder(tmp_path):
    """<미결> 자리 표시 → 멈춤"""
    p = _write_cfg(tmp_path, """
        schema: operational-v1
        tide:
          flatline_minutes: <미결>
        stale_threshold_hours:
          water_temp: 3
        evaluation:
          interpolation_stale_minutes: 60
          grading_stale_minutes: 30
        water_temp: 3
        red_tide_bulletin: 72
    """)
    with pytest.raises(SystemExit):
        load_operational(path=p)


def test_B8_success_and_hash(tmp_path):
    """B8: 기동 성공 → 설정 해시 반환"""
    from common.config._operational import operational_hash
    p = _write_cfg(tmp_path, """
        schema: operational-v1
        tide:
          flatline_minutes: 30
        stale_threshold_hours:
          water_temp: 3
        evaluation:
          interpolation_stale_minutes: 60
          grading_stale_minutes: 30
        water_temp: 3
        red_tide_bulletin: 72
    """)
    cfg = load_operational(path=p)
    assert cfg["schema"] == "operational-v1"
    h = operational_hash(cfg)
    assert isinstance(h, str) and len(h) == 16

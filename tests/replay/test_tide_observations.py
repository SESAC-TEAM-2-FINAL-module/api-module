"""
tests/replay/test_tide_observations.py — S3(I-2) 재현 완결성 검사

목적: $IDW_OUTPUT_DIR/observations.csv 가 definitions.yaml의 조위 정점과
     IDW 보간 입력 지표(water_temp·salinity)를 빠짐없이 담고 있는지 확인한다.

     observations.csv 는 IDW 보간 입력 전용 파일이므로 water_temp·salinity만
     포함한다. tide_level·wind_speed·air_temp 는 DB 적재 경로이고 이 CSV에 없다.
     (단위 테스트 tests/unit/test_tide_processor.py 에서 어댑터 수준 검증)

실행 조건: IDW_OUTPUT_DIR 환경변수 설정 필요 (로컬 수동 실행만).
"""
from __future__ import annotations

import csv
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pytest
import yaml

_SKIP = pytest.mark.skipif(
    not os.environ.get("IDW_OUTPUT_DIR"),
    reason="IDW_OUTPUT_DIR 미설정 — replay 로컬 수동 실행만",
)

_ROOT = Path(__file__).parents[2]
_DEFS = yaml.safe_load((_ROOT / "config" / "definitions.yaml").read_text("utf-8"))

# definitions.yaml tide.stations (DT_ 코드, prefix 없음)
_TIDE_STATIONS: set[str] = set(_DEFS["tide"]["stations"])

# IDW 보간 입력에 포함되는 지표 (observations.csv 에 있는 것만)
# tide_level·wind_speed·air_temp 는 DB 적재 경로이고 이 CSV에 없음
_IDW_METRICS = {"water_temp", "salinity"}

# 물리 범위 (quality 규칙 3.3절 기반)
_VALUE_RANGE: dict[str, tuple[float, float]] = {
    "water_temp": (-2.0, 40.0),
    "salinity":   (0.0, 40.0),
}


def _load_obs(obs_path: Path) -> dict[str, dict[str, list]]:
    """
    observations.csv → {station_id: {metric: [value, ...]}}
    0.000 / 빈 값도 포함 (결측 포함해 정점 존재 여부를 확인해야 하므로).
    """
    data: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    with obs_path.open(encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sid = row.get("station_id", "")
            if sid not in _TIDE_STATIONS:
                continue
            metric = row.get("metric", "")
            if metric not in _IDW_METRICS:
                continue
            v = row.get("value", "")
            if v.strip() not in ("", "None"):
                try:
                    data[sid][metric].append(float(v))
                except ValueError:
                    pass
    return data


@pytest.fixture(scope="module")
def obs_data():
    obs_path = Path(os.environ["IDW_OUTPUT_DIR"]) / "observations.csv"
    assert obs_path.exists(), f"observations.csv 없음: {obs_path}"
    return _load_obs(obs_path)


# ─────────────────────────────────────────────────────────────────────────────
# F11-R1: 정점 커버리지
# ─────────────────────────────────────────────────────────────────────────────

@_SKIP
def test_all_tide_stations_present(obs_data):
    """definitions.yaml 의 모든 조위 정점이 observations.csv 에 있다."""
    missing = _TIDE_STATIONS - set(obs_data.keys())
    assert not missing, f"observations.csv 에 없는 조위 정점: {missing}"


@_SKIP
def test_all_metrics_per_station(obs_data):
    """각 정점에 IDW 보간 지표 2종(water_temp·salinity)이 모두 있다."""
    missing_map: dict[str, set[str]] = {}
    for sid in _TIDE_STATIONS:
        missing = _IDW_METRICS - set(obs_data.get(sid, {}).keys())
        if missing:
            missing_map[sid] = missing
    assert not missing_map, f"정점별 IDW 지표 누락: {missing_map}"


# ─────────────────────────────────────────────────────────────────────────────
# F11-R2: 데이터 볼륨
# ─────────────────────────────────────────────────────────────────────────────

@_SKIP
def test_minimum_observation_count(obs_data):
    """각 정점 × IDW 지표 조합에 정상값 >= 1,000 행이 있다."""
    sparse: list[str] = []
    for sid in _TIDE_STATIONS:
        for metric in _IDW_METRICS:
            cnt = len(obs_data.get(sid, {}).get(metric, []))
            if cnt < 1_000:
                sparse.append(f"{sid}/{metric}={cnt}")
    assert not sparse, f"관측 행 수 부족 (< 1,000): {sparse}"


# ─────────────────────────────────────────────────────────────────────────────
# F11-R3: 값 범위
# ─────────────────────────────────────────────────────────────────────────────

@_SKIP
@pytest.mark.parametrize("metric,lo,hi", [
    (m, r[0], r[1]) for m, r in _VALUE_RANGE.items()
])
def test_value_range(obs_data, metric, lo, hi):
    """IDW 지표의 비결측 값이 물리 범위 [lo, hi] 안에 있다."""
    out_of_range: list[str] = []
    for sid in _TIDE_STATIONS:
        for v in obs_data.get(sid, {}).get(metric, []):
            if not (lo <= v <= hi):
                out_of_range.append(f"{sid}/{metric}={v}")
    assert not out_of_range, f"범위 [{lo}, {hi}] 초과 값: {out_of_range[:10]}"


# ─────────────────────────────────────────────────────────────────────────────
# F11-R4: 기간 커버리지
# ─────────────────────────────────────────────────────────────────────────────

@_SKIP
def test_date_coverage_at_least_30_days():
    """observations.csv 의 전체 기간이 최소 30일이다."""
    obs_path = Path(os.environ["IDW_OUTPUT_DIR"]) / "observations.csv"
    dates: set[str] = set()
    with obs_path.open(encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            d = row.get("observed_date", "")
            if d:
                dates.add(d)
    assert len(dates) >= 30, f"기간 {len(dates)}일 < 30일"

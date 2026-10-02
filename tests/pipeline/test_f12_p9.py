"""
tests/pipeline/test_f12_p9.py — S8(I-7) 파이프라인 검사 (pytest 공식화)

F12: LOOCV 교차검증으로 수온 IDW 오차 P95 재현 (목표 2.48, 허용 ±0.05)
P9:  가장 가까운 관측소 제거 시 오차 P95 >= 전체 집합 P95

scripts/run_f12_p9.py 의 로직을 pytest assertion 으로 공식화한다.
두 검사 모두 IDW_OUTPUT_DIR 환경변수 설정 필요 (로컬 수동 실행만).
"""
from __future__ import annotations

import csv
import os
import sys
from datetime import datetime
from pathlib import Path

import pytest

_SKIP = pytest.mark.skipif(
    not os.environ.get("IDW_OUTPUT_DIR"),
    reason="IDW_OUTPUT_DIR 미설정 — pipeline 로컬 수동 실행만",
)

_ROOT = Path(__file__).parents[2]
_STATIONS_CSV = _ROOT / "fixtures" / "derived" / "stations.csv"

# F12 통과 기준 (skill interpolation ⑥)
_F12_P95_TARGET = 2.48
_F12_P95_TOLERANCE = 0.05

# P9 합성 양식장 좌표 (fixtures/synthetic/farms.csv)
_P9_FARM_LAT = 34.68
_P9_FARM_LNG = 127.69


# ─────────────────────────────────────────────────────────────────────────────
# 공통 픽스처
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def station_coords() -> dict[str, dict]:
    coords = {}
    with _STATIONS_CSV.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            sid = f"tide:{row['station_id']}"
            coords[sid] = {"lat": float(row["lat"]), "lng": float(row["lng"])}
    return coords


@pytest.fixture(scope="module")
def obs_list(station_coords) -> list[dict]:
    """observations.csv → 수온·데모권역·정상값 필터 관측 리스트."""
    sys.path.insert(0, str(_ROOT / "src" / "api_module"))
    import pandas as pd
    obs_path = Path(os.environ["IDW_OUTPUT_DIR"]) / "observations.csv"
    assert obs_path.exists(), f"observations.csv 없음: {obs_path}"

    df = pd.read_csv(obs_path, low_memory=False, encoding="utf-8-sig")
    df = df[df["value"].notna() & (df["value"] != 0.0)]
    df = df[
        (df["metric"] == "water_temp") &
        (df["network"].str.startswith("tide", na=False)) &
        (df["in_demo_zone"] == True)
    ]

    result = []
    for _, row in df.iterrows():
        sid = row["station_id"]
        if not str(sid).startswith("tide:"):
            sid = f"tide:{sid}"
        if sid not in station_coords:
            continue
        obs_at_raw = row.get("observed_at_utc") or row.get("observed_at")
        try:
            obs_at = datetime.fromisoformat(str(obs_at_raw))
        except Exception:
            continue
        result.append({
            "station_id": sid,
            "observed_at_utc": obs_at,
            "value": float(row["value"]),
        })
    return result


# ─────────────────────────────────────────────────────────────────────────────
# F12 — 교차검증 P95 재현
# ─────────────────────────────────────────────────────────────────────────────

@_SKIP
def test_f12_water_temp_p95(obs_list, station_coords):
    """
    F12: M2 N=5 수온 LOOCV P95 ≈ 2.48 (허용 ±0.05).
    전체 기간 기준 — 계절 분리는 레퍼런스 참고값으로, 통과 기준 아님.
    """
    from interpolation._loocv import compute_loocv

    p95, mae, n = compute_loocv(obs_list, station_coords, power_p=2, n_neighbors=5)
    assert p95 is not None, "LOOCV 결과 없음 — 관측 수 부족"
    assert abs(p95 - _F12_P95_TARGET) <= _F12_P95_TOLERANCE, (
        f"F12 수온 P95={p95:.4f}, 목표 {_F12_P95_TARGET} ±{_F12_P95_TOLERANCE}"
    )


@_SKIP
def test_f12_sample_count(obs_list, station_coords):
    """F12: LOOCV 샘플 수가 10만 이상이다 (데이터 충분성)."""
    from interpolation._loocv import compute_loocv

    _, _, n = compute_loocv(obs_list, station_coords, power_p=2, n_neighbors=5)
    assert n is not None and n >= 100_000, f"샘플 수 {n} < 100,000"


# ─────────────────────────────────────────────────────────────────────────────
# P9 — 가장 가까운 관측소 제거 시 오차 확대
# ─────────────────────────────────────────────────────────────────────────────

@_SKIP
def test_p9_nearest_removal_increases_error(obs_list, station_coords):
    """
    P9: 합성 양식장(34.68, 127.69) 최근접 관측소를 제거한 집합의
    P95 >= 전체 집합 P95.
    """
    from common.geo import haversine
    from interpolation._loocv import compute_loocv

    # 전체 집합 P95
    p95_all, _, _ = compute_loocv(obs_list, station_coords, power_p=2, n_neighbors=5)
    assert p95_all is not None

    # 최근접 관측소 탐색
    nearest = min(
        station_coords,
        key=lambda sid: haversine(
            _P9_FARM_LAT, _P9_FARM_LNG,
            station_coords[sid]["lat"], station_coords[sid]["lng"],
        ),
    )

    subset_coords = {sid: c for sid, c in station_coords.items() if sid != nearest}
    subset_obs = [o for o in obs_list if o["station_id"] != nearest]

    p95_sub, _, _ = compute_loocv(subset_obs, subset_coords, power_p=2, n_neighbors=5)
    assert p95_sub is not None
    assert p95_sub >= p95_all, (
        f"P9 FAIL: 제거 후 P95={p95_sub:.4f} < 전체 P95={p95_all:.4f} "
        f"(제거된 관측소: {nearest})"
    )

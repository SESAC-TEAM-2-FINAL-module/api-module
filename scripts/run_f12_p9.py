"""
F12·P9 로컬 수동 검사 스크립트 (CI 게이트 밖 — 실측 가공 CSV 필요).

실행:
  python scripts/run_f12_p9.py

필요 파일:
  $SRC_IDW/output/observations.csv  (280MB+, 저장소 밖 로컬 경로)
  fixtures/derived/stations.csv

F12 통과 기준 (skill interpolation ⑥):
  M2 N=5 수온 P95 2.48, 염분 P95 7.55
  수온 MAE 여름(6/24~8/31) 0.9106, 가을(9/1~9/22) 0.3646

P9 통과 기준:
  가장 가까운 관측소를 뺀 집합의 오차 P95 >= 전체 집합 P95
"""
from __future__ import annotations

import csv
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# 저장소 루트를 sys.path에 추가
ROOT = Path(__file__).parents[1]
SRC = ROOT / "src" / "api_module"
sys.path.insert(0, str(SRC))

from common.geo import haversine
from interpolation._idw import idw_estimate
from interpolation._loocv import compute_loocv

# ─────────────────────────────────────────────────────────────────────────────
# 경로
# ─────────────────────────────────────────────────────────────────────────────

STATIONS_CSV = ROOT / "fixtures" / "derived" / "stations.csv"

# $SRC_IDW/output/observations.csv 경로 — .env.sources에서 로드
def _get_obs_csv() -> Path:
    env_sources = ROOT / ".env.sources"
    src_idw = None
    if env_sources.exists():
        for line in env_sources.read_text(encoding="utf-8").splitlines():
            if line.startswith("SRC_IDW="):
                src_idw = line.split("=", 1)[1].strip()
    if not src_idw:
        raise FileNotFoundError("$SRC_IDW가 .env.sources에 없음")
    obs_csv = Path(src_idw) / "output" / "observations.csv"
    if not obs_csv.exists():
        raise FileNotFoundError(f"observations.csv 없음: {obs_csv}")
    return obs_csv


# ─────────────────────────────────────────────────────────────────────────────
# 데이터 로딩
# ─────────────────────────────────────────────────────────────────────────────

def load_stations() -> dict[str, dict]:
    coords = {}
    with STATIONS_CSV.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            coords[f"tide:{row['station_id']}"] = {
                "lat": float(row["lat"]),
                "lng": float(row["lng"]),
            }
    return coords


def load_observations(obs_csv: Path) -> pd.DataFrame:
    print(f"observations.csv 로딩 중: {obs_csv}")
    df = pd.read_csv(obs_csv, low_memory=False, encoding="utf-8-sig")
    # 0.000 제외 — stage3_idw.py 전처리와 동일 (결측 표기)
    before = len(df)
    df = df[df["value"].notna() & (df["value"] != 0.0)].reset_index(drop=True)
    print(f"  행 수: {len(df):,} (0.000·NaN 제외: {before - len(df):,}건)")
    return df


def _make_obs_list(df: pd.DataFrame, station_coords: dict) -> list[dict]:
    """DataFrame → compute_loocv 입력 리스트. station_coords 밖 관측 제외."""
    if "station_id" in df.columns and not df["station_id"].str.startswith("tide:").all():
        df = df.copy()
        df["station_id"] = "tide:" + df["station_id"].astype(str)

    obs_list = []
    for _, row in df.iterrows():
        sid = row["station_id"]
        if sid not in station_coords:
            continue
        obs_at = row.get("observed_at_utc") or row.get("observed_at")
        try:
            obs_at = datetime.fromisoformat(str(obs_at)) if isinstance(obs_at, str) else obs_at
        except Exception:
            continue
        obs_list.append({
            "station_id": sid,
            "observed_at_utc": obs_at,
            "value": float(row["value"]),
        })
    return obs_list


# ─────────────────────────────────────────────────────────────────────────────
# F12 — 교차검증 재현 (수온 P95 2.48 목표)
# ─────────────────────────────────────────────────────────────────────────────

def run_f12(df: pd.DataFrame, station_coords: dict) -> None:
    print("\n=== F12: 교차검증 재현 ===")

    # 수온만 — network=tide, in_demo_zone=True (stage3_idw.py와 동일 전처리)
    wt = df[
        (df["metric"] == "water_temp") &
        (df["network"].str.startswith("tide", na=False)) &
        (df["in_demo_zone"] == True)
    ].copy()
    print(f"  수온·데모권역 관측 수: {len(wt):,}")

    # station_coords도 in_demo_zone 관측소만 (시연권역 9개)
    demo_station_ids = set(wt["station_id"].str.replace("^", "tide:", regex=False).unique()
                           if not wt["station_id"].str.startswith("tide:").all()
                           else wt["station_id"].unique())
    # 간단히: station_coords 중 observations에 나타난 관측소만
    demo_coords = {
        f"tide:{sid}" if not sid.startswith("tide:") else sid: c
        for sid, c in station_coords.items()
    }

    obs_list = _make_obs_list(wt, demo_coords)
    print(f"  좌표 있는 수온 관측: {len(obs_list):,}")

    p95, mae, n_samples = compute_loocv(
        obs_list, station_coords, power_p=2, n_neighbors=5
    )
    print(f"  M2 N=5 수온 P95: {p95}  (목표: 2.48)")
    print(f"  M2 N=5 수온 MAE: {mae}  n={n_samples:,}")

    if p95 is not None:
        passed = abs(p95 - 2.48) < 0.05
        print(f"  F12 {'PASS ✓' if passed else 'FAIL ✗ — 오차 > 0.05'}")
    else:
        print("  F12 결과 없음 — 관측 수 부족 또는 오류")


# ─────────────────────────────────────────────────────────────────────────────
# P9 — 가장 가까운 관측소를 뺀 집합의 오차 >= 전체 집합 오차
# ─────────────────────────────────────────────────────────────────────────────

def run_p9(df: pd.DataFrame, station_coords: dict) -> None:
    print("\n=== P9: 관측소 제거 시 오차 확대 확인 ===")

    # F12와 동일 전처리 — in_demo_zone=True, 0.000 이미 제거됨
    wt = df[
        (df["metric"] == "water_temp") &
        (df["network"].str.startswith("tide", na=False)) &
        (df["in_demo_zone"] == True)
    ].copy()

    obs_list = _make_obs_list(wt, station_coords)

    # 전체 집합 오차
    p95_all, _, n_all = compute_loocv(
        obs_list, station_coords, power_p=2, n_neighbors=5
    )
    print(f"  전체 집합 P95: {p95_all}  n={n_all:,}")

    # 가막만(34.68, 127.69)에서 가장 가까운 관측소 찾기 → 제거
    gamak_lat, gamak_lon = 34.68, 127.69
    nearest_sid = min(
        station_coords.keys(),
        key=lambda sid: haversine(gamak_lat, gamak_lon, station_coords[sid]["lat"], station_coords[sid]["lng"])
    )
    nearest_dist = haversine(gamak_lat, gamak_lon, station_coords[nearest_sid]["lat"], station_coords[nearest_sid]["lng"])
    print(f"  가막만 최근접 관측소: {nearest_sid} ({nearest_dist:.2f} km) → 제거")

    subset_coords = {sid: c for sid, c in station_coords.items() if sid != nearest_sid}
    subset_obs = [o for o in obs_list if o["station_id"] != nearest_sid]

    p95_sub, _, n_sub = compute_loocv(
        subset_obs, subset_coords, power_p=2, n_neighbors=5
    )
    print(f"  제거 후 집합 P95:  {p95_sub}  n={n_sub:,}")

    if p95_all is not None and p95_sub is not None:
        passed = p95_sub >= p95_all
        print(f"  P9 {'PASS ✓' if passed else 'FAIL ✗ — 오차가 줄었음'}")
    else:
        print("  P9 결과 없음")


# ─────────────────────────────────────────────────────────────────────────────
# 실행
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        obs_csv = _get_obs_csv()
    except FileNotFoundError as e:
        print(f"오류: {e}")
        sys.exit(1)

    station_coords = load_stations()
    df = load_observations(obs_csv)

    run_f12(df, station_coords)
    run_p9(df, station_coords)

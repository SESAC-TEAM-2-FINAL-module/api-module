"""
LOOCV 교차검증 — 오늘의 오차 산출.
$SRC_IDW/stage3_idw.py::run_e1() (2차 재검증) 이식.
그룹 내 동일 station_id 중복 제거 포함 — 1차 IDW 실험 함정.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime
from typing import Optional

from common.geo import haversine
from ._idw import idw_estimate


def compute_loocv(
    observations: list[dict],
    station_coords: dict[str, dict],
    power_p: float,
    n_neighbors: int,
    bucket_minutes: int = 5,
) -> tuple[Optional[float], Optional[float], int]:
    """
    LOOCV P95·MAE·샘플 수.
    observations: {station_id, observed_at_utc, value}
    반환: (p95, mae, n_samples)
    0km 최근접 참조 발생 시 ValueError — 즉시 상위로 전파.
    """
    import numpy as np

    def _bucket(dt: datetime) -> datetime:
        minutes = (dt.minute // bucket_minutes) * bucket_minutes
        return dt.replace(minute=minutes, second=0, microsecond=0)

    valid: list[dict] = []
    for obs in observations:
        sid = obs["station_id"]
        coords = station_coords.get(sid)
        if not coords:
            continue
        v = obs.get("value")
        if v is None:
            continue
        try:
            if math.isnan(float(v)):
                continue
        except (TypeError, ValueError):
            pass
        obs_at = obs["observed_at_utc"]
        if isinstance(obs_at, str):
            obs_at = datetime.fromisoformat(obs_at)
        valid.append({
            "station_id": sid,
            "lat": float(coords["lat"]),
            "lng": float(coords["lng"]),
            "value": float(v),
            "bucket": _bucket(obs_at),
        })

    if not valid:
        return None, None, 0

    groups: dict[datetime, list[dict]] = defaultdict(list)
    for obs in valid:
        groups[obs["bucket"]].append(obs)

    errors: list[float] = []
    for grp_list in groups.values():
        # 동일 station_id 중복 제거 — stage3_idw.py::run_e1() 필수 처리
        seen: dict[str, dict] = {}
        for pt in grp_list:
            if pt["station_id"] not in seen:
                seen[pt["station_id"]] = pt
        pts = list(seen.values())

        if len(pts) < 4:
            continue

        for i, target in enumerate(pts):
            refs = [p for j, p in enumerate(pts) if j != i]

            nn_dist = min(
                haversine(target["lat"], target["lng"], r["lat"], r["lng"])
                for r in refs
            )
            if nn_dist == 0.0:
                raise ValueError(
                    f"최근접 참조 거리 0km: station={target['station_id']}"
                    " — station_id 중복 또는 동일 좌표 관측소"
                )

            pred, _ = idw_estimate(
                target["lat"], target["lng"], refs, power_p, n_neighbors
            )
            if pred is not None and not math.isnan(pred):
                errors.append(abs(pred - target["value"]))

    if not errors:
        return None, None, 0

    p95 = float(np.percentile(errors, 95))
    mae = float(np.mean(errors))
    return round(p95, 4), round(mae, 4), len(errors)

"""IDW 입력 관측 선택 (4.6절, 4.7절, Q7) — interpolation이 고르고, grading이 같은 규칙으로 run_id의 값을 재현한다."""
from __future__ import annotations

import math
from datetime import datetime, timedelta


def filter_stations(
    observations: list[dict],
    station_coords: dict[str, dict],
    ref_time: datetime,
    align_window_min: int,
    exclude_flatline: object,
) -> list[dict]:
    """
    관측소마다 정렬 창 [ref_time - align_window_min, ref_time] 안의 **최신 유효값 하나**.
    제외: missing_reason 있음(STATION_INACTIVE 포함), value 없음·NaN, SENSOR_QUALITY(R3·R4),
    exclude_flatline 설정 시 STALE_SUSPECT, 좌표 없는 관측소.
    """
    cutoff = ref_time - timedelta(minutes=align_window_min)

    latest: dict[str, dict] = {}
    for obs in observations:
        if obs.get("missing_reason"):
            continue

        v = obs.get("value")
        if v is None:
            continue
        try:
            if math.isnan(float(v)):
                continue
        except (TypeError, ValueError):
            pass

        flags = obs.get("flags") or []
        if isinstance(flags, str):
            flags = [f.strip() for f in flags.split(",") if f.strip()]

        if "SENSOR_QUALITY" in flags:
            continue
        if exclude_flatline and "STALE_SUSPECT" in flags:
            continue

        obs_at = obs["observed_at_utc"]
        if isinstance(obs_at, str):
            obs_at = datetime.fromisoformat(obs_at)

        if not (cutoff <= obs_at <= ref_time):
            continue

        sid = obs["station_id"]
        coords = station_coords.get(sid)
        if not coords:
            continue

        prev = latest.get(sid)
        if prev is not None and prev["observed_at_utc"] >= obs_at:
            continue
        latest[sid] = {
            "station_id": sid,
            "lat": float(coords["lat"]),
            "lng": float(coords["lng"]),
            "value": float(v),
            "observed_at_utc": obs_at,
        }

    return [latest[sid] for sid in sorted(latest)]

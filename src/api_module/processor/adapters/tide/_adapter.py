"""
조위관측소 최신관측 가공 어댑터 (I-2)
- obsrvnDt KST naive → UTC 변환 (-9h) (SOURCES.md 기록)
- 0.000 결측 (R0): value=NULL, missing_reason='ZERO_SENTINEL'
- 값 멈춤 플래그 (STALE_SUSPECT): tide.flatline_minutes 초과 연속 동일 값
- 관측소 미가동 (STATION_INACTIVE): 최근 24h 전 행 결측
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone

from common.classifier import ParsedResponse
from common.config import load_definitions

API_ID = "dtRecent"

# API 필드 → metric 이름 (SKILL.md ③-3)
_METRIC_FIELDS: list[tuple[str, str]] = [
    ("wtem", "water_temp"),
    ("slntQty", "salinity"),
    ("bscTdlvHgt", "tide_level"),
    ("wspd", "wind_speed"),
    ("wdir", "wind_dir"),
    ("artmp", "air_temp"),
]

# 0.000 결측 대상 metric — R0 (수온·염분·pH; dtRecent는 pH 없음)
_ZERO_SENTINEL_METRICS = {"water_temp", "salinity"}


class TideProcessorAdapter:
    api_id = API_ID

    def interpret(self, pr: ParsedResponse, raw_meta: dict) -> list[dict]:
        """items → (station_id, observed_at_utc, metric, _raw_value) 행"""
        rows: list[dict] = []
        raw_id = raw_meta.get("raw_id", "")
        for item in pr.items:
            obs_code = item.get("obsCode") or item.get("obsCd") or ""
            if not obs_code:
                continue
            station_id = f"tide:{obs_code}"
            obs_dt_str = item.get("obsrvnDt", "")
            observed_at_utc = _kst_to_utc(obs_dt_str)

            for api_field, metric in _METRIC_FIELDS:
                rows.append({
                    "station_id": station_id,
                    "observed_at_utc": observed_at_utc,
                    "metric": metric,
                    "_raw_value": item.get(api_field),
                    "flags": [],
                    "missing_reason": None,
                    "raw_id": raw_id,
                })
        return rows

    def normalize(self, rows: list[dict]) -> list[dict]:
        """0.000 결측, 값 멈춤 플래그, STATION_INACTIVE 판정"""
        # 운영 조정: tide.flatline_minutes (값 미결 — 환경변수로 로드)
        flatline_minutes = _load_flatline_minutes()

        for row in rows:
            raw_val = row.pop("_raw_value", None)
            metric = row["metric"]
            value, missing_reason = _parse_value(raw_val, metric)
            row["value"] = value
            row["missing_reason"] = missing_reason

        if flatline_minutes is not None:
            _apply_flatline_flags(rows, flatline_minutes)

        _apply_station_inactive(rows)

        return rows


# ── 헬퍼 ────────────────────────────────────────────────────────────────────


def _kst_to_utc(dt_str: str) -> str:
    """obsrvnDt KST naive → UTC (-9h). SOURCES.md: obsrvnDt는 KST naive 확인(I-2)"""
    if not dt_str:
        return ""
    try:
        dt_str = dt_str.strip().replace("T", " ")
        dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        utc = dt - timedelta(hours=9)
        return utc.strftime("%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return dt_str


def _parse_value(raw_val, metric: str) -> tuple[float | None, str | None]:
    """raw 값 → (value, missing_reason)"""
    if raw_val is None or str(raw_val).strip() == "":
        return None, "MISSING"
    try:
        v = float(raw_val)
    except (TypeError, ValueError):
        return None, "PARSE_ERROR"
    if v == 0.0 and metric in _ZERO_SENTINEL_METRICS:
        return None, "ZERO_SENTINEL"
    return v, None


def _load_flatline_minutes() -> int | None:
    """tide.flatline_minutes 운영 조정 값 로드. <미결>이면 None"""
    import os
    env_path = os.environ.get("OPERATIONAL_CONFIG_PATH")
    if not env_path:
        return None
    try:
        from common.config import load_operational
        cfg = load_operational(env_path)
        return cfg.get("tide", {}).get("flatline_minutes")
    except SystemExit:
        return None


def _apply_flatline_flags(rows: list[dict], flatline_minutes: int) -> None:
    """
    값 멈춤 감지 — STALE_SUSPECT 플래그.
    station×metric별 관측 시각 순서로 같은 값이 flatline_minutes 이상 연속이면 플래그.
    """
    from collections import defaultdict

    # station×metric → [(observed_at_utc, value, row_index)] 정렬
    groups: dict[tuple, list[tuple]] = defaultdict(list)
    for idx, row in enumerate(rows):
        key = (row["station_id"], row["metric"])
        groups[key].append((row["observed_at_utc"], row["value"], idx))

    for key, entries in groups.items():
        entries.sort(key=lambda x: x[0])  # 시각 순 정렬

        # 연속 같은 값 구간 탐색
        streak_start_idx = 0
        for i in range(1, len(entries)):
            prev_val = entries[i - 1][1]
            cur_val = entries[i][1]
            if prev_val is None or cur_val is None or cur_val != prev_val:
                streak_start_idx = i
                continue
            # 같은 값 연속: 구간 길이(분) 계산
            try:
                t_start = datetime.fromisoformat(entries[streak_start_idx][0])
                t_cur = datetime.fromisoformat(entries[i][0])
                elapsed = (t_cur - t_start).total_seconds() / 60
            except ValueError:
                continue
            if elapsed >= flatline_minutes:
                row_idx = entries[i][2]
                if "STALE_SUSPECT" not in rows[row_idx]["flags"]:
                    rows[row_idx]["flags"].append("STALE_SUSPECT")


def _apply_station_inactive(rows: list[dict]) -> None:
    """
    관측소 미가동: 최근 24h 전 행이 결측이면 station_inactive=True.
    rows는 단일 수집의 결과 — 24h 기준을 rows 내 최신 시각으로 설정.
    """
    from collections import defaultdict

    station_rows: dict[str, list[dict]] = defaultdict(list)
    latest_utc: dict[str, str] = {}

    for row in rows:
        sid = row["station_id"]
        station_rows[sid].append(row)
        obs = row.get("observed_at_utc", "")
        if obs > latest_utc.get(sid, ""):
            latest_utc[sid] = obs

    for sid, s_rows in station_rows.items():
        cutoff_str = latest_utc.get(sid, "")
        if not cutoff_str:
            continue
        try:
            latest_dt = datetime.fromisoformat(cutoff_str)
            cutoff_dt = latest_dt - timedelta(hours=24)
            cutoff_utc = cutoff_dt.strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError:
            continue

        recent = [r for r in s_rows if r.get("observed_at_utc", "") >= cutoff_utc]
        if recent and all(r.get("value") is None for r in recent):
            for r in s_rows:
                r["station_inactive"] = True

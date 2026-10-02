"""
조위관측소 최신관측 가공 어댑터 (I-2)
- obsrvnDt KST naive → UTC 변환 (-9h) (SOURCES.md 기록)
- 0.000 결측 (R0): value=NULL, missing_reason='ZERO_SENTINEL'
- 값 멈춤 플래그 (STALE_SUSPECT): tide.flatline_minutes 초과 연속 동일 값
- 관측소 미가동 (STATION_INACTIVE): 최근 24h 전 행 결측
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone

from common.clock import kst_naive_to_utc_iso
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

    def __init__(self) -> None:
        self._flatline_minutes: float | None = None
        self._configured = False

    def configure(self, definitions: dict, operational: dict) -> None:
        """기동 시 한 번 — 운영 조정 tide.flatline_minutes를 받는다 (2.0.6절). 없으면 멈춘다"""
        value = (operational.get("tide") or {}).get("flatline_minutes")
        if value is None:
            raise SystemExit("운영 조정 tide.flatline_minutes 없음 — 값 멈춤 감지를 끈 채 기동하지 않는다")
        self._flatline_minutes = value
        self._configured = True

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
            observed_at_utc = kst_naive_to_utc_iso(obs_dt_str)

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
        # 운영 조정: tide.flatline_minutes — configure()로 기동 시 받는다. 받지 않았으면 멈춘다
        if not self._configured:
            raise RuntimeError("TideProcessorAdapter.configure() 전에 normalize() 호출 — 운영 조정 미주입")
        flatline_minutes = self._flatline_minutes

        for row in rows:
            raw_val = row.pop("_raw_value", None)
            metric = row["metric"]
            value, missing_reason = _parse_value(raw_val, metric)
            row["value"] = value
            row["missing_reason"] = missing_reason

        _apply_flatline_flags(rows, flatline_minutes)

        _apply_station_inactive(rows)

        return rows


    def stations(self, pr: ParsedResponse) -> list[dict]:
        """
        관측소 마스터 행 (5.3절, 결정 D5) — 원문의 좌표로. 경도 필드는 `lot`(1.2절, 오타 아님).
        좌표가 없거나 숫자가 아니면 그 관측소는 내지 않는다. active는 processor가 STATION_INACTIVE로 정한다
        """
        out: dict[str, dict] = {}
        for item in pr.items:
            code = item.get("obsCode") or item.get("obsCd") or ""
            if not code:
                continue
            try:
                lat, lng = float(item.get("lat")), float(item.get("lot"))
            except (TypeError, ValueError):
                continue
            out[f"tide:{code}"] = {
                "id": f"tide:{code}", "source_api": "tide",
                "name": item.get("obsName") or item.get("obsPostName"),
                "lat": lat, "lng": lng, "sea_area": None, "active": True,
            }
        return list(out.values())


# ── 헬퍼 ────────────────────────────────────────────────────────────────────




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

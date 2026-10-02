"""
어장환경 해수면 femoSeaList 가공 어댑터 (I-5)
참고: $SRC_API/verify_nifs_api.py::extract_dates() — DATE_Y/M/D 조립
     (조용히 넘기는 결함 → 명시적 오류로 수정)
- LATITUDE/LONGITUDE DMS → 십진도 (common/geo._dms.dms_to_decimal)
- 좌표 폐구간 검증 (common/geo._coords.validate_coords_closed)
- metric 3종(수온·염분·클로로필) × layer 2종(S표층/B저층) = 6행/레코드
- R0: water_temp·salinity의 0.000 → ZERO_SENTINEL (클로로필 제외)
- 게시 감시 결과(femoSeaList-watch): publication_checks 행 생성
"""
from __future__ import annotations
import sys
from datetime import datetime, timedelta

from common.classifier import ParsedResponse
from common.config import load_definitions
from common.geo import dms_to_decimal, validate_coords_closed

API_ID = "femoSeaList"
API_ID_WATCH = "femoSeaList-watch"
AXIS = "chlorophyll"

# 원문 필드 → (metric, layer) — I-5에서 원문 확인 (SOURCES.md 기록)
_METRIC_FIELDS: list[tuple[str, str, str]] = [
    ("TEMP_S", "water_temp",  "S"),
    ("TEMP_B", "water_temp",  "B"),
    ("SAL_S",  "salinity",    "S"),
    ("SAL_B",  "salinity",    "B"),
    ("CHL_S",  "chlorophyll", "S"),
    ("CHL_B",  "chlorophyll", "B"),
]

# R0: 0.000 결측 대상 (수온·염분만; 클로로필 제외)
_ZERO_SENTINEL_METRICS = {"water_temp", "salinity"}


class FisheryProcessorAdapter:
    api_id = API_ID

    def interpret(self, pr: ParsedResponse, raw_meta: dict) -> list[dict]:
        defs = load_definitions()
        lat_range = tuple(defs["geo"]["lat_range"])
        lng_range = tuple(defs["geo"]["lng_range"])
        raw_id = raw_meta.get("raw_id", "")

        rows: list[dict] = []
        for r in pr.items:
            fishery = str(r.get("FISHERY", "") or "").strip()
            location_point = str(r.get("LOCATION_POINT", "") or "").strip()
            if not fishery or not location_point:
                continue
            station_id = f"fishery:{fishery}-{location_point}"

            try:
                surveyed_on = _assemble_date(r)
                observed_at_utc = _assemble_observed_at_utc(r, surveyed_on)
            except ValueError as e:
                print(f"[fishery-processor] 날짜·시각 오류 skip: {e}", file=sys.stderr)
                continue

            lat = dms_to_decimal(r.get("LATITUDE", ""))
            lng = dms_to_decimal(r.get("LONGITUDE", ""))
            if lat is None or lng is None:
                continue
            if not validate_coords_closed(lat, lng, lat_range, lng_range):
                continue

            for api_field, metric, layer in _METRIC_FIELDS:
                rows.append({
                    "station_id": station_id,
                    "observed_at_utc": observed_at_utc,
                    "surveyed_on": surveyed_on,
                    "layer": layer,
                    "metric": metric,
                    "_raw_value": r.get(api_field),
                    "missing_reason": None,
                    "raw_id": raw_id,
                })
        return rows

    def stations(self, pr: ParsedResponse) -> list[dict]:
        """관측소 마스터 행 (5.3절, 결정 D5) — 원문 도분초 좌표를 십진도로(폐구간 통과분만). name = FISHERY"""
        defs = load_definitions()
        lat_range = tuple(defs["geo"]["lat_range"])
        lng_range = tuple(defs["geo"]["lng_range"])
        out: dict[str, dict] = {}
        for r in pr.items:
            fishery = str(r.get("FISHERY", "") or "").strip()
            location_point = str(r.get("LOCATION_POINT", "") or "").strip()
            if not fishery or not location_point:
                continue
            lat = dms_to_decimal(r.get("LATITUDE", ""))
            lng = dms_to_decimal(r.get("LONGITUDE", ""))
            if lat is None or lng is None or not validate_coords_closed(lat, lng, lat_range, lng_range):
                continue
            sid = f"fishery:{fishery}-{location_point}"
            out[sid] = {"id": sid, "source_api": "fishery", "name": fishery,
                        "lat": lat, "lng": lng, "sea_area": None, "active": True}
        return list(out.values())

    def normalize(self, rows: list[dict]) -> list[dict]:
        for row in rows:
            raw_val = row.pop("_raw_value", None)
            row["value"], row["missing_reason"] = _parse_value(raw_val, row["metric"])
        return rows


class FisheryWatchProcessorAdapter:
    """게시 감시 결과 → publication_checks 행. 호출 실패를 게시 대기로 삼키지 않는다."""
    api_id = API_ID_WATCH

    def interpret(self, pr: ParsedResponse, raw_meta: dict) -> list[dict]:
        raw_id = raw_meta.get("raw_id", "")
        checked_at_utc = raw_meta.get("fetched_at_utc", "")
        target_year_raw = raw_meta.get("target_year")
        target_year = int(target_year_raw) if target_year_raw is not None else None
        prev_total_count = raw_meta.get("prev_total_count")

        ok_status = pr.parse_status in ("OK", "OK_EMPTY")
        if ok_status:
            total_count: int | None = len(pr.items)
            delta: int | None = (
                total_count - (prev_total_count or 0)
                if prev_total_count is not None
                else None
            )
        else:
            total_count = None
            delta = None

        return [{
            "_type": "publication_check",
            "axis": AXIS,
            "checked_at_utc": checked_at_utc,
            "target_year": target_year,
            "total_count": total_count,
            "prev_total_count": prev_total_count,
            "delta": delta,
            "raw_id": raw_id,
            "parse_status": pr.parse_status,
        }]

    def normalize(self, rows: list[dict]) -> list[dict]:
        return rows


def _assemble_date(r: dict) -> str:
    """DATE_Y·DATE_M·DATE_D 정수 변환 후 조립. 누락·변환 실패 시 명시적 오류."""
    y = r.get("DATE_Y")
    m = r.get("DATE_M")
    d = r.get("DATE_D")
    if y is None or m is None or d is None:
        raise ValueError(f"날짜 필드 누락: DATE_Y={y} DATE_M={m} DATE_D={d}")
    try:
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    except (ValueError, TypeError) as e:
        raise ValueError(f"날짜 변환 실패: Y={y} M={m} D={d}") from e


def _assemble_observed_at_utc(r: dict, surveyed_on: str) -> str:
    """
    조사 시각 = DATE_Y/M/D + TIME_H·TIME_I — KST(계획서 1.5절, 사용자 확인) → UTC ISO.
    시각이 없거나 범위 밖이면 추정하지 않고 오류 (그 레코드는 건너뛴다)
    """
    h, m = r.get("TIME_H"), r.get("TIME_I")
    try:
        hh, mm = int(h), int(m)
    except (ValueError, TypeError) as e:
        raise ValueError(f"조사 시각 없음·변환 실패: TIME_H={h} TIME_I={m}") from e
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        raise ValueError(f"조사 시각 범위 밖: TIME_H={h} TIME_I={m}")
    kst = datetime.fromisoformat(f"{surveyed_on}T{hh:02d}:{mm:02d}:00")
    return (kst - timedelta(hours=9)).strftime("%Y-%m-%dT%H:%M:%S")


def _parse_value(raw_val, metric: str) -> tuple[float | None, str | None]:
    if raw_val is None or str(raw_val).strip() == "":
        return None, "MISSING"
    try:
        v = float(raw_val)
    except (ValueError, TypeError):
        return None, "PARSE_ERROR"
    if v == 0.0 and metric in _ZERO_SENTINEL_METRICS:
        return None, "ZERO_SENTINEL"
    return v, None

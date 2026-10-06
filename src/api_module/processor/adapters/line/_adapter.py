"""
정선해양관측 sooList 가공 어댑터 (I-4)
이식: $SRC_IDW/src/normalizer.py::normalize_line_with_depth() (B v2) + line_depth_collect_v2.py::_assign_casts()
- obs_dtm KST naive → UTC 변환 (-9h) (SOURCES.md 기록)
- 좌표 폐구간 검증 — validate_coords_closed, 범위는 판정 정의에서 주입
- group_type: 원문 레코드 단위 계산 (metric 펼치기 전) — B v2 수정본 이식
- 캐스트 키: 연속 간격 > cast_gap_minutes → 새 캐스트, 버전은 cast_rule_version
- 전제 감시: 10 < gap ≤ 720분 → flags에 CAST_RULE_ASSUMPTION_BROKEN 추가 + stderr
- 빈 값 레코드: wtr_tmp·sal·dox 모두 빈 문자열 → value=None, missing_reason='MISSING'
"""
from __future__ import annotations
import sys
from collections import defaultdict
from datetime import datetime, timedelta

from common.clock import kst_naive_to_utc_iso
from common.classifier import ParsedResponse
from common.config import load_definitions
from common.geo import validate_coords_closed

API_ID = "sooList"

# API 필드 → metric 이름 (SKILL.md ③-3)
_METRIC_FIELDS: list[tuple[str, str]] = [
    ("wtr_tmp", "water_temp"),
    ("sal", "salinity"),
    ("dox", "dissolved_oxygen"),
]


class LineProcessorAdapter:
    api_id = API_ID

    def interpret(self, pr: ParsedResponse, raw_meta: dict) -> list[dict]:
        """items → (station_id, observed_at_utc, depth_m, metric, cast_id, ...) 행"""
        defs = load_definitions()
        lat_range: tuple[float, float] = tuple(defs["geo"]["lat_range"])
        lng_range: tuple[float, float] = tuple(defs["geo"]["lng_range"])
        cast_gap_minutes: int = int(defs.get("line", {}).get("cast_gap_minutes", 60))
        cast_rule_version = f"x{cast_gap_minutes}"
        raw_id = raw_meta.get("raw_id", "")

        # ── 1단계: 원문 레코드 단위 group_type 계산 (metric 펼치기 전) ───────
        group_type_map = _compute_group_types(pr.items)

        # ── 2단계: 좌표 검증 통과 레코드 수집 + 정점별 시각 순서 구성 ──────────
        station_recs: dict[tuple, list[tuple]] = defaultdict(list)
        valid_records: list[dict] = []

        for r in pr.items:
            gru = str(r.get("gru_nam", "") or "").strip()
            sln = str(r.get("sln_cde", "") or "").strip()
            sta = str(r.get("sta_cde", "") or "").strip()

            try:
                lat = float(r.get("lat") or "")
                lng = float(r.get("lon") or "")
            except (ValueError, TypeError):
                continue
            if not validate_coords_closed(lat, lng, lat_range, lng_range):
                continue

            obs_dtm_str = str(r.get("obs_dtm", "") or "").strip()
            obs_at_utc = kst_naive_to_utc_iso(obs_dtm_str)
            dtm = _parse_dtm(obs_dtm_str)

            wtr_dep_raw = r.get("wtr_dep")
            try:
                depth_m: float | None = float(wtr_dep_raw) if wtr_dep_raw not in (None, "") else None
            except (ValueError, TypeError):
                depth_m = None

            gt = group_type_map.get((gru, sln, sta, obs_dtm_str), "NO_ZERO")
            station_key = (gru, sln, sta)
            station_recs[station_key].append((dtm, r))

            valid_records.append({
                "_gru": gru, "_sln": sln, "_sta": sta,
                "_obs_dtm_str": obs_dtm_str,
                "_station_key": station_key,
                "_raw": r,
                "station_id": f"line:{gru}-{sln}-{sta}",
                "observed_at_utc": obs_at_utc,
                "depth_m": depth_m,
                "group_type": gt,
                "cast_rule_version": cast_rule_version,
                "raw_id": raw_id,
            })

        # ── 3단계: 정점별 시각 순 정렬 후 cast_id 할당 ──────────────────────
        for key in station_recs:
            station_recs[key].sort(key=lambda x: (x[0] is None, x[0]))

        cast_id_map, broken_keys = _assign_casts(station_recs, cast_gap_minutes)

        # ── 4단계: metric 행으로 펼치기 ─────────────────────────────────────
        rows: list[dict] = []
        for rec in valid_records:
            station_key = rec["_station_key"]
            obs_dtm_str = rec["_obs_dtm_str"]
            r = rec["_raw"]
            map_key = (station_key, obs_dtm_str)

            cast_id = cast_id_map.get(map_key, 0)

            # 빈 값 레코드: wtr_tmp·sal·dox 모두 빈 문자열
            is_blank = all(
                str(r.get(api_f, "") or "").strip() == ""
                for api_f, _ in _METRIC_FIELDS
            )

            flags: list[str] = []
            if map_key in broken_keys:
                flags.append("CAST_RULE_ASSUMPTION_BROKEN")

            for api_field, metric in _METRIC_FIELDS:
                rows.append({
                    "station_id": rec["station_id"],
                    "observed_at_utc": rec["observed_at_utc"],
                    "depth_m": rec["depth_m"],
                    "metric": metric,
                    "cast_id": cast_id,
                    "cast_rule_version": rec["cast_rule_version"],
                    "group_type": rec["group_type"],
                    "flags": list(flags),
                    "missing_reason": None,
                    "raw_id": rec["raw_id"],
                    "_raw_value": None if is_blank else r.get(api_field),
                    "_is_blank_record": is_blank,
                })

        return rows

    def stations(self, pr: ParsedResponse, raw_meta: dict | None = None) -> list[dict]:
        """관측소 마스터 행 (5.3절, 결정 D5) — 원문 십진도 좌표(폐구간 통과분만). sea_area = gru_nam"""
        defs = load_definitions()
        lat_range = tuple(defs["geo"]["lat_range"])
        lng_range = tuple(defs["geo"]["lng_range"])
        out: dict[str, dict] = {}
        for r in pr.items:
            gru = str(r.get("gru_nam", "") or "").strip()
            sln = str(r.get("sln_cde", "") or "").strip()
            sta = str(r.get("sta_cde", "") or "").strip()
            try:
                lat, lng = float(r.get("lat") or ""), float(r.get("lon") or "")
            except (ValueError, TypeError):
                continue
            if not validate_coords_closed(lat, lng, lat_range, lng_range):
                continue
            sid = f"line:{gru}-{sln}-{sta}"
            out[sid] = {"id": sid, "source_api": "line", "name": None,
                        "lat": lat, "lng": lng, "sea_area": gru or None, "active": True}
        return list(out.values())

    def normalize(self, rows: list[dict]) -> list[dict]:
        """_raw_value → value/missing_reason. CAST_RULE_ASSUMPTION_BROKEN 감사."""
        broken_keys: set = set()
        for row in rows:
            is_blank = row.pop("_is_blank_record", False)
            raw_val = row.pop("_raw_value", None)

            if is_blank:
                row["value"] = None
                row["missing_reason"] = "MISSING"
            else:
                row["value"], row["missing_reason"] = _parse_value(raw_val)

            if "CAST_RULE_ASSUMPTION_BROKEN" in row.get("flags", []):
                broken_keys.add((row["station_id"], row["observed_at_utc"]))

        if broken_keys:
            print(
                f"[line-processor] CAST_RULE_ASSUMPTION_BROKEN {len(broken_keys)}건"
                " (ops_events 적재는 I-6)",
                file=sys.stderr,
            )

        return rows


# ── 헬퍼 ────────────────────────────────────────────────────────────────────




def _parse_dtm(dt_str: str) -> datetime | None:
    """캐스트 시각 간격 계산용 파싱 (timezone-naive)"""
    if not dt_str:
        return None
    try:
        return datetime.strptime(dt_str.strip(), "%Y-%m-%d %H:%M")
    except ValueError:
        return None


def _parse_value(raw_val) -> tuple[float | None, str | None]:
    """raw 문자열 → (value, missing_reason). 빈 문자열 → MISSING"""
    if raw_val is None or str(raw_val).strip() == "":
        return None, "MISSING"
    try:
        return float(raw_val), None
    except (TypeError, ValueError):
        return None, "PARSE_ERROR"


def _compute_group_types(items: list[dict]) -> dict[tuple, str]:
    """
    원문 레코드 단위 group_type 계산 (metric 펼치기 전).
    이식: $SRC_IDW/src/normalizer.py::normalize_line_with_depth() 1단계 (B v2)
    키: (gru_nam, sln_cde, sta_cde, obs_dtm 원문 문자열)
    P: 0m 정확히 1개 + 양수 수심 ≥ 1개 (일반 프로파일)
    Z: 0m 2개 이상 (이상 레코드)
    S: 0m 1개, 총 레코드 = 1 (단독 표층)
    NO_ZERO: 0m 없음
    """
    grp_depths: dict[tuple, list] = defaultdict(list)
    grp_total: dict[tuple, int] = defaultdict(int)

    for r in items:
        gru = str(r.get("gru_nam", "") or "").strip()
        sln = str(r.get("sln_cde", "") or "").strip()
        sta = str(r.get("sta_cde", "") or "").strip()
        obs_dtm = str(r.get("obs_dtm", "") or "").strip()
        key = (gru, sln, sta, obs_dtm)

        wtr_dep_raw = r.get("wtr_dep")
        try:
            depth_m: float | None = float(wtr_dep_raw) if wtr_dep_raw not in (None, "") else None
        except (ValueError, TypeError):
            depth_m = None

        grp_depths[key].append(depth_m)
        grp_total[key] += 1

    return {
        key: _classify_group(depths, grp_total[key])
        for key, depths in grp_depths.items()
    }


def _classify_group(depths: list, total: int) -> str:
    non_null = [d for d in depths if d is not None]
    zeros = [d for d in non_null if d == 0.0]
    positives = [d for d in non_null if d > 0.0]
    n_z = len(zeros)
    if n_z == 0:
        return "NO_ZERO"
    if n_z >= 2:
        return "Z"
    # n_z == 1
    if total == 1:
        return "S"
    if positives:
        return "P"
    return "Z"  # 0m 1개, 양수 없음, 총 레코드 > 1


def _assign_casts(
    station_recs: dict[tuple, list[tuple]],
    x_min: int,
) -> tuple[dict, set]:
    """
    캐스트 키 할당 + 전제 감시.
    이식: $SRC_IDW/line_depth_collect_v2.py::_assign_casts() + cast_id_x60_map 구성

    Returns:
        cast_id_map: (station_key, obs_dtm_str) → 전역 cast_id
        broken_keys: 전제 감시 발동 기록 — (station_key, obs_dtm_str)
                     (10 < gap ≤ 720분인 전환에서 새 캐스트를 시작한 레코드)
    """
    cast_id_map: dict[tuple, int] = {}
    broken_keys: set[tuple] = set()
    next_id: int = 0

    for station_key, rlist in station_recs.items():
        # rlist는 이미 (dtm, r) 시각 순 정렬 완료
        cur_id = next_id
        next_id += 1

        prev_dtm: datetime | None = None

        for i, (dtm, r) in enumerate(rlist):
            obs_dtm_str = str(r.get("obs_dtm", "") or "").strip()
            map_key = (station_key, obs_dtm_str)

            if i == 0:
                cast_id_map[map_key] = cur_id
                prev_dtm = dtm
                continue

            if dtm is None or prev_dtm is None:
                cast_id_map[map_key] = cur_id
                if dtm is not None:
                    prev_dtm = dtm
                continue

            gap_min = (dtm - prev_dtm).total_seconds() / 60.0

            if gap_min > x_min:
                cur_id = next_id
                next_id += 1

            cast_id_map[map_key] = cur_id

            # 전제 감시: 10 < gap ≤ 720분
            if 10 < gap_min <= 720:
                broken_keys.add(map_key)

            prev_dtm = dtm

    return cast_id_map, broken_keys

"""
processor 적재 (계획서 2.1·2.3·4.3·4.5·4.9·5.3절, 지시서 I-12)

원문 하나의 처리 결과를 **한 트랜잭션**으로 쓴다 — 실패하면 아무것도 남기지 않고, 알림도 내지 않는다.
  raw_index        원문 메타로 색인 행 (결정 D1 — collector는 DB에 쓰지 않는다). 고유 storage_key라 멱등
  ingest_runs      status = 응답 상태 (결정 D6). 고유 (raw_id, parser_version)
  관측 테이블       dtRecent → observations / sooList → line_observations / femoSeaList → survey_observations
  publication_checks  femoSeaList-watch — 직전 감시 행에서 prev_total_count·delta
  bulletins …      redtideList — bulletins·bulletin_details·bulletin_detail_areas·unmapped_locations
  stations         어댑터 stations()의 원문 좌표 (결정 D5). tide는 STATION_INACTIVE면 active = false
  adapter_health   수집 원천 단위 (결정 D2·D4) — 원문의 첫 처리에서만 갱신
  ops_events       CAST_RULE_ASSUMPTION_BROKEN, 버려진 열·행, BULLETIN_WINDOW_MISSING(적조 직전 원문 대조 — 3.3절, 개정 18)

같은 원문·같은 파서 버전이 다시 오면(중복 알림) 아무것도 쓰지 않는다 — 결과가 같다(2.2절).
"""
from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime

from common.classifier import ParsedResponse
from common.repository import tables as t
from common.sources import base_api, source_of
from processor._health import next_adapter_health

# 관측 테이블 (base api_id → 테이블)
_OBS_TABLE = {
    "dtRecent": t.observations,
    "sooList": t.line_observations,
    "femoSeaList": t.survey_observations,
}

# 행에 있으나 테이블 열이 아닌 판정 보조 값 — 다른 곳에 옮겨 저장하므로 버려도 정보가 줄지 않는다
#   quality_flag·quality_rule → flags(SENSOR_QUALITY)·value=None(MISSING) / station_inactive → stations.active
#   parse_status(감시 행) → publication_checks.parse_status 열로 그대로 들어간다
_DERIVED_KEYS = frozenset({"quality_flag", "quality_rule", "station_inactive"})

_PUBLICATION_AXIS = "chlorophyll"


@dataclass
class LoadResult:
    raw_id: int
    status: str
    duplicate: bool = False
    rows_written: dict[str, int] = field(default_factory=dict)
    window_missing: int = 0               # 적조 직전 원문 대조 — 빠진 속보 수 (지표는 커밋 뒤 호출자가)
    window_skip: str | None = None        # 대조를 건너뛴 사유 (NO_PREV / PREV_UNREADABLE / NO_WINDOW)


# ── 응답 상태 (3.2절) ────────────────────────────────────────────────────────

def response_status(pr: ParsedResponse, meta: dict, completeness=None) -> str:
    """
    원문 메타의 호출 실패를 먼저 본다 — HTTP 오류·연결 실패는 `HTTP_ERROR`/`NET_ERROR`(3.2절).
    호출 타임아웃(`error.type = TIMEOUT`)은 연결 실패로 본다 — 결과 코드 `05`(`TIMEOUT_05`)와 다르다.
    그다음 응답 해석 상태, 해석이 정상이면 완전성 결과(`INCOMPLETE`·`FILTER_IGNORED`, 3.3절)
    """
    err = (meta or {}).get("error")
    if err:
        typ = err.get("type") if isinstance(err, dict) else None
        return "HTTP_ERROR" if typ == "HTTP_ERROR" else "NET_ERROR"
    http_status = (meta or {}).get("http_status")
    if isinstance(http_status, int) and http_status >= 400:
        return "HTTP_ERROR"
    status = pr.parse_status
    comp = getattr(completeness, "status", None)
    if status == "OK" and comp in ("INCOMPLETE", "FILTER_IGNORED"):
        return comp
    return status


# ── 값 변환 ──────────────────────────────────────────────────────────────────

def _to_datetime(v):
    if isinstance(v, datetime):
        return v.astimezone(timezone.utc).replace(tzinfo=None) if v.tzinfo else v
    if isinstance(v, str) and v:
        dt = datetime.fromisoformat(v.strip().replace("Z", "+00:00"))
        if dt.tzinfo:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    return None if v == "" else v


def _to_date(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str) and v:
        return date.fromisoformat(v.strip()[:10])
    return None if v == "" else v


def _fit(table, row: dict, dropped: Counter) -> dict:
    """테이블 열로 거르고 시각·날짜를 변환한다. 값이 있는데 버려지는 열은 dropped에 센다"""
    cols = table.c
    out = {}
    for k, v in row.items():
        if k in cols:
            ctype = cols[k].type
            if isinstance(ctype, DateTime):
                v = _to_datetime(v)
            elif isinstance(ctype, Date):
                v = _to_date(v)
            out[k] = v
        elif not k.startswith("_") and k not in _DERIVED_KEYS and v not in (None, "", []):
            dropped[(table.name, k)] += 1
    return out


def _storage_tag(storage_key: str) -> str | None:
    """raw/{api}/{yyyy}/{mm}/{dd}/{epoch_ms}_{tag}.json → tag (2.3절)"""
    name = storage_key.rsplit("/", 1)[-1]
    if name.endswith(".json"):
        name = name[:-5]
    return name.split("_", 1)[1] if "_" in name else None


# ── 적재 ─────────────────────────────────────────────────────────────────────

def load(
    repo,
    *,
    storage_key: str,
    api: str,
    meta: dict,
    body: str | None,
    pr: ParsedResponse,
    rows: list[dict],
    completeness,
    adapter,
    parser_version: str,
    now_utc: datetime,
    untimed_rows: int = 0,
) -> LoadResult:
    status = response_status(pr, meta, completeness)
    with repo.transaction() as tx:
        raw_id = _index_raw(tx, storage_key, api, meta, body)

        runs = tx.get_ingest_runs_for_raw(raw_id)
        if any(r["parser_version"] == parser_version for r in runs):
            return LoadResult(raw_id=raw_id, status=status, duplicate=True)
        first_time = not runs   # 재처리(파서 버전 변경)면 False — 헬스·검토 큐 횟수를 다시 세지 않는다

        tx.upsert_ingest_run([{
            "raw_id": raw_id,
            "parser_version": parser_version,
            "status": status,
            "result_code": pr.result_code,
            "total_count": pr.total_count,
            "item_count": len(pr.items),
            "format": pr.format,
            "format_mismatch": None,
            "processed_at_utc": now_utc,
        }])

        dropped: Counter = Counter()
        written: dict[str, int] = {}
        b = base_api(api)

        if api == "femoSeaList-watch":
            written.update(_load_publication(tx, raw_id, storage_key, rows, dropped))
        elif b == "redtideList":
            written.update(_load_bulletin(tx, raw_id, rows, dropped, now_utc, first_time))
        elif b in _OBS_TABLE:
            written.update(_load_observations(tx, b, raw_id, rows, dropped, now_utc))

        if hasattr(adapter, "stations") and body is not None:
            written.update(_load_stations(tx, adapter.stations(pr, meta), rows, dropped))

        if first_time:
            _update_health(tx, api, status, meta, now_utc)

        events = []
        if untimed_rows:
            events.append({"event_type": "LOAD_ROWS_SKIPPED", "api": api, "occurred_at_utc": now_utc,
                           "detail": {"raw_id": raw_id, "reason": "observed_at_utc 변환 실패", "rows": untimed_rows}})
        window = _check_bulletin_window(api, first_time, status, body, storage_key, meta, pr)
        if window is not None and window.missing:
            events.append({
                "event_type": "BULLETIN_WINDOW_MISSING", "api": api, "occurred_at_utc": now_utc,
                "detail": {"raw_key": storage_key, "prev_raw_key": window.prev_key,
                           "window": list(window.window), "missing": window.missing},
            })
        if dropped:
            events.append({
                "event_type": "LOAD_COLUMNS_DROPPED", "api": api, "occurred_at_utc": now_utc,
                "detail": {"raw_id": raw_id,
                           "columns": [{"table": tb, "column": c, "rows": n} for (tb, c), n in sorted(dropped.items())]},
            })
        if events:
            tx.insert_ops_events(events)

    return LoadResult(raw_id=raw_id, status=status, rows_written=written,
                      window_missing=len(window.missing) if window else 0,
                      window_skip=window.skip_reason if window else None)


def _check_bulletin_window(api: str, first_time: bool, status: str, body, storage_key: str, meta: dict, pr):
    """적조 직전 원문 대조 — 정기 원문의 첫 처리·정상 응답일 때만 (3.3절, 개정 18). 그 밖에는 None"""
    # processor.completeness._split_check가 이 모듈을 import하므로 여기서 늦게 가져온다 (순환 방지)
    from common.raw_store import get_raw_body, get_raw_meta, list_raw_keys
    from processor.completeness._bulletin_window import API_ID, NORMAL_STATUSES, check_window
    if api != API_ID or not first_time or status not in NORMAL_STATUSES or body is None:
        return None
    return check_window(storage_key, meta, pr, list_keys=list_raw_keys, read_meta=get_raw_meta,
                        read_body=get_raw_body, judge=lambda p, m: response_status(p, m))


def _index_raw(tx, storage_key: str, api: str, meta: dict, body: str | None) -> int:
    body_bytes = body.encode("utf-8") if body is not None else None
    fetched = _to_datetime(meta.get("fetched_at")) if meta.get("fetched_at") else None
    return tx.insert_raw_index({
        "api": api,
        "tag": _storage_tag(storage_key),
        "storage_key": storage_key,
        "fetched_at_utc": fetched or datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0),
        "http_status": meta.get("http_status"),
        "body_sha256": hashlib.sha256(body_bytes).hexdigest() if body_bytes is not None else None,
        "body_bytes": len(body_bytes) if body_bytes is not None else None,
        "precheck_code": meta.get("precheck_code"),
    })


def _load_observations(tx, b: str, raw_id: int, rows: list[dict], dropped: Counter, now_utc) -> dict:
    table = _OBS_TABLE[b]
    out, skipped = [], 0
    broken = 0
    for r in rows:
        row = _fit(table, {**r, "raw_id": raw_id}, dropped)
        if b == "sooList":
            if "CAST_RULE_ASSUMPTION_BROKEN" in (r.get("flags") or []):
                broken += 1
            if row.get("depth_m") is None:      # PK 열 — 수심 없는 행은 키를 만들 수 없다
                skipped += 1
                continue
        out.append(row)
    upsert = {"dtRecent": tx.upsert_observations,
              "sooList": tx.upsert_line_observations,
              "femoSeaList": tx.upsert_survey_observations}[b]
    if out:
        upsert(out)
    events = []
    if broken:
        events.append({"event_type": "CAST_RULE_ASSUMPTION_BROKEN", "api": b, "occurred_at_utc": now_utc,
                       "detail": {"raw_id": raw_id, "rows": broken}})
    if skipped:
        events.append({"event_type": "LOAD_ROWS_SKIPPED", "api": b, "occurred_at_utc": now_utc,
                       "detail": {"raw_id": raw_id, "table": table.name, "reason": "depth_m 없음", "rows": skipped}})
    if events:
        tx.insert_ops_events(events)
    return {table.name: len(out)}


def _load_publication(tx, raw_id: int, storage_key: str, rows: list[dict], dropped: Counter) -> dict:
    """게시 감시 (4.5절) — target_year는 tag(`watch_{year}`)에서, 직전 건수는 적재된 직전 감시 행에서"""
    tag = _storage_tag(storage_key) or ""
    year = int(tag.split("_", 1)[1]) if tag.startswith("watch_") and tag.split("_", 1)[1].isdigit() else None
    out = []
    for r in rows:
        row = {**r, "raw_id": raw_id}
        if row.get("target_year") is None:
            row["target_year"] = year
        checked = _to_datetime(row.get("checked_at_utc"))
        prev = [p for p in tx.get_publication_checks(row.get("axis") or _PUBLICATION_AXIS)
                if p["target_year"] == row["target_year"] and p["raw_id"] != raw_id
                and p.get("total_count") is not None
                and (checked is None or p["checked_at_utc"] <= checked)]
        if prev:
            last = max(prev, key=lambda p: p["checked_at_utc"])
            row["prev_total_count"] = last["total_count"]
            if row.get("total_count") is not None:
                row["delta"] = row["total_count"] - last["total_count"]
        out.append(_fit(t.publication_checks, row, dropped))
    if out:
        tx.upsert_publication_checks(out)
    return {"publication_checks": len(out)}


def _load_bulletin(tx, raw_id: int, rows: list[dict], dropped: Counter, now_utc, first_time: bool) -> dict:
    groups: dict[str, list[dict]] = {"bulletin": [], "bulletin_detail": [], "bulletin_detail_area": [],
                                     "unmapped_location": []}
    for r in rows:
        groups.setdefault(r.get("_type", ""), []).append(r)

    bl = [_fit(t.bulletins, {**r, "raw_id": raw_id}, dropped) for r in groups["bulletin"]]
    dt = [_fit(t.bulletin_details, r, dropped) for r in groups["bulletin_detail"]]
    ar = [_fit(t.bulletin_detail_areas, r, dropped) for r in groups["bulletin_detail_area"]]
    if bl:
        tx.upsert_bulletins(bl)
    if dt:
        tx.upsert_bulletin_details(dt)
    if ar:
        tx.upsert_bulletin_detail_areas(ar)

    # 검토 큐 (4.3절) — 같은 키면 행을 늘리지 않고 횟수·마지막 시각만. 재처리에서는 횟수를 다시 세지 않는다
    seen = Counter(r["area_key"] for r in groups["unmapped_location"])
    sample = {r["area_key"]: r for r in groups["unmapped_location"]}
    existing = {e["area_key"]: e for e in tx.get_unmapped_locations(list(seen))}
    um = []
    for key, n in seen.items():
        e = existing.get(key)
        um.append({
            "area_key": key,
            "kind": (e or sample[key])["kind"],
            "raw_sample": (e or {}).get("raw_sample") or sample[key].get("raw_sample"),
            "occurrence_count": (e["occurrence_count"] if e else 0) + (n if first_time else 0),
            "first_seen_utc": e["first_seen_utc"] if e else now_utc,
            "last_seen_utc": now_utc,
            "resolved_at_utc": e.get("resolved_at_utc") if e else None,
        })
    if um:
        tx.upsert_unmapped_locations(um)
    return {"bulletins": len(bl), "bulletin_details": len(dt),
            "bulletin_detail_areas": len(ar), "unmapped_locations": len(um)}


def _load_stations(tx, stations: list[dict], rows: list[dict], dropped: Counter) -> dict:
    inactive = {r["station_id"] for r in rows if r.get("station_inactive")}
    out = []
    for s in stations:
        row = dict(s)
        if row["id"] in inactive:
            row["active"] = False
        out.append(_fit(t.stations, row, dropped))
    if out:
        tx.upsert_stations(out)
    return {"stations": len(out)}


def _update_health(tx, api: str, status: str, meta: dict, now_utc) -> None:
    source = source_of(api)
    if source is None:
        return
    prev = next((h for h in tx.get_adapter_health() if h["adapter"] == source), None)
    nxt = next_adapter_health(prev, source, status, now_utc, retried=bool(meta.get("_retried")))
    tx.upsert_adapter_health([nxt])

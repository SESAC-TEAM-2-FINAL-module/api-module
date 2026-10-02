"""
분할 합산 검사기 (계획서 3.3절 "분할 합산 처리 경로", 개정 17)

`completeness.collected` 하나를 받아, 알림에 실린 원문을 **원문 저장소에서 직접 읽어** 한 번에 판정한다.
processor의 처리 결과(ingest_runs)를 기다리지 않는다. 중간 상태가 없으므로 중복 알림·동시 처리와 무관하다.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from urllib.parse import parse_qs, urlsplit

from common.classifier import ParsedResponse, parse
from common.metrics import completeness_last_checked_timestamp, completeness_mismatch_total
from common.raw_store import get_raw_body, get_raw_meta
from processor._load import response_status
from processor.completeness._checker import check_split_completeness

_NORMAL = frozenset({"OK", "OK_EMPTY", "NO_DATA"})
# INVALID 사유가 여럿이면 앞의 것 — 원문이 없으면 나머지는 볼 수 없다
_REASON_ORDER = ("RAW_MISSING", "PART_STATUS", "WINDOW_MISMATCH", "FILTER_IGNORED")
# "같은 결과" 비교 열 — checked_at_utc는 보지 않는다 (3.3절)
_COMPARE = ("status", "reason", "truncated_side", "single_count", "split_sum", "parts", "window_start", "window_end")


def _item_date(api: str, item: dict) -> str | None:
    """요청 창 밖 행 검사용 날짜(KST, YYYYMMDD). 못 읽으면 None — 판정에 쓰지 않는다"""
    try:
        if api == "redtideList":
            return str(item.get("day_report") or "")[:8] or None
        if api == "sooList":
            return str(item.get("obs_dtm") or "")[:10].replace("-", "") or None
        if api == "femoSeaList":
            return f"{int(item['DATE_Y']):04d}{int(item['DATE_M']):02d}{int(item['DATE_D']):02d}"
    except (KeyError, TypeError, ValueError):
        return None
    return None


def _requested_window(meta: dict) -> tuple[str | None, str | None]:
    params = meta.get("params") or {}
    if "sdate" not in params and meta.get("url"):
        q = parse_qs(urlsplit(meta["url"]).query)
        params = {k: v[0] for k, v in q.items()}
    return params.get("sdate"), params.get("edate")


def _read(api: str, raw_id: str, start: str, end: str) -> dict:
    """원문 하나 → {"count": n} 또는 {"reason": …}"""
    meta = get_raw_meta(raw_id)
    if meta is None:
        return {"reason": "RAW_MISSING"}
    body = get_raw_body(raw_id)
    pr = parse(body) if body is not None else ParsedResponse(parse_status="PARSE_FAILURE")
    if response_status(pr, meta) not in _NORMAL:
        return {"reason": "PART_STATUS"}
    if _requested_window(meta) != (start, end):
        return {"reason": "WINDOW_MISMATCH"}
    for item in pr.items:
        d = _item_date(api, item)
        if d is not None and not (start <= d <= end):
            return {"reason": "FILTER_IGNORED"}
    return {"count": len(pr.items)}


def _d(ymd: str) -> date:
    return date(int(ymd[:4]), int(ymd[4:6]), int(ymd[6:8]))


def judge(payload: dict) -> dict:
    """알림 하나 → completeness_checks 행(checked_at_utc 제외)"""
    api, ws, we = payload["api"], payload["window_start"], payload["window_end"]
    parts = payload.get("parts") or []
    row = {"run_key": payload["run_key"], "api": api, "window_start": _d(ws), "window_end": _d(we),
           "parts": len(parts), "single_count": None, "split_sum": None, "truncated_side": None,
           "status": "INVALID", "reason": None}

    single = _read(api, payload["single_raw_id"], ws, we)
    part_reads = [(p, _read(api, p["raw_id"], p["start"], p["end"])) for p in parts]
    reasons = {r["reason"] for r in [single] + [pr for _, pr in part_reads] if "reason" in r}
    if reasons:
        row["reason"] = next(x for x in _REASON_ORDER if x in reasons)
        return row

    res = check_split_completeness((ws, we, single["count"]),
                                   [(p["start"], p["end"], r["count"]) for p, r in part_reads])
    row.update(status=res.status, truncated_side=res.truncated_side,
               single_count=single["count"], split_sum=sum(r["count"] for _, r in part_reads))
    return row


def run_completeness_check(payload: dict, repo, now_utc: datetime | None = None) -> dict | None:
    """판정 → 기록. 같은 결과면 다시 쓰지 않고, RAW_MISSING은 판정이 난 행을 덮지 않는다 (3.3절)"""
    now = (now_utc or datetime.now(timezone.utc)).replace(tzinfo=None, microsecond=0)
    if payload.get("schema") != "queue-v1":
        repo.insert_ops_events([{"event_type": "CONTRACT_VERSION_MISMATCH", "api": payload.get("api"),
                                 "occurred_at_utc": now,
                                 "detail": {"topic": "completeness.collected", "schema": payload.get("schema")}}])
        return None

    row = {**judge(payload), "checked_at_utc": now}
    wrote = False
    with repo.transaction() as tx:
        old = tx.get_completeness_check(row["run_key"], row["api"])
        same = old is not None and all(old.get(k) == row[k] for k in _COMPARE)
        keep_old = old is not None and row["reason"] == "RAW_MISSING" and old.get("reason") != "RAW_MISSING"
        if not same and not keep_old:
            tx.upsert_completeness_checks([row])
            wrote = True
            if row["status"] != "OK":           # 운영 이벤트는 결과 행과 같은 트랜잭션 (3.3절)
                tx.insert_ops_events([{
                    "event_type": row["status"], "api": row["api"], "occurred_at_utc": now,
                    "detail": {"run_key": row["run_key"], "reason": row["reason"],
                               "truncated_side": row["truncated_side"],
                               "single_count": row["single_count"], "split_sum": row["split_sum"]},
                }])
    if wrote and row["status"] != "OK":           # 지표는 커밋 뒤
        completeness_mismatch_total.labels(api=row["api"], status=row["status"]).inc()
    for api, ts in repo.get_latest_completeness_checked().items():
        if ts is not None:
            completeness_last_checked_timestamp.labels(api=api).set(ts.replace(tzinfo=timezone.utc).timestamp())
    return row

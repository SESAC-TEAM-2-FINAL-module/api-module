"""
적조정보 수집 어댑터 (I-3)
- redtideList: 최근 14일 창 수집, 페이징 없음
- collector-completeness: 같은 창을 월 분할 수집 (3.3절), tag='completeness'
"""
from __future__ import annotations
import sys
from datetime import date, timedelta

from common.config import load_env_config
from common.http import fetch
from common.queue import Queue, Message
from common.raw_store import save_raw

API_ID = "redtideList"
API_ID_COMPLETENESS = "redtideList-completeness"
_WINDOW_DAYS = 14


class BulletinCollectorAdapter:
    api_id = API_ID

    def run(self, queue: Queue) -> None:
        env = load_env_config()
        key = env.get_key(env.nifs_key_bulletin_var)
        today = date.today()
        sdate = (today - timedelta(days=_WINDOW_DAYS - 1)).strftime("%Y%m%d")
        edate = today.strftime("%Y%m%d")
        tag = f"{sdate}_{edate}"

        result = _collect_window(env.nifs_url, key, sdate, edate)
        if result is None:
            print("[bulletin-collector] 수집 실패", file=sys.stderr)
            return
        raw_id = save_raw(API_ID, tag, result)
        queue.publish(Message(
            topic="raw.fetched",
            payload={
                "schema": "queue-v1",
                "topic": "raw.fetched",
                "raw_id": raw_id,
                "api": API_ID,
                "tag": tag,
                "fetched_at_utc": result.get("fetched_at", ""),
            },
        ))


class BulletinCompletenessAdapter:
    """월 분할 수집 — collector-completeness 워크로드 (3.3절)."""
    api_id = API_ID_COMPLETENESS

    def run(self, queue: Queue) -> None:
        env = load_env_config()
        key = env.get_key(env.nifs_key_bulletin_var)
        today = date.today()
        start = today - timedelta(days=_WINDOW_DAYS - 1)
        segments = _split_by_month(start, today)

        for seg_start, seg_end in segments:
            sdate = seg_start.strftime("%Y%m%d")
            edate = seg_end.strftime("%Y%m%d")
            tag = f"completeness_{sdate}_{edate}"

            result = _collect_window(env.nifs_url, key, sdate, edate)
            if result is None:
                print(f"[bulletin-completeness] 수집 실패: {sdate}~{edate}", file=sys.stderr)
                continue
            raw_id = save_raw(API_ID_COMPLETENESS, tag, result)
            queue.publish(Message(
                topic="raw.fetched",
                payload={
                    "schema": "queue-v1",
                    "topic": "raw.fetched",
                    "raw_id": raw_id,
                    "api": API_ID_COMPLETENESS,
                    "tag": tag,
                    "fetched_at_utc": result.get("fetched_at", ""),
                },
            ))


def _collect_window(url: str, key: str, sdate: str, edate: str) -> dict | None:
    params = {
        "id": "redtideList",
        "key": key,
        "sdate": sdate,
        "edate": edate,
    }
    result = fetch(url, params, "key", key)
    if result.get("error"):
        return None
    return result


def _split_by_month(start: date, end: date) -> list[tuple[date, date]]:
    """날짜 범위를 월 경계로 분할한다."""
    segments: list[tuple[date, date]] = []
    cur = start
    while cur <= end:
        if cur.month == 12:
            month_end = date(cur.year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(cur.year, cur.month + 1, 1) - timedelta(days=1)
        seg_end = min(month_end, end)
        segments.append((cur, seg_end))
        cur = seg_end + timedelta(days=1)
    return segments

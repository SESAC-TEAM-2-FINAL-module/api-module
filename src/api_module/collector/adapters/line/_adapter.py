"""
정선해양관측 sooList 수집 어댑터 (I-4)
참고: $SRC_IDW/src/collector.py::collect_line_survey() — 1년 창 1회 호출
- 페이징 없음: pageNo 파라미터를 쓰지 않는다 — 한 번 호출하면 전체가 온다
  (여러 번 호출하면 같은 데이터가 중복된다)
- collector-completeness: 같은 창을 월 분할 호출 (3.3절), tag='completeness_...'
"""
from __future__ import annotations
import sys
from datetime import date, timedelta

from common.config import load_env_config
from common.http import fetch
from common.queue import Queue, Message
from common.raw_store import save_raw

API_ID = "sooList"
API_ID_COMPLETENESS = "sooList-completeness"


class LineCollectorAdapter:
    api_id = API_ID

    def run(self, queue: Queue) -> None:
        env = load_env_config()
        key = env.get_key(env.nifs_key_line_var)
        sdate, edate = _window()
        tag = f"{sdate}_{edate}"

        result = _collect_window(env.nifs_url, key, sdate, edate)
        if result is None:
            print("[line-collector] 수집 실패", file=sys.stderr)
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


class LineCompletenessAdapter:
    """월 분할 수집 — collector-completeness 워크로드 (3.3절)."""
    api_id = API_ID_COMPLETENESS

    def run(self, queue: Queue) -> None:
        env = load_env_config()
        key = env.get_key(env.nifs_key_line_var)
        sdate_d, edate_d = _window_as_date()
        segments = _split_by_month(sdate_d, edate_d)

        for seg_start, seg_end in segments:
            sdate = seg_start.strftime("%Y%m%d")
            edate = seg_end.strftime("%Y%m%d")
            tag = f"completeness_{sdate}_{edate}"

            result = _collect_window(env.nifs_url, key, sdate, edate)
            if result is None:
                print(f"[line-completeness] 수집 실패: {sdate}~{edate}", file=sys.stderr)
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


def _window() -> tuple[str, str]:
    """1년 창: (sdate_str, edate_str) YYYYMMDD 형식"""
    sdate_d, edate_d = _window_as_date()
    return sdate_d.strftime("%Y%m%d"), edate_d.strftime("%Y%m%d")


def _window_as_date() -> tuple[date, date]:
    edate = date.today()
    sdate = edate - timedelta(days=365)
    return sdate, edate


def _collect_window(url: str, key: str, sdate: str, edate: str) -> dict | None:
    """sooList 1회 호출 — 페이징 없음, pageNo 사용 금지"""
    params = {
        "id": "sooList",
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

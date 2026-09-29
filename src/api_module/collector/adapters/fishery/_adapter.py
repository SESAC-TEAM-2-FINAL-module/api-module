"""
어장환경 해수면 femoSeaList 수집 어댑터 (I-5)
참고: $SRC_IDW/src/collector.py::collect_fishery_sea() — 달력 연도 단위 호출
- 달력 연도 단위: sdate=YYYY0101, edate=YYYY1231 (올해는 오늘까지)
- 백필(femoSeaList-backfill): 올해 직전 연도부터 거슬러, 연속 2개 연도 0건이면 정지
- 분할 수집(femoSeaList-completeness): collector-completeness 워크로드용 월 분할
- 페이징 없음 (pageNo 무시)
"""
from __future__ import annotations
import sys
from datetime import date, timedelta

from common.classifier import parse
from common.config import load_env_config
from common.http import fetch
from common.queue import Queue, Message
from common.raw_store import save_raw

API_ID = "femoSeaList"
API_ID_BACKFILL = "femoSeaList-backfill"
API_ID_COMPLETENESS = "femoSeaList-completeness"


class FisheryBackfillAdapter:
    """과거 연도 백필 — collector-fishery-backfill 워크로드 (Job, 1회)."""
    api_id = API_ID_BACKFILL

    def run(self, queue: Queue) -> None:
        env = load_env_config()
        key = env.get_key(env.nifs_key_fishery_sea_var)
        today = date.today()
        consecutive_zero = 0

        for year in range(today.year - 1, 0, -1):
            result = _collect_year(env.nifs_url, key, year, today)
            if result is None:
                print(f"[fishery-backfill] 수집 실패: {year}", file=sys.stderr)
                consecutive_zero += 1
            else:
                pr = parse(result.get("body", ""))
                count = len(pr.items)
                if count == 0:
                    consecutive_zero += 1
                    print(f"[fishery-backfill] {year}: 0건", file=sys.stderr)
                else:
                    consecutive_zero = 0
                raw_id = save_raw(API_ID, str(year), result)
                queue.publish(Message(
                    topic="raw.fetched",
                    payload={
                        "schema": "queue-v1",
                        "topic": "raw.fetched",
                        "raw_id": raw_id,
                        "api": API_ID,
                        "tag": str(year),
                        "fetched_at_utc": result.get("fetched_at", ""),
                    },
                ))

            if consecutive_zero >= 2:
                print("[fishery-backfill] 연속 2개 연도 0건 — 정지", file=sys.stderr)
                break


class FisheryCompletenessAdapter:
    """올해 창 월 분할 수집 — collector-completeness 워크로드 (3.3절)."""
    api_id = API_ID_COMPLETENESS

    def run(self, queue: Queue) -> None:
        env = load_env_config()
        key = env.get_key(env.nifs_key_fishery_sea_var)
        today = date.today()
        year_start = date(today.year, 1, 1)
        segments = _split_by_month(year_start, today)

        for seg_start, seg_end in segments:
            sdate = seg_start.strftime("%Y%m%d")
            edate = seg_end.strftime("%Y%m%d")
            tag = f"completeness_{sdate}_{edate}"

            result = _collect_window(env.nifs_url, key, sdate, edate)
            if result is None:
                print(f"[fishery-completeness] 수집 실패: {sdate}~{edate}", file=sys.stderr)
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


def _collect_year(url: str, key: str, year: int, today: date) -> dict | None:
    sdate = f"{year}0101"
    edate = f"{year}1231" if year < today.year else today.strftime("%Y%m%d")
    return _collect_window(url, key, sdate, edate)


def _collect_window(url: str, key: str, sdate: str, edate: str) -> dict | None:
    params = {"id": "femoSeaList", "key": key, "sdate": sdate, "edate": edate}
    result = fetch(url, params, "key", key)
    if result.get("error"):
        return None
    return result


def _split_by_month(start: date, end: date) -> list[tuple[date, date]]:
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

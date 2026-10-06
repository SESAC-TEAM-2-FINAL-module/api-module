"""
분할 합산 수집 (계획서 3.3절 "분할 합산 처리 경로", 개정 17)

원천마다 같은 실행에서 **단일 창을 먼저 1회, 이어서 그 창의 월 분할**을 받고, 다 받으면
`completeness.collected`를 낸다. 알림에는 **무엇을 받았는지만** 싣는다 — 건수·판정은 싣지 않는다(2.1절).
호출 실패도 원문으로 남긴다(2.3절) — 판정은 검사기 몫.
분할 원문에는 `raw.fetched`를 내지 않는다 — processor는 받지 않고 검사기만 원문 저장소에서 읽는다(개정 17 보완).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable

from common.clock import kst_today, split_by_month
from common.queue import Message, Queue
from common.raw_store import save_raw


@dataclass(frozen=True)
class CompletenessRun:
    """워크로드 실행 하나 — 실행 키와 창의 끝(KST 어제)을 시작 때 한 번 정해 세 원천이 함께 쓴다"""
    run_key: str
    end: date

    @staticmethod
    def start(now_utc: datetime | None = None) -> "CompletenessRun":
        now = now_utc or datetime.now(timezone.utc)
        return CompletenessRun(run_key=now.strftime("%Y%m%dT%H%M%S"),
                               end=kst_today(now) - timedelta(days=1))


def _ymd(d: date) -> str:
    return d.strftime("%Y%m%d")


def collect(
    *,
    api_base: str,
    api_completeness: str,
    window: tuple[date, date],
    fetch_window: Callable[[str, str], dict],
    run: CompletenessRun,
    queue: Queue,
) -> dict:
    """단일 창 → 월 분할 순서로 받아 원문을 저장하고, 마지막에 completeness.collected 하나. 알림 본문을 돌려준다"""
    start, end = window

    def _save(tag: str, s: date, e: date) -> str:
        result = fetch_window(_ymd(s), _ymd(e))
        return save_raw(api_completeness, tag, result)

    single = _save(f"cmp_{run.run_key}_single_{_ymd(start)}_{_ymd(end)}", start, end)
    parts = []
    for ps, pe in split_by_month(start, end):
        parts.append({"start": _ymd(ps), "end": _ymd(pe),
                      "raw_id": _save(f"cmp_{run.run_key}_part_{_ymd(ps)}_{_ymd(pe)}", ps, pe)})

    payload = {
        "schema": "queue-v2", "topic": "completeness.collected",
        "run_key": run.run_key, "api": api_base,
        "window_start": _ymd(start), "window_end": _ymd(end),
        "single_raw_id": single, "parts": parts,
    }
    queue.publish(Message(topic="completeness.collected", payload=payload))
    return payload

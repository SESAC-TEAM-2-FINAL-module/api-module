"""
적조정보 수집 어댑터 (I-3, I-14)
- redtideList: 최근 30일 창 수집, 페이징 없음. 날짜 필터는 day_report 기준이라 등록 지연(최대 14일 관측)을
  덮도록 30일 (1.3·2.1절, 개정 18)
- 분할 합산(collector-completeness)은 적조를 받지 않는다 — 절단 감시는 processor의 직전 원문 대조 (3.3절, 개정 18)
"""
from __future__ import annotations
import sys
from datetime import timedelta

from common.clock import kst_today
from common.config import load_env_config
from common.http import fetch
from common.queue import Queue, Message
from common.raw_store import save_raw

API_ID = "redtideList"
_WINDOW_DAYS = 30


class BulletinCollectorAdapter:
    api_id = API_ID

    def run(self, queue: Queue) -> None:
        env = load_env_config()
        key = env.get_key(env.nifs_key_bulletin_var)
        today = kst_today()   # 창의 오늘은 KST (3.3절)
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


def _collect_window(url: str, key: str, sdate: str, edate: str) -> dict | None:
    params = {
        "id": "redtideList",
        "key": key,
        "sdate": sdate,
        "edate": edate,
    }
    # 연결 실패·타임아웃도 원문(error 기록)으로 남긴다 — 판정은 processor (2.3절)
    return fetch(url, params, "key", key)



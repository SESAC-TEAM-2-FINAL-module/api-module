"""
조위관측소 최신관측 수집 어댑터 (I-2, 개정 22)
이식: $SRC_IDW/stage2_collect.py _fetch_all_pages() — 개정 22에서 페이지 루프·합치기 제거
요청: min=5, numOfRows=300, reqDate=호출 직전 KST 날짜 1회만 (한 페이지)
자정 경계: KST [00:00, 00:30) 시작이면 어제분 1회 더 (tag: {obsCode}_y) (1.2절, 개정 22)
보충 원문 (_y): 관측·색인 적재까지만 — obs.loaded 미발행, adapter_health 미갱신
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone

from common.config import load_env_config, load_definitions
from common.http import fetch
from common.queue import Queue, Message
from common.raw_store import save_raw
from common.contract_check import QUEUE_CONTRACT

API_ID = "dtRecent"
_NUM_OF_ROWS = 300
_MIDNIGHT_BOUNDARY_MIN = 30   # KST [00:00, 00:30) 이면 자정 경계
_KST = timezone(timedelta(hours=9))


class TideCollectorAdapter:
    api_id = API_ID

    def run(self, queue: Queue) -> None:
        env = load_env_config()
        defs = load_definitions()
        stations: list[str] = defs.get("tide", {}).get("stations", [])
        key = env.get_key(env.dtrecent_key_var)

        # 자정 경계는 실행 시작 시각(KST)으로 한 번만 판별한다 — 관측소별이 아니다 (1.2절)
        started = _now_kst()
        at_midnight = (started.hour == 0 and started.minute < _MIDNIGHT_BOUNDARY_MIN)
        yesterday_req_date = (started - timedelta(days=1)).strftime("%Y%m%d") if at_midnight else None

        for station_code in stations:
            # 정기 원문 — reqDate = 호출 직전 KST 날짜 (23:59:59 시작 → 자정 뒤 호출은 새 날짜, 7.11 T2)
            result = _fetch_station(env.dtrecent_url, station_code, key, _now_kst().strftime("%Y%m%d"))
            # 저장 실패(같은 키 충돌 포함)는 그대로 올린다 — raw.fetched를 내지 않고 실행이 실패로 끝난다 (2.3절)
            raw_id = save_raw(API_ID, station_code, result)
            queue.publish(Message(
                topic="raw.fetched",
                payload={
                    "schema": QUEUE_CONTRACT,
                    "topic": "raw.fetched",
                    "raw_id": raw_id,
                    "api": API_ID,
                    "tag": station_code,
                    "fetched_at_utc": result.get("fetched_at", ""),
                },
            ))

            # 자정 경계: 어제분 보충 원문(tag `_y`) — processor가 관측·색인까지만 적재한다 (1.2절, 개정 22)
            if yesterday_req_date:
                y_tag = f"{station_code}_y"
                y_result = _fetch_station(env.dtrecent_url, station_code, key, yesterday_req_date)
                y_raw_id = save_raw(API_ID, y_tag, y_result)
                queue.publish(Message(
                    topic="raw.fetched",
                    payload={
                        "schema": QUEUE_CONTRACT,
                        "topic": "raw.fetched",
                        "raw_id": y_raw_id,
                        "api": API_ID,
                        "tag": y_tag,
                        "fetched_at_utc": y_result.get("fetched_at", ""),
                    },
                ))


def _now_kst() -> datetime:
    return datetime.now(_KST)


def _fetch_station(url: str, station_code: str, key: str, req_date: str) -> dict | None:
    """
    관측소 단일 페이지 수집 (개정 22 — 페이지 루프·합치기 삭제).
    min=5이면 하루 최대 288건이라 한 페이지에 들어온다.
    연결 실패·타임아웃도 원문(error 기록)으로 반환 — 판정은 processor (2.3절).
    """
    params = {
        "serviceKey": key,
        "type": "json",
        "obsCode": station_code,
        "numOfRows": str(_NUM_OF_ROWS),
        "min": "5",
        "reqDate": req_date,
    }
    return fetch(url, params, "serviceKey", key)

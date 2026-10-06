"""
조위관측소 최신관측 수집 어댑터 (I-2, 개정 22)
이식: $SRC_IDW/stage2_collect.py _fetch_all_pages() — 개정 22에서 페이지 루프·합치기 제거
요청: min=5, numOfRows=300, reqDate=호출 직전 KST 날짜 1회만 (한 페이지)
자정 경계: KST [00:00, 00:30) 시작이면 어제분 1회 더 (tag: {obsCode}_y) (1.2절, 개정 22)
보충 원문 (_y): 관측·색인 적재까지만 — obs.loaded 미발행, adapter_health 미갱신
"""
from __future__ import annotations
import sys
from datetime import datetime, timedelta, timezone

from common.config import load_env_config, load_definitions
from common.http import fetch
from common.queue import Queue, Message
from common.raw_store import save_raw

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

        # 실행 시작 시각(KST) 기준 — 자정 경계는 관측소별이 아니라 실행마다 한 번 판별
        now_kst = datetime.now(_KST)
        req_date = now_kst.strftime("%Y%m%d")
        at_midnight = (now_kst.hour == 0 and now_kst.minute < _MIDNIGHT_BOUNDARY_MIN)
        yesterday_req_date = (now_kst - timedelta(days=1)).strftime("%Y%m%d") if at_midnight else None

        for station_code in stations:
            # 정기 원문 — 호출 직전 KST 날짜 1회
            result = _fetch_station(env.dtrecent_url, station_code, key, req_date)
            if result is None:
                print(f"[tide-collector] 수집 실패: {station_code}", file=sys.stderr)
                continue
            try:
                raw_id = save_raw(API_ID, station_code, result)
            except FileExistsError:
                # 같은 초에 중복 실행 — raw.fetched는 내지 않는다 (2.3절)
                print(f"[tide-collector] 원문 키 충돌(스킵): {station_code}", file=sys.stderr)
                continue
            queue.publish(Message(
                topic="raw.fetched",
                payload={
                    "schema": "queue-v2",
                    "topic": "raw.fetched",
                    "raw_id": raw_id,
                    "api": API_ID,
                    "tag": station_code,
                    "fetched_at_utc": result.get("fetched_at", ""),
                },
            ))

            # 자정 경계: 어제분 보충 원문 (_y) — obs.loaded 발행 없음 (1.2절, 개정 22)
            if yesterday_req_date:
                y_tag = f"{station_code}_y"
                y_result = _fetch_station(env.dtrecent_url, station_code, key, yesterday_req_date)
                if y_result is None:
                    print(f"[tide-collector] 어제분 수집 실패: {y_tag}", file=sys.stderr)
                    continue
                try:
                    save_raw(API_ID, y_tag, y_result)
                    # obs.loaded 발행하지 않는다 — 어제분 보충은 색인·관측 적재까지만
                except FileExistsError:
                    pass  # 이미 저장된 어제분 — 정상 (당일 두 번째 자정 경계 실행 등)


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

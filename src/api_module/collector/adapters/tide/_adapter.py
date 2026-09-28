"""
조위관측소 최신관측 수집 어댑터 (I-2)
이식: $SRC_IDW/stage2_collect.py _fetch_all_pages() — totalCount까지 전 페이지 수령
판정하지 않는다 — totalCount는 페이지 루프 종료 조건(사전 읽기)으로만
"""
from __future__ import annotations
import json
import sys
import time

from common.classifier import parse
from common.config import load_env_config, load_definitions
from common.http import fetch
from common.queue import Queue, Message
from common.raw_store import save_raw

API_ID = "dtRecent"
_NUM_OF_ROWS = 300


class TideCollectorAdapter:
    api_id = API_ID

    def run(self, queue: Queue) -> None:
        env = load_env_config()
        defs = load_definitions()
        stations: list[str] = defs.get("tide", {}).get("stations", [])
        key = env.get_key(env.dtrecent_key_var)

        for station_code in stations:
            result = _collect_station(env.dtrecent_url, station_code, key)
            if result is None:
                print(f"[tide-collector] 수집 실패: {station_code}", file=sys.stderr)
                continue
            raw_id = save_raw(API_ID, station_code, result)
            queue.publish(Message(
                topic="raw.fetched",
                payload={
                    "schema": "queue-v1",
                    "topic": "raw.fetched",
                    "raw_id": raw_id,
                    "api": API_ID,
                    "tag": station_code,
                    "fetched_at_utc": result.get("fetched_at", ""),
                },
            ))


def _collect_station(url: str, station_code: str, key: str) -> dict | None:
    """
    관측소 전 페이지 items 합산.
    단일 페이지: HTTP 응답 원문 그대로 반환.
    다중 페이지: data.go.kr 계열 형식으로 합산 결과 구성 (계획서 반영 후보).
    """
    all_items: list[dict] = []
    total_count: int | None = None
    first_result: dict | None = None
    page = 1

    while True:
        params = {
            "serviceKey": key,
            "type": "json",
            "obsCode": station_code,
            "numOfRows": str(_NUM_OF_ROWS),
            "pageNo": str(page),
            "min": "1",
        }
        result = fetch(url, params, "serviceKey", key)
        if first_result is None:
            first_result = result

        if result.get("error"):
            return None

        # 사전 읽기: totalCount와 items 추출 (판정하지 않는다)
        body_text = result.get("body") or ""
        pr = parse(body_text)

        if pr.total_count is not None and total_count is None:
            total_count = pr.total_count

        all_items.extend(pr.items)

        # 종료 조건: totalCount 기준 또는 마지막 페이지
        if total_count is not None and len(all_items) >= total_count:
            break
        if len(pr.items) < _NUM_OF_ROWS:
            break
        page += 1
        time.sleep(0.15)

    # 단일 페이지: 원문 그대로
    if page == 1:
        return first_result

    # 다중 페이지: 합산 결과를 data.go.kr 계열 JSON 형식으로 구성
    # 계획서 반영 후보 — HTTP 응답 body가 여러 개일 때의 처리
    tc_final = total_count if total_count is not None else len(all_items)
    synthetic_body = json.dumps({
        "response": {
            "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
            "body": {
                "totalCount": tc_final,
                "numOfRows": len(all_items),
                "pageNo": 1,
                "items": {"item": all_items},
            },
        }
    }, ensure_ascii=False)
    return {**first_result, "body": synthetic_body, "_page_count": page}

"""
어장환경 해수면 게시 감시 (I-5)
신규 코드: 검증 코드 없음 (SKILL.md ④)
- 주 1회 올해 창 건수(사전 읽기)를 직전 감시 원문 메타 건수와 비교
  → 다르면 같은 실행에서 해당 연도 전량 호출 (이벤트를 받는 별도 워크로드 없음)
- 사용 금지: $SRC_API/verify_nifs_api.py check_liveness() — 실패 시 작년으로 폴백하는 결함
- 호출 실패를 게시 대기로 삼키지 않는다
"""
from __future__ import annotations
import sys
from datetime import date

from common.classifier import parse
from common.config import load_env_config
from common.http import fetch
from common.queue import Queue, Message
from common.raw_store import save_raw

from collector.main import register

API_ID = "femoSeaList"
API_ID_WATCH = "femoSeaList-watch"


class FisheryWatchAdapter:
    """게시 감시 — collector-fishery-watch 워크로드 (CronJob, 주 1회)."""
    api_id = API_ID_WATCH

    def run(self, queue: Queue) -> None:
        env = load_env_config()
        key = env.get_key(env.nifs_key_fishery_sea_var)
        today = date.today()
        year = today.year
        sdate = f"{year}0101"
        edate = today.strftime("%Y%m%d")

        # 사전 읽기 — 수집 범위 결정 목적, 판정하지 않는다
        watch_result = fetch(
            env.nifs_url,
            {"id": "femoSeaList", "key": key, "sdate": sdate, "edate": edate},
            "key", key,
        )

        if watch_result.get("error"):
            # 호출 실패 — 게시 대기(OK_EMPTY)로 삼키지 않는다
            raw_id = save_raw(API_ID_WATCH, f"watch_{year}", watch_result)
            queue.publish(Message(
                topic="raw.fetched",
                payload={
                    "schema": "queue-v1",
                    "topic": "raw.fetched",
                    "raw_id": raw_id,
                    "api": API_ID_WATCH,
                    "tag": f"watch_{year}",
                    "fetched_at_utc": watch_result.get("fetched_at", ""),
                    "target_year": year,
                    "prev_total_count": None,
                },
            ))
            print(f"[fishery-watch] 호출 실패: {watch_result.get('error')}", file=sys.stderr)
            return

        # 현재 건수 (사전 읽기)
        pr = parse(watch_result.get("body", ""))
        current_count = len(pr.items)

        # 직전 감시 메타 건수 로드 (I-6 이전: DB 접근 불가 → None)
        prev_count = _load_prev_count()

        raw_id = save_raw(API_ID_WATCH, f"watch_{year}", watch_result)
        queue.publish(Message(
            topic="raw.fetched",
            payload={
                "schema": "queue-v1",
                "topic": "raw.fetched",
                "raw_id": raw_id,
                "api": API_ID_WATCH,
                "tag": f"watch_{year}",
                "fetched_at_utc": watch_result.get("fetched_at", ""),
                "target_year": year,
                "total_count": current_count,
                "prev_total_count": prev_count,
            },
        ))

        # 건수 변화 시 전량 수집 (같은 실행에서, 2.1절)
        changed = prev_count is None or current_count != prev_count
        if changed and current_count > 0:
            full_result = fetch(
                env.nifs_url,
                {"id": "femoSeaList", "key": key, "sdate": sdate, "edate": edate},
                "key", key,
            )
            if full_result.get("error"):
                print(f"[fishery-watch] 전량 수집 실패: {year}", file=sys.stderr)
                return
            full_raw_id = save_raw(API_ID, str(year), full_result)
            queue.publish(Message(
                topic="raw.fetched",
                payload={
                    "schema": "queue-v1",
                    "topic": "raw.fetched",
                    "raw_id": full_raw_id,
                    "api": API_ID,
                    "tag": str(year),
                    "fetched_at_utc": full_result.get("fetched_at", ""),
                },
            ))


def _load_prev_count() -> int | None:
    """직전 감시 원문 메타 건수 로드. I-6 이전에는 DB 접근 불가 → None."""
    return None


register(FisheryWatchAdapter())

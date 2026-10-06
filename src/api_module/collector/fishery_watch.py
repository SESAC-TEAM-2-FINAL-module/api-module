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


from common.classifier import parse
from common.clock import kst_today
from common.config import load_env_config
from common.http import fetch
from common.queue import Queue, Message
from common.raw_store import get_raw_body, get_raw_meta, list_raw_keys, save_raw

from collector.main import register

API_ID = "femoSeaList"
API_ID_WATCH = "femoSeaList-watch"
_NORMAL = ("OK", "OK_EMPTY", "NO_DATA")   # 사전 읽기 건수를 믿을 수 있는 응답 — 판정이 아니라 비교 기준 선택


class FisheryWatchAdapter:
    """게시 감시 — collector-fishery-watch 워크로드 (CronJob, 주 1회)."""
    api_id = API_ID_WATCH

    def run(self, queue: Queue) -> None:
        env = load_env_config()
        key = env.get_key(env.nifs_key_fishery_sea_var)
        today = kst_today()   # 올해 창의 오늘은 KST (3.3절)
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
                    "schema": "queue-v2",
                    "topic": "raw.fetched",
                    "raw_id": raw_id,
                    "api": API_ID_WATCH,
                    "tag": f"watch_{year}",
                    "fetched_at_utc": watch_result.get("fetched_at", ""),
                },
            ))
            print(f"[fishery-watch] 호출 실패: {watch_result.get('error')}", file=sys.stderr)
            return

        # 현재 건수 (사전 읽기) — 원문 메타에 남겨 다음 감시가 비교한다 (2.1절)
        pr = parse(watch_result.get("body") or "")
        current_count = len(pr.items)
        if pr.parse_status in _NORMAL:
            watch_result["precheck_count"] = current_count   # 비정상 응답의 0건이 다음 비교 기준이 되지 않게

        # 직전 감시 원문(같은 연도, 정상 응답)의 메타 건수 — 원문 저장소에서 읽는다. 없으면 None → 전량 수집
        prev_count = _load_prev_count(year)

        raw_id = save_raw(API_ID_WATCH, f"watch_{year}", watch_result)
        queue.publish(Message(
            topic="raw.fetched",
            payload={
                "schema": "queue-v2",
                "topic": "raw.fetched",
                "raw_id": raw_id,
                "api": API_ID_WATCH,
                "tag": f"watch_{year}",
                "fetched_at_utc": watch_result.get("fetched_at", ""),
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
                # 실패 원문도 저장·발행한다 — processor가 장애로 센다 (2.3절, 개정 16)
                print(f"[fishery-watch] 전량 수집 실패: {year}", file=sys.stderr)
            full_raw_id = save_raw(API_ID, str(year), full_result)
            queue.publish(Message(
                topic="raw.fetched",
                payload={
                    "schema": "queue-v2",
                    "topic": "raw.fetched",
                    "raw_id": full_raw_id,
                    "api": API_ID,
                    "tag": str(year),
                    "fetched_at_utc": full_result.get("fetched_at", ""),
                },
            ))


def _load_prev_count(year: int) -> int | None:
    """
    직전 감시 원문의 메타 건수 (2.1절 — "직전 감시 원문의 메타 건수와 비교").
    원문 저장소 `raw/femoSeaList-watch/…`에서 tag `watch_{year}`인 원문을 키 순서(epoch_ms, 키)로 거슬러
    호출 실패(error)·건수 없음은 건너뛰고 처음 만나는 건수를 쓴다. 메타에 건수가 없는 옛 원문은 본문을 사전 읽기한다.
    찾지 못하거나 읽기 예외면 None — 호출자는 전량 수집한다(건수 변화를 놓치는 쪽보다 안전)
    """
    tag = f"watch_{year}"
    try:
        keys = [k for k in list_raw_keys(f"raw/{API_ID_WATCH}") if k.endswith(f"_{tag}.json")]
    except Exception:
        return None

    def order(k: str) -> tuple[int, str]:
        head = k.rsplit("/", 1)[-1].split("_", 1)[0]
        return (int(head) if head.isdigit() else -1, k)

    for k in sorted(keys, key=order, reverse=True):
        try:
            meta = get_raw_meta(k)
            if not meta or meta.get("error"):
                continue
            if isinstance(meta.get("precheck_count"), int):
                return meta["precheck_count"]
            body = get_raw_body(k)
            prev = parse(body) if body else None
            if prev is not None and prev.parse_status in _NORMAL:
                return len(prev.items)
        except Exception:
            return None
    return None


register(FisheryWatchAdapter())


if __name__ == "__main__":
    # handoff/k8s/collector-fishery-watch.yaml — `python -m collector.fishery_watch`
    import collector.main as _m
    _m._load_adapters()
    _m.main("fishery-watch")

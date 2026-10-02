"""
어장환경 해수면 femoSeaList 수집 어댑터 (I-5)
참고: $SRC_IDW/src/collector.py::collect_fishery_sea() — 달력 연도 단위 호출
- 달력 연도 단위: sdate=YYYY0101, edate=YYYY1231 (올해는 오늘까지)
- 백필(femoSeaList-backfill): 올해 직전 연도부터 거슬러, 연속 2개 연도 0건이면 정지
- 분할 수집(femoSeaList-completeness): 같은 실행에서 단일 창 + 월 분할, 창 = 어제가 속한 해의 1월 1일 ~ KST 어제 (3.3절)
- 페이징 없음 (pageNo 무시)
"""
from __future__ import annotations
import sys
from datetime import date

from common.classifier import parse
from common.clock import kst_today
from common.config import load_env_config
from common.http import fetch
from common.queue import Queue, Message
from common.raw_store import save_raw
from collector._completeness import CompletenessRun, collect

API_ID = "femoSeaList"
API_ID_BACKFILL = "femoSeaList-backfill"
API_ID_COMPLETENESS = "femoSeaList-completeness"


class FisheryBackfillAdapter:
    """과거 연도 백필 — collector-fishery-backfill 워크로드 (Job, 1회)."""
    api_id = API_ID_BACKFILL

    def run(self, queue: Queue) -> None:
        env = load_env_config()
        key = env.get_key(env.nifs_key_fishery_sea_var)
        today = kst_today()
        consecutive_zero = 0

        for year in range(today.year - 1, 0, -1):
            result = _collect_year(env.nifs_url, key, year, today)
            # 실패 원문도 저장·발행한다 — processor가 장애로 센다 (2.3절, 개정 16)
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
            pr = parse(result.get("body") or "") if not result.get("error") else None
            if pr is None or pr.parse_status not in ("OK", "OK_EMPTY", "NO_DATA"):
                # 호출 실패·비정상 응답을 0건으로 세지 않는다 (4.5절). 다음 연도로 넘어가지도 않는다 — 자동 대체 금지(3.1절)
                status = (result.get("error") or {}).get("type") or (pr.parse_status if pr else "PARSE_FAILURE")
                raise SystemExit(f"[fishery-backfill] {year} 호출 실패({status}) — 백필을 멈춘다. 원문은 보관됨")
            if len(pr.items) == 0:
                consecutive_zero += 1
                print(f"[fishery-backfill] {year}: 0건", file=sys.stderr)
            else:
                consecutive_zero = 0

            if consecutive_zero >= 2:
                print("[fishery-backfill] 연속 2개 연도 0건 — 정지", file=sys.stderr)
                break


class FisheryCompletenessAdapter:
    """분할 합산 수집 — collector-completeness 워크로드 (3.3절). 창 = 어제가 속한 해의 1월 1일 ~ KST 어제"""
    api_id = API_ID_COMPLETENESS
    uses_completeness_run = True

    def run(self, queue: Queue, run: CompletenessRun | None = None) -> None:
        env = load_env_config()
        key = env.get_key(env.nifs_key_fishery_sea_var)
        run = run or CompletenessRun.start()
        start = date(run.end.year, 1, 1)
        collect(api_base=API_ID, api_completeness=API_ID_COMPLETENESS, window=(start, run.end),
                fetch_window=lambda s, e: _collect_window(env.nifs_url, key, s, e), run=run, queue=queue)

def _collect_year(url: str, key: str, year: int, today: date) -> dict | None:
    sdate = f"{year}0101"
    edate = f"{year}1231" if year < today.year else today.strftime("%Y%m%d")
    return _collect_window(url, key, sdate, edate)


def _collect_window(url: str, key: str, sdate: str, edate: str) -> dict | None:
    params = {"id": "femoSeaList", "key": key, "sdate": sdate, "edate": edate}
    # 연결 실패·타임아웃도 원문(error 기록)으로 남긴다 — 판정은 processor (2.3절)
    return fetch(url, params, "key", key)



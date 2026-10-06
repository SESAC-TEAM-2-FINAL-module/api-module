"""
정선해양관측 sooList 수집 어댑터 (I-4)
참고: $SRC_IDW/src/collector.py::collect_line_survey() — 1년 창 1회 호출
- 페이징 없음: pageNo 파라미터를 쓰지 않는다 — 한 번 호출하면 전체가 온다
  (여러 번 호출하면 같은 데이터가 중복된다)
- collector-completeness: 같은 실행에서 단일 창 + 월 분할(창 끝 = KST 어제), 다 받으면 completeness.collected (3.3절)
- 1년 창 = 작년 같은 날(없으면 2/28) ~ 끝 날짜, 양끝 포함 — IDW 검증 코드·기준 데이터와 같다(3.3절)
"""
from __future__ import annotations
import sys
from datetime import date

from common.clock import kst_today, same_day_last_year
from common.config import load_env_config
from common.http import fetch
from common.queue import Queue, Message
from common.raw_store import save_raw
from collector._completeness import CompletenessRun, collect

API_ID = "sooList"
API_ID_COMPLETENESS = "sooList-completeness"


class LineCollectorAdapter:
    api_id = API_ID

    def run(self, queue: Queue) -> None:
        env = load_env_config()
        key = env.get_key(env.nifs_key_line_var)
        start, end = year_window(kst_today())
        sdate, edate = start.strftime("%Y%m%d"), end.strftime("%Y%m%d")
        tag = f"{sdate}_{edate}"

        result = _collect_window(env.nifs_url, key, sdate, edate)
        if result is None:
            print("[line-collector] 수집 실패", file=sys.stderr)
            return

        raw_id = save_raw(API_ID, tag, result)
        queue.publish(Message(
            topic="raw.fetched",
            payload={
                "schema": "queue-v2",
                "topic": "raw.fetched",
                "raw_id": raw_id,
                "api": API_ID,
                "tag": tag,
                "fetched_at_utc": result.get("fetched_at", ""),
            },
        ))


class LineCompletenessAdapter:
    """분할 합산 수집 — collector-completeness 워크로드 (3.3절). 창 = 작년 같은 날 ~ KST 어제"""
    api_id = API_ID_COMPLETENESS
    uses_completeness_run = True

    def run(self, queue: Queue, run: CompletenessRun | None = None) -> None:
        env = load_env_config()
        key = env.get_key(env.nifs_key_line_var)
        run = run or CompletenessRun.start()
        collect(api_base=API_ID, api_completeness=API_ID_COMPLETENESS, window=year_window(run.end),
                fetch_window=lambda s, e: _collect_window(env.nifs_url, key, s, e), run=run, queue=queue)

def year_window(end: date) -> tuple[date, date]:
    """정선 1년 창 — 작년 같은 날(없으면 2월 28일) ~ end, 양끝 포함 (3.3절). 정기·분할 합산이 함께 쓴다"""
    return same_day_last_year(end), end


def _collect_window(url: str, key: str, sdate: str, edate: str) -> dict | None:
    """sooList 1회 호출 — 페이징 없음, pageNo 사용 금지"""
    params = {
        "id": "sooList",
        "key": key,
        "sdate": sdate,
        "edate": edate,
    }
    # 연결 실패·타임아웃도 원문(error 기록)으로 남긴다 — 판정은 processor (2.3절)
    return fetch(url, params, "key", key)



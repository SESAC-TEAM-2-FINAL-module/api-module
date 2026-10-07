"""
수집 진입점 (2.1절, 6.1절)
판정하지 않는다 — 원문과 요청 메타데이터만 남기고 raw.fetched 발행
어댑터 등록 방식: I-2~I-5가 register()로 등록 (키 = api_id)
워크로드 이름(인계 매니페스트 handoff/k8s/collector-*.yaml의 명령) → 그 워크로드가 부르는 어댑터 api_id
"""
from __future__ import annotations
import sys
import time
from typing import Protocol

from common.queue import Queue, Message
from common.metrics import collector_calls_total, collector_retry_total, collector_duration_seconds


class CollectorAdapter(Protocol):
    api_id: str

    def run(self, queue: Queue) -> None: ...


_REGISTRY: dict[str, CollectorAdapter] = {}

# 워크로드 → 어댑터 api_id (2.1절 표). `collector-` 접두를 붙인 이름(k8s 리소스 이름)도 받는다
WORKLOADS: dict[str, tuple[str, ...]] = {
    "tide": ("dtRecent",),
    "bulletin": ("redtideList",),
    "line": ("sooList",),
    "fishery-watch": ("femoSeaList-watch",),
    "fishery-backfill": ("femoSeaList-backfill",),
    # 적조는 분할 합산에서 뺐다 — 직전 원문 대조로 본다 (3.3절, 개정 18)
    "completeness": ("sooList-completeness", "femoSeaList-completeness"),
}


def register(adapter: CollectorAdapter) -> None:
    _REGISTRY[adapter.api_id] = adapter


def resolve(workload: str) -> list[CollectorAdapter]:
    """워크로드 이름(또는 api_id) → 등록된 어댑터. 하나라도 없으면 멈춘다"""
    name = workload.removeprefix("collector-")
    api_ids = WORKLOADS.get(name, (name,))
    missing = [a for a in api_ids if a not in _REGISTRY]
    if missing:
        raise SystemExit(f"[collector] 등록된 어댑터 없음: {workload} → {missing}")
    return [_REGISTRY[a] for a in api_ids]


def main(workload: str, queue: Queue) -> None:
    """큐는 부르는 쪽이 넘긴다 — 운영은 `__main__`의 open_queue, 테스트·시험 실행기는 인메모리 (2.2절, 개정 22)"""
    adapters = resolve(workload)
    run = None
    if any(getattr(a, "uses_completeness_run", False) for a in adapters):
        from collector._completeness import CompletenessRun
        run = CompletenessRun.start()          # 실행 키·창 끝(KST 어제)을 한 번 정해 두 원천이 함께 쓴다 (3.3절)
    for adapter in adapters:
        t0 = time.monotonic()
        if getattr(adapter, "uses_completeness_run", False):
            adapter.run(queue, run=run)
        else:
            adapter.run(queue)
        collector_duration_seconds.labels(api=adapter.api_id).observe(time.monotonic() - t0)


def _load_adapters() -> None:
    """어댑터 패키지를 import해 register()가 돌게 한다"""
    import collector.adapters.tide  # noqa: F401
    import collector.adapters.bulletin  # noqa: F401
    import collector.adapters.line  # noqa: F401
    import collector.adapters.fishery  # noqa: F401
    import collector.fishery_watch  # noqa: F401


if __name__ == "__main__":
    # `python -m collector.main`으로 돌면 이 파일은 __main__ 모듈이다. 어댑터는 collector.main에
    # register()하므로 실행도 같은 모듈(collector.main)의 함수로 한다 — 레지스트리가 둘로 나뉘지 않게
    import argparse
    import collector.main as _m
    p = argparse.ArgumentParser()
    p.add_argument("workload", help=f"워크로드: {', '.join(WORKLOADS)} (또는 api_id)")
    args = p.parse_args()
    _m._load_adapters()
    _m.resolve(args.workload)                    # 워크로드 이름 확인 먼저 — 연결 전에 멈출 수 있게
    from common.queue import open_queue
    from common.raw_store import open_raw_store
    open_raw_store("collector")                  # RAW_STORE_DSN 없으면 멈춤 — 로컬 대체 없음 (2.3절)
    _q = open_queue("collector")                 # QUEUE_DSN 없으면 멈춤 — 인메모리 대체 없음 (2.2절)
    try:
        _m.main(args.workload, _q)
    finally:
        _q.close()

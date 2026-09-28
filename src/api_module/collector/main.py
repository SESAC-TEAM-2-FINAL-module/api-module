"""
수집 진입점 (2.1절, 6.1절)
판정하지 않는다 — 원문과 요청 메타데이터만 남기고 raw.fetched 발행
어댑터 등록 방식: I-2~I-5가 register()로 등록
"""
from __future__ import annotations
import sys
import time
from typing import Protocol

from common.queue import Queue, Message, MemoryQueue
from common.metrics import collector_calls_total, collector_retry_total, collector_duration_seconds


class CollectorAdapter(Protocol):
    api_id: str

    def run(self, queue: Queue) -> None: ...


_REGISTRY: dict[str, CollectorAdapter] = {}


def register(adapter: CollectorAdapter) -> None:
    _REGISTRY[adapter.api_id] = adapter


def main(workload: str, queue: Queue | None = None) -> None:
    if queue is None:
        queue = MemoryQueue()

    adapter = _REGISTRY.get(workload)
    if adapter is None:
        print(f"[collector] 등록된 어댑터 없음: {workload}", file=sys.stderr)
        sys.exit(1)

    t0 = time.monotonic()
    adapter.run(queue)
    collector_duration_seconds.labels(api=workload).observe(time.monotonic() - t0)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("workload")
    args = p.parse_args()
    main(args.workload)

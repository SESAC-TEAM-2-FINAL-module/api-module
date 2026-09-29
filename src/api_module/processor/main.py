"""
가공 진입점 (2.1절, 6.1절)
process: raw.fetched 소비 → classifier → 어댑터 해석·정규화 → completeness → quality → 적재 → obs.loaded
reprocess: 원문 ID 범위 재처리 (파서 수정 후). 재처리마다 ingest_runs 행 추가, 같은 (raw_id, parser_version)은 중복 추가 안 함
"""
from __future__ import annotations
import sys
from typing import Protocol

from common.classifier import ParsedResponse, parse
from common.queue import Queue, Message, MemoryQueue
from common.raw_store import get_raw_body, get_raw_meta
from common.metrics import processor_parse_failure_total
from processor.completeness import check_completeness
from processor.quality import apply_quality

PARSER_VERSION = "v0.1"


class ProcessorAdapter(Protocol):
    api_id: str

    def interpret(self, pr: ParsedResponse, raw_meta: dict) -> list[dict]: ...
    def normalize(self, rows: list[dict]) -> list[dict]: ...


_REGISTRY: dict[str, ProcessorAdapter] = {}


def register(adapter: ProcessorAdapter) -> None:
    _REGISTRY[adapter.api_id] = adapter


def _process_one(raw_id: str, api: str, queue: Queue) -> None:
    body = get_raw_body(raw_id)
    if body is None:
        print(f"[processor] 원문 없음: {raw_id}", file=sys.stderr)
        return

    meta = get_raw_meta(raw_id) or {}
    pr = parse(body)

    if pr.parse_status == "PARSE_FAILURE":
        processor_parse_failure_total.labels(api=api, parser_version=PARSER_VERSION).inc()

    adapter = _REGISTRY.get(api)
    if adapter is None:
        print(f"[processor] 등록된 어댑터 없음: {api}", file=sys.stderr)
        return

    rows = adapter.interpret(pr, meta)
    rows = adapter.normalize(rows)
    completeness = check_completeness(pr, rows, api, actual_items=len(pr.items))
    rows = apply_quality(rows, api)

    # 적재: DB 접근 계층 인터페이스 (I-6에서 구현)
    # _repository.load(raw_id, PARSER_VERSION, rows, completeness, pr)

    # adapter_health 갱신: DB 접근 계층 인터페이스 (I-6에서 구현)
    # _repository.update_adapter_health(api, pr.parse_status)

    ok_rows = [r for r in rows if r.get("quality_flag") != "MISSING"]

    queue.publish(Message(
        topic="obs.loaded",
        payload={
            "schema": "queue-v1",
            "load_id": f"{raw_id}::{PARSER_VERSION}",
            "api": api,
            "source": api,
            "station_ids": list({r["station_id"] for r in ok_rows if r.get("station_id")}),
            "observed_from_utc": min((r.get("observed_at_utc", "") for r in ok_rows), default=""),
            "observed_to_utc": max((r.get("observed_at_utc", "") for r in ok_rows), default=""),
            "row_count": len(ok_rows),
        },
    ))


def process(raw_id: str, api: str, queue: Queue | None = None) -> None:
    if queue is None:
        queue = MemoryQueue()
    _process_one(raw_id, api, queue)


def reprocess(raw_ids: list[str], api: str, queue: Queue | None = None) -> None:
    if queue is None:
        queue = MemoryQueue()
    for raw_id in raw_ids:
        _process_one(raw_id, api, queue)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd")
    p1 = sub.add_parser("process")
    p1.add_argument("raw_id")
    p1.add_argument("api")
    p2 = sub.add_parser("reprocess")
    p2.add_argument("api")
    p2.add_argument("raw_ids", nargs="+")
    args = p.parse_args()
    if args.cmd == "process":
        process(args.raw_id, args.api)
    elif args.cmd == "reprocess":
        reprocess(args.raw_ids, args.api)

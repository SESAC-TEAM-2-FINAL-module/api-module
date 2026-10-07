"""
가공 진입점 (2.1절, 6.1절)
process: raw.fetched 소비 → classifier → 어댑터 해석·정규화 → completeness → quality → 적재(_load, 한 트랜잭션) → obs.loaded
reprocess: 원문 ID(raw_index.id) 범위 재처리 (파서 수정 후, `--raw-id-from`·`--raw-id-to`). 재처리마다 ingest_runs 행 추가, 같은 (raw_id, parser_version)은 중복 추가 안 함
"""
from __future__ import annotations
import sys
from datetime import datetime, timezone
from typing import Protocol

from common.classifier import ParsedResponse, parse
from common.config import load_definitions, load_operational, operational_hash
from common.contract_check import QUEUE_CONTRACT, accept_message
from common.queue import Queue, Message
from common.sources import source_of
from common.raw_store import get_raw_body, get_raw_meta
from common.metrics import (processor_parse_failure_total, operational_config_info,
                            bulletin_window_missing_total, bulletin_window_check_skipped_total)
from processor.completeness import check_completeness
from processor.completeness._checker import requested_window
from processor.quality import apply_quality
from processor._load import load, _storage_tag

PARSER_VERSION = "v0.1"


class ProcessorAdapter(Protocol):
    api_id: str

    def interpret(self, pr: ParsedResponse, raw_meta: dict) -> list[dict]: ...
    def normalize(self, rows: list[dict]) -> list[dict]: ...


_REGISTRY: dict[str, ProcessorAdapter] = {}

# 기동 시 한 번 읽는 설정 (2.0.6절) — startup()이 채운다
_CONFIG: dict = {}


# 등록된 어댑터가 없는 변형 api_id → 같은 해석을 쓰는 어댑터 (2.1절 — 백필은 과거 연도 같은 원문)
_ADAPTER_ALIAS = {"femoSeaList-backfill": "femoSeaList"}

# 받지만 아직 처리 경로가 없는 api_id — 설계 대기를 명시한다(이름 대조 검사가 이 목록을 본다). 개정 17 이후 비어 있다
PENDING_APIS: frozenset[str] = frozenset()


def register(adapter: ProcessorAdapter) -> None:
    _REGISTRY[adapter.api_id] = adapter


def schema_checks(repo) -> None:
    """읽기 전용 스키마 검사 — completeness_checks 포함 (5.3절). startup()과 시험 실행기 _preflight가 함께 부른다."""
    repo.check_schema(include=("completeness_checks",))


def startup(
    definitions: dict | None = None,
    operational: dict | None = None,
    repo=None,
) -> None:
    """
    기동 시 검사 (2.0.3·2.0.6절) — 판정 정의와 운영 조정을 한 번 읽어 어댑터에 넘기고,
    DB 테이블이 정의와 같은지 본다. 어느 쪽이든 없거나 다르면 멈춘다 (기본값으로 대체하지 않는다, 스스로 만들지 않는다)
    repo를 주지 않으면 DATABASE_URL로 SqlRepository를 만든다 (값은 출력하지 않는다)
    """
    if definitions is None:
        definitions = load_definitions()
    if operational is None:
        operational = load_operational()
    if repo is None:
        repo = _repository_from_env()
    schema_checks(repo)   # 분할 합산 결과 표는 processor만 요구 (5.3절)

    for adapter in _REGISTRY.values():
        configure = getattr(adapter, "configure", None)
        if configure is not None:
            configure(definitions, operational)

    h = operational_hash(operational)
    operational_config_info.labels(image="processor", hash=h, schema=operational.get("schema", "")).set(1)
    repo.insert_ops_events([{
        "event_type": "OPERATIONAL_CONFIG_LOADED", "api": None, "occurred_at_utc": _now_utc(),
        "detail": {"image": "processor", "hash": h, "schema": operational.get("schema")},
    }])
    _CONFIG.clear()
    _CONFIG.update(definitions=definitions, operational=operational, repo=repo)


def _repository_from_env():
    from sqlalchemy import create_engine
    from common.config import database_url
    from common.repository import SqlRepository
    return SqlRepository(create_engine(database_url()))


def _now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def _is_supplement(raw_id: str, api: str) -> bool:
    """조위 보충 원문(어제분) 판별 — 조위 원문의 tag가 `_y`로 끝나면 True (1.2절, 개정 22).
    tag는 storage_key 파일명 {epoch_ms}_{tag}.json에서 추출. 다른 원천의 tag는 보지 않는다"""
    tag = _storage_tag(raw_id)
    return api == "dtRecent" and tag is not None and tag.endswith("_y")


def _process_one(raw_id: str, api: str, queue: Queue) -> None:
    """raw_id = 원문 객체 키(raw_index.storage_key, 결정 D1)"""
    if not _CONFIG:
        raise RuntimeError("processor.startup() 전에 처리 호출 — 설정 미주입")

    meta = get_raw_meta(raw_id)
    if meta is None:
        raise RuntimeError(f"[processor] 원문 없음: {raw_id}")
    body = get_raw_body(raw_id)

    adapter = _REGISTRY.get(api) or _REGISTRY.get(_ADAPTER_ALIAS.get(api, ""))
    if adapter is None:
        if api in PENDING_APIS:
            print(f"[processor] 처리 경로 설계 대기 — 원문은 보관됨: {raw_id}", file=sys.stderr)
        else:
            print(f"[processor] 등록된 어댑터 없음: {api}", file=sys.stderr)
        return

    # 호출 실패 원문(body 없음, error 기록)도 처리한다 — adapter_health에 장애로 남아야 한다 (4.9절)
    if body is None:
        pr = ParsedResponse(parse_status="PARSE_FAILURE")
        rows: list[dict] = []
        completeness = None
        untimed = 0
    else:
        pr = parse(body)
        if pr.parse_status == "PARSE_FAILURE":
            processor_parse_failure_total.labels(api=api, parser_version=PARSER_VERSION).inc()
        raw_meta = {**meta, "raw_id": raw_id, "fetched_at_utc": meta.get("fetched_at")}
        raw_meta.update(_watch_meta(api, raw_id))
        rows = adapter.interpret(pr, raw_meta)
        # 관측 시각을 읽지 못한 행은 키를 만들 수 없다 — 추정하지 않고 건너뛰고 적재 때 기록한다 (5.2절)
        timed = [r for r in rows if not ("observed_at_utc" in r and r["observed_at_utc"] is None)]
        untimed, rows = len(rows) - len(timed), timed
        rows = adapter.normalize(rows)
        sdate, edate = requested_window(meta)
        completeness = check_completeness(pr, rows, api, actual_items=len(pr.items),
                                          request_window=(sdate, edate) if sdate and edate else None)
        rows = apply_quality(rows, api, _CONFIG["definitions"], operational=_CONFIG["operational"])

    # 보충 원문(_y): 관측·색인 적재까지만 — obs.loaded 미발행, adapter_health 미갱신 (1.2절, 개정 22)
    supplement = _is_supplement(raw_id, api)

    # 적재 — 한 트랜잭션. 예외가 나면 알림을 내지 않는다 (I-12)
    result = load(
        _CONFIG["repo"],
        storage_key=raw_id, api=api, meta=meta, body=body, pr=pr, rows=rows,
        completeness=completeness, adapter=adapter, parser_version=PARSER_VERSION, now_utc=_now_utc(),
        untimed_rows=untimed, skip_health=supplement,
    )
    # 적조 직전 원문 대조 지표 — 커밋 뒤 (3.3절, 개정 18)
    if result.window_missing:
        bulletin_window_missing_total.inc(result.window_missing)
    if result.window_skip:
        bulletin_window_check_skipped_total.labels(reason=result.window_skip).inc()

    if supplement:
        # 보충 원문은 obs.loaded를 내지 않는다 (1.2절, 개정 22)
        return result

    ok_rows = [r for r in rows if r.get("quality_flag") != "MISSING"]

    queue.publish(Message(
        topic="obs.loaded",
        payload={
            "schema": QUEUE_CONTRACT,
            "topic": "obs.loaded",
            "load_id": f"{raw_id}::{PARSER_VERSION}",
            "api": api,
            "source": source_of(api) or api,  # 수집 원천 — 축이 아니다 (2.2절)
            "station_ids": sorted({r["station_id"] for r in ok_rows if r.get("station_id")}),
            "observed_from_utc": min((r.get("observed_at_utc", "") for r in ok_rows), default=""),
            "observed_to_utc": max((r.get("observed_at_utc", "") for r in ok_rows), default=""),
            "row_count": len(ok_rows),
        },
    ))
    return result


def _watch_meta(api: str, raw_id: str) -> dict:
    """게시 감시 원문은 대상 연도를 tag(`watch_{year}`)로 갖는다 — 직전 건수는 적재 시 DB에서 (4.5절)"""
    if api != "femoSeaList-watch":
        return {}
    tag = _storage_tag(raw_id) or ""
    year = tag.split("_", 1)[1] if tag.startswith("watch_") else None
    return {"target_year": int(year) if year and year.isdigit() else None}


def process(raw_id: str, api: str, queue: Queue) -> None:
    """원문 한 건 처리 — 큐는 부르는 쪽이 넘긴다(운영은 open_queue, 테스트는 MemoryQueue — 2.2절, 개정 22)"""
    _process_one(raw_id, api, queue)


def handle_raw_fetched(payload: dict, queue: Queue) -> None:
    """raw.fetched 컨슈머 — 계약 버전이 다르면 처리하지 않는다 (2.2절)"""
    if not _CONFIG:
        raise RuntimeError("processor.startup() 전에 처리 호출 — 설정 미주입")
    if not accept_message(payload, "raw.fetched", _CONFIG["repo"]):
        return
    _process_one(payload["raw_id"], payload["api"], queue)


def reprocess(raw_ids: list[str], api: str, queue: Queue) -> None:
    for raw_id in raw_ids:
        _process_one(raw_id, api, queue)


def reprocess_range(id_from: int, id_to: int, queue: Queue) -> int:
    """
    원문 ID 범위 재처리 (2.1절, 개정 15) — 원문 ID = raw_index.id(5.3절, 결정 D1), 양끝 포함.
    색인 행의 api·storage_key로 다시 처리한다. 반환: 처리한 원문 수
    """
    if not _CONFIG:
        raise RuntimeError("processor.startup() 전에 처리 호출 — 설정 미주입")
    if id_from > id_to:
        raise SystemExit(f"재처리 범위가 거꾸로다: {id_from} > {id_to}")
    rows = _CONFIG["repo"].get_raw_index_range(id_from, id_to)
    for r in rows:
        _process_one(r["storage_key"], r["api"], queue)
    return len(rows)


def completeness_check(payload: dict, now_utc: datetime | None = None):
    """`completeness.collected` 한 건 판정 (3.3절, 개정 17) — 검사기 워크로드 `completeness-check`"""
    if not _CONFIG:
        raise RuntimeError("processor.startup() 전에 처리 호출 — 설정 미주입")
    from processor.completeness import run_completeness_check
    return run_completeness_check(payload, _CONFIG["repo"], now_utc)


def seed_check(repo, defs: dict | None = None) -> list[str]:
    """해역 시드 대조 — startup() 없이 DB 시드를 이미지 시드 파일과 비교 (4.3절, 개정 19).
    repo는 check_schema()가 이미 통과한 것을 전제한다.
    반환: 차이 줄 목록 (빈 목록 = 통과)"""
    if defs is None:
        defs = load_definitions()
    from common.seeds import compare_seed_tables
    return compare_seed_tables(repo, defs)


def _load_adapters() -> None:
    """어댑터 패키지를 import해 register()가 돌게 한다"""
    import processor.adapters.tide  # noqa: F401
    import processor.adapters.bulletin  # noqa: F401
    import processor.adapters.line  # noqa: F401
    import processor.adapters.fishery  # noqa: F401


if __name__ == "__main__":
    # `python -m processor.main`으로 돌면 이 파일은 __main__ 모듈이다. 어댑터는 processor.main에
    # register()하므로, 실행도 같은 모듈(processor.main)의 함수로 한다 — 레지스트리가 둘로 나뉘지 않게
    import argparse
    import processor.main as _m
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd")
    p1 = sub.add_parser("process")
    p1.add_argument("raw_id")
    p1.add_argument("api")
    p2 = sub.add_parser("reprocess")     # handoff/k8s/processor.yaml — 원문 ID(raw_index.id) 범위
    p2.add_argument("--raw-id-from", type=int, required=True)
    p2.add_argument("--raw-id-to", type=int, required=True)
    sub.add_parser("completeness-check")   # 분할 합산 검사기 — completeness.collected 컨슈머 (3.3절, KEDA 밖 1대)
    sub.add_parser("seed-check")           # 해역 시드 점검 — startup() 없이 DB 대조 (4.3절, 개정 19)
    args = p.parse_args()
    if args.cmd == "seed-check":
        # startup()·_load_adapters() 없이 돈다 — 운영 조정 읽기 없음 (4.3절, 개정 19)
        from sqlalchemy import create_engine as _ce
        from common.config import database_url as _dbu
        from common.repository.sql import SqlRepository as _SR
        _repo = _SR(_ce(_dbu()))
        _repo.check_schema()   # seed-check도 스키마 검사 (4.3절)
        _diffs = _m.seed_check(_repo)
        for _line in _diffs:
            print(_line)
        print(f"[seed-check] 차이 {len(_diffs)}건")
        sys.exit(1 if _diffs else 0)
    _m._load_adapters()
    # 읽기 전용 검사(판정 정의·운영 조정 스키마·DB 스키마) → 원문 저장소·큐 연결 → 쓰기가 있는 startup() (개정 22)
    from common.config import load_definitions as _ld, load_operational as _lo
    from common.queue import open_queue
    from common.raw_store import open_raw_store
    _defs, _op, _repo = _ld(), _lo(), _m._repository_from_env()
    _m.schema_checks(_repo)
    open_raw_store("processor")
    _workload = "completeness-check" if args.cmd == "completeness-check" else "processor"
    _q = open_queue(_workload, _repo)
    try:
        _m.startup(_defs, _op, _repo)
        if args.cmd == "process":
            _m.process(args.raw_id, args.api, _q)
        elif args.cmd == "reprocess":
            n = _m.reprocess_range(args.raw_id_from, args.raw_id_to, _q)
            print(f"[processor] 재처리 {n}건 (raw_index.id {args.raw_id_from}~{args.raw_id_to})", file=sys.stderr)
        elif args.cmd == "completeness-check":
            _q.subscribe("completeness.collected", lambda msg: _m.completeness_check(msg.payload))
            _q.run()
        else:
            # 명령 없음 = raw.fetched 컨슈머 (Deployment) — 메시지를 기다리며 계속 돈다 (점검 C17)
            _q.subscribe("raw.fetched", lambda msg: _m.handle_raw_fetched(msg.payload, _q))
            _q.run()
    finally:
        _q.close()

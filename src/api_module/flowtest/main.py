"""
시험 실행기 flowtest — collector → processor → interpolation → grading → evaluation
한 프로세스 · 인메모리 큐 (계획서 2.1.1절, 개정 21)

모드
  --mode collect (기본): 실제 수집 API 호출 → 파이프라인
  --mode replay:          원문 저장소 정기 경로 원문을 raw.fetched 재발행
실행
  --run once (기본): 워크로드 한 번 수집 → interpolation-error 1회 → evaluation-sweep 1회 → 요약 → 종료
  --run loop:         주기 반복 (--*-interval 인수 또는 FT_*_INTERVAL_SEC 환경 변수)
                      loop 모드에서는 모든 주기 인수 또는 환경 변수를 지정해야 한다
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

log = logging.getLogger("flowtest")


# ─ 통계 ───────────────────────────────────────────────────────────────────────

@dataclass
class _Stats:
    failures: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    runs: int = 0


# ─ 핸들러 바인딩 (FT1 함수 동일성) ──────────────────────────────────────────

def _bind_handler(fn, *args, **kwargs):
    """단계 함수 fn을 msg 하나만 받는 핸들러로 묶는다.
    _stage_fn 속성에 fn 을 노출 — FT1 ① `is` 연산자 검사에 쓴다."""
    def _bound(msg):
        fn(msg.payload, *args, **kwargs)
    _bound._stage_fn = fn
    return _bound


# ─ 예외 포착 래퍼 ─────────────────────────────────────────────────────────────

def _wrap(stage: str, topic: str, handler, stats: _Stats):
    """예외를 잡아 기록하고 다음 메시지를 계속 처리한다 (2.1.1절).
    _stage_fn 을 핸들러에서 전파 — FT1 ① 함수 동일성 검사 지원."""
    def _wrapped(msg):
        try:
            handler(msg)
        except Exception as exc:
            stats.failures[stage] += 1
            # H5: 예외 메시지에 URL·키가 실릴 수 있다 — 종류 이름만 기록 (2.3절)
            log.error("[%s] %s 처리 실패: %s", stage, topic, type(exc).__name__)
    _wrapped._stage_fn = getattr(handler, "_stage_fn", handler)
    return _wrapped


# ─ 실행 전 점검 (읽기 전용) ──────────────────────────────────────────────────

def _preflight(repo, defs: dict, collect_mode: bool) -> dict:
    """
    읽기 전용 검사 전부 — 모두 통과한 뒤에만 processor.startup()을 부른다 (2.1.1절).
    순서: 운영 연결 변수 부재 확인 → 운영 조정 스키마 → 단계별 기동 시 검사 → seed-check → farm_sites → (수집 모드) 환경 변수 존재.
    반환: 검사에서 읽은 operational dict (쓰기 기동 절차에서 재사용).
    """
    # QUEUE_DSN·RAW_STORE_DSN이 있으면 운영 연결 위험 — 멈춘다 (2.1.1절, 개정 22)
    for _var in ("QUEUE_DSN", "RAW_STORE_DSN"):
        if os.environ.get(_var):
            raise SystemExit(
                f"실행 전 점검 실패: {_var} 가 설정돼 있습니다 — "
                f"flowtest는 인메모리·로컬 구현만 씁니다 (2.1.1절)"
            )

    import interpolation.main as ip
    import grading.main as gr
    import processor.main as pm
    import evaluation.main as ev
    from common.config import load_operational

    # 1. 운영 조정 스키마 — load_operational이 내부에서 검사, 실패하면 SystemExit
    log.info("[preflight] 운영 조정 스키마 검사")
    operational = load_operational()

    # 2. 단계별 테이블·컬럼·시드·정의 전제 검사 (읽기 전용)
    # M1: 추출된 함수를 직접 호출 — 복제 아님 (FT1 ② 점검 콜 집합 일치)
    log.info("[preflight] processor 스키마 검사")
    pm.schema_checks(repo)

    log.info("[preflight] interpolation 기동 시 검사")
    ip.startup_checks(repo)

    # grading: 테이블·컬럼, areas 빈 시드, 위험도 지수 파라미터 전제
    log.info("[preflight] grading 기동 시 검사")
    gr.startup_checks(repo, defs)

    # evaluation: 테이블·컬럼, areas + axis_coverage 빈 시드
    log.info("[preflight] evaluation 기동 시 검사")
    ev.startup_checks(repo)

    # 3. seed-check — DB 시드 vs 이미지 시드 파일 대조
    log.info("[preflight] seed-check")
    diffs = pm.seed_check(repo, defs)
    if diffs:
        lines = "\n".join(diffs)
        raise SystemExit(
            f"실행 전 점검 실패: seed-check 차이 {len(diffs)}건\n{lines}"
        )

    # 4. farm_sites 표·열·활성 1건
    log.info("[preflight] farm_sites 점검")
    _check_farm_sites(repo._engine)

    # 5. 수집 모드 — 환경 변수 이름만 확인 (값은 출력하지 않는다)
    if collect_mode:
        log.info("[preflight] 수집 환경 변수 존재 확인")
        _check_collect_env()

    return operational


def _check_farm_sites(engine) -> None:
    """farm_sites 표·열(contracts/inputs/farm_sites.md) + 활성 1건 이상 (2.1.1절)."""
    from sqlalchemy import text, inspect as sa_inspect

    required_cols = {"farm_id", "lat", "lng", "active", "updated_at_utc"}
    try:
        insp = sa_inspect(engine)
        if "farm_sites" not in insp.get_table_names():
            raise SystemExit(
                "실행 전 점검 실패: farm_sites 표 없음 — contracts/inputs/farm_sites.md"
            )
        existing = {c["name"] for c in insp.get_columns("farm_sites")}
        missing = required_cols - existing
        if missing:
            raise SystemExit(
                f"실행 전 점검 실패: farm_sites 열 없음 — {sorted(missing)}"
            )
        with engine.connect() as conn:
            n = conn.execute(
                text("SELECT COUNT(*) FROM farm_sites WHERE active = TRUE")
            ).scalar()
        if not n:
            raise SystemExit(
                "실행 전 점검 실패: farm_sites 활성 행(active=TRUE) 없음 — 추정 불가"
            )
    except SystemExit:
        raise
    except Exception as exc:
        raise SystemExit(
            f"실행 전 점검 실패: farm_sites 조회 오류 — {type(exc).__name__}"
        ) from exc


def _check_collect_env() -> None:
    """수집 원천 키·요청주소 변수 존재만 확인 — 값은 출력하지 않는다 (2.1.1절)."""
    required = [
        "DTRECENT_URL", "DTRECENT_KEY",
        "NIFS_URL", "NIFS_KEY_BULLETIN", "NIFS_KEY_LINE", "NIFS_KEY_FISHERY_SEA",
    ]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        raise SystemExit(
            f"실행 전 점검 실패: 수집 환경 변수 없음 — {missing}"
        )


# ─ 파이프라인 설정 ────────────────────────────────────────────────────────────

def _setup_pipeline(repo, defs: dict, operational: dict, q, stats: _Stats) -> None:
    """
    인메모리 큐 구독 설정 → 쓰기 기동 절차 (2.2절, 2.1.1절).
    구독: raw.fetched → processor
          obs.loaded  → interpolation(조위만 — 거름은 핸들러가), grading
          interp.done → grading
          grade.done  → evaluation
    _bind_handler 로 stage 함수를 묶어 _stage_fn 속성을 보존 — FT1 ① 검사 지원.
    """
    import processor.main as pm
    import interpolation.main as ip
    import grading.main as gr
    import evaluation.main as ev

    q.subscribe("raw.fetched", _wrap(
        "processor", "raw.fetched",
        _bind_handler(pm.handle_raw_fetched, q),
        stats,
    ))
    q.subscribe("obs.loaded", _wrap(
        "interpolation", "obs.loaded",
        _bind_handler(ip.handle_obs_loaded, repo, q, defs),
        stats,
    ))
    q.subscribe("obs.loaded", _wrap(
        "grading", "obs.loaded",
        _bind_handler(gr.handle_obs_loaded, repo, q, defs),
        stats,
    ))
    q.subscribe("interp.done", _wrap(
        "grading", "interp.done",
        _bind_handler(gr.handle_interp_done, repo, q, defs),
        stats,
    ))
    q.subscribe("grade.done", _wrap(
        "evaluation", "grade.done",
        _bind_handler(ev.handle_grade_done, repo, q, operational),
        stats,
    ))

    # 쓰기 기동 절차 — 모든 읽기 전용 점검 통과 후 (2.1.1절)
    pm._load_adapters()
    pm.startup(definitions=defs, operational=operational, repo=repo)


# ─ 수집 실행 ──────────────────────────────────────────────────────────────────

def _do_collect(q, stats: _Stats) -> None:
    """4개 워크로드 한 번씩 수집."""
    import collector.main as cm
    cm._load_adapters()
    for workload in ("tide", "bulletin", "line", "fishery-watch"):
        try:
            cm.main(workload, q)
        except Exception as exc:
            stats.failures["collector"] += 1
            # H5: 예외 메시지에 URL·키가 실릴 수 있다 — 종류 이름만 기록 (2.3절)
            log.error("[collector] %s 실패: %s", workload, type(exc).__name__)


# ─ 재생 실행 ──────────────────────────────────────────────────────────────────

def _do_replay(api: str, date_prefix: str, q, stats: _Stats) -> None:
    """
    원문 저장소 정기 경로 원문을 epoch_ms 순으로 raw.fetched 재발행 (2.1.1절).
    분할 합산 원문(tag: cmp_*)은 건너뛴다 — raw.fetched 대상 아님 (3.3절).
    api: 예) dtRecent  date_prefix: 예) 2026/09/20
    """
    from common.raw_store import list_raw_keys
    from common.queue import Message
    from common.contract_check import QUEUE_CONTRACT

    prefix = f"raw/{api}/{date_prefix}"
    keys = sorted(list_raw_keys(prefix))
    log.info("[replay] %s: %d개 원문 발행", prefix, len(keys))
    for key in keys:
        try:
            fname = key.rsplit("/", 1)[-1]
            tag = fname.split("_", 1)[1].removesuffix(".json") if "_" in fname else ""
            if tag.startswith("cmp_"):
                continue
            epoch_part = fname.split("_", 1)[0]
            fetched_at = datetime.fromtimestamp(
                int(epoch_part) / 1000, tz=timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%S")
            q.publish(Message(
                topic="raw.fetched",
                payload={
                    "schema": QUEUE_CONTRACT,
                    "topic": "raw.fetched",
                    "raw_id": key,
                    "api": api,
                    "tag": tag,
                    "fetched_at_utc": fetched_at,
                },
            ))
        except Exception as exc:
            stats.failures["replay"] += 1
            # H5: 예외 메시지에 URL·키가 실릴 수 있다 — 종류 이름만 기록 (2.3절)
            log.error("[replay] %s 발행 실패: %s", key, type(exc).__name__)


# ─ 후처리 워크로드 ────────────────────────────────────────────────────────────

def _do_interpolation_error(repo, defs: dict, stats: _Stats) -> None:
    import interpolation.main as ip
    try:
        ip.run_interpolation_error(repo, defs)
    except Exception as exc:
        stats.failures["interpolation-error"] += 1
        log.error("[interpolation-error] 실패: %s", type(exc).__name__)


def _do_evaluation_sweep(repo, operational: dict, stats: _Stats) -> None:
    import evaluation.main as ev
    try:
        ev.handle_sweep(repo, operational)
    except Exception as exc:
        stats.failures["evaluation-sweep"] += 1
        log.error("[evaluation-sweep] 실패: %s", type(exc).__name__)


# ─ 종료 요약 ──────────────────────────────────────────────────────────────────

def _print_summary(repo, q, stats: _Stats) -> None:
    """워크로드 호출 수, 토픽별 메시지 수, 단계별 실패 수, 결과 테이블 행 수 (2.1.1절, M2)."""
    from sqlalchemy import text

    published_by_topic: dict[str, int] = defaultdict(int)
    for msg in q.drain():
        published_by_topic[msg.topic] += 1

    # M2: 전 결과·인덱스 테이블 행 수 (5.3·5.5절)
    result_tables = [
        "farm_readings",
        "farm_reading_history",
        "farm_areas",
        "axis_status",
        "risk_index_factors",
        "risk_index_levels",
        "interpolation_runs",
        "bulletins",
        "bulletin_details",
        "observations",
        "survey_observations",
        "raw_index",
        "ingest_runs",
    ]
    row_counts: dict[str, int] = {}
    with repo._engine.connect() as conn:
        for tbl in result_tables:
            try:
                n = conn.execute(text(f"SELECT COUNT(*) FROM {tbl}")).scalar()  # noqa: S608
                row_counts[tbl] = int(n)
            except Exception:
                row_counts[tbl] = -1

    summary = {
        "runs": stats.runs,
        "published_by_topic": dict(published_by_topic),
        "stage_failures": dict(stats.failures),
        "result_table_rows": row_counts,
    }

    print("\n─── flowtest 종료 요약 ─────────────────────────────────────────────")
    print(f"  실행 횟수: {stats.runs}")
    print("  토픽별 발행:")
    for topic, cnt in sorted(published_by_topic.items()):
        print(f"    {topic}: {cnt}")
    print("  단계별 처리 실패:")
    if stats.failures:
        for stage, cnt in sorted(stats.failures.items()):
            print(f"    {stage}: {cnt}")
    else:
        print("    (없음)")
    print("  결과 테이블 행 수:")
    for tbl, cnt in row_counts.items():
        label = str(cnt) if cnt >= 0 else "(표 없음)"
        print(f"    {tbl}: {label}")
    print("────────────────────────────────────────────────────────────────────")
    print(json.dumps(summary, ensure_ascii=False))


# ─ 실행 ───────────────────────────────────────────────────────────────────────

def _run_once(args, repo, defs: dict, operational: dict, q, stats: _Stats) -> None:
    stats.runs += 1
    if args.mode == "collect":
        _do_collect(q, stats)
    else:
        _do_replay(args.replay_api, args.replay_date, q, stats)
    _do_interpolation_error(repo, defs, stats)
    _do_evaluation_sweep(repo, operational, stats)


def _bulletin_interval(args) -> int:
    """현재 KST 월에 따라 적조 속보 수집 주기를 반환한다 (H3: 시즌 5-10월, 계획서 2.1.1절)."""
    from datetime import timedelta
    kst = datetime.now(timezone(timedelta(hours=9)))
    if 5 <= kst.month <= 10:
        return args.bulletin_season_interval
    return args.bulletin_offseason_interval


def _run_loop(args, repo, defs: dict, operational: dict, q, stats: _Stats) -> None:
    """
    주기별 반복 실행 — 워크로드마다 다음 실행 시각 관리.
    권장 주기: 조위 10분, 적조 시즌 1시간·시즌 밖 6시간, 정선 1일, 어장환경 주 1회,
               침묵 점검(sweep) 10분, 오늘의 오차(error) 1일 (계획서 2.1.1절).
    Ctrl-C / SIGTERM 으로 종료 후 요약 출력.
    """
    import signal
    import collector.main as cm
    cm._load_adapters()

    _stop = [False]

    def _on_signal(sig, frame):
        log.info("[flowtest] 종료 신호 — 현재 실행 후 종료합니다")
        _stop[0] = True

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    now = time.time()
    # H3: bulletin은 _bulletin_interval로 동적으로 다음 시각을 정함 — 정적 intervals 표에 넣지 않는다
    static_intervals = {
        "tide": args.tide_interval,
        "line": args.line_interval,
        "fishery-watch": args.fishery_interval,
        "interpolation-error": args.error_interval,
        "sweep": args.sweep_interval,
    }
    next_at = {w: now for w in static_intervals}
    next_at["bulletin"] = now

    while not _stop[0]:
        now = time.time()
        ran_any = False
        for workload in list(static_intervals) + ["bulletin"]:
            if now < next_at[workload]:
                continue
            ran_any = True
            stats.runs += 1
            if workload == "interpolation-error":
                _do_interpolation_error(repo, defs, stats)
                next_at[workload] = time.time() + static_intervals[workload]
            elif workload == "sweep":
                _do_evaluation_sweep(repo, operational, stats)
                next_at[workload] = time.time() + static_intervals[workload]
            elif workload == "bulletin":
                if args.mode == "collect":
                    try:
                        cm.main("bulletin", q)
                    except Exception as exc:
                        stats.failures["collector"] += 1
                        # H5: 예외 메시지에 URL·키가 실릴 수 있다 — 종류 이름만 기록 (2.3절)
                        log.error("[collector] bulletin 실패: %s", type(exc).__name__)
                else:
                    _do_replay(args.replay_api, args.replay_date, q, stats)
                # H3: 실행 후 현재 KST 월에 따라 다음 주기 결정
                next_at["bulletin"] = time.time() + _bulletin_interval(args)
            elif args.mode == "collect":
                try:
                    cm.main(workload, q)
                except Exception as exc:
                    stats.failures["collector"] += 1
                    # H5: 예외 메시지에 URL·키가 실릴 수 있다 — 종류 이름만 기록 (2.3절)
                    log.error("[collector] %s 실패: %s", workload, type(exc).__name__)
                next_at[workload] = time.time() + static_intervals[workload]
            else:
                # replay loop: 설정한 api/date 원문 전체를 반복 재생
                _do_replay(args.replay_api, args.replay_date, q, stats)
                next_at[workload] = time.time() + static_intervals[workload]
        if not ran_any:
            time.sleep(1)

    _print_summary(repo, q, stats)


# ─ 진입점 ─────────────────────────────────────────────────────────────────────

def _parse_args(argv):
    p = argparse.ArgumentParser(
        description=(
            "시험 실행기 — 한 프로세스·인메모리 큐로 전 파이프라인 실행 (2.1.1절, 개정 21)"
        ),
        # H2: 기본값 없음 — loop 모드에서는 모두 필수 (main에서 검증)
    )
    p.add_argument(
        "--mode", choices=["collect", "replay"], default="collect",
        help="collect: 실제 API 호출. replay: 원문 저장소 재발행",
    )
    p.add_argument(
        "--run", choices=["once", "loop"], default="once",
        help="once: 한 번 실행 후 종료. loop: 주기 반복 (모든 --*-interval 필수)",
    )
    p.add_argument("--replay-api", metavar="API",
                   help="replay 모드: 원문 api_id (예: dtRecent)")
    p.add_argument("--replay-date", metavar="DATE",
                   help="replay 모드: 날짜 접두 (예: 2026/09/20)")
    # H2: loop 주기 — 기본값 없음. 환경 변수가 있으면 사용, 없으면 None → loop 시 기동 멈춤
    def _env_int(key):
        v = os.environ.get(key)
        return int(v) if v else None

    p.add_argument("--tide-interval", type=int,
                   default=_env_int("FT_TIDE_INTERVAL_SEC"),
                   help="조위 수집 주기(초). loop 필수. 권장: 600")
    p.add_argument("--bulletin-season-interval", type=int,
                   default=_env_int("FT_BULLETIN_SEASON_INTERVAL_SEC"),
                   help="적조 시즌(5-10월) 수집 주기(초). loop 필수. 권장: 3600")
    p.add_argument("--bulletin-offseason-interval", type=int,
                   default=_env_int("FT_BULLETIN_OFFSEASON_INTERVAL_SEC"),
                   help="적조 시즌 밖 수집 주기(초). loop 필수. 권장: 21600")
    p.add_argument("--line-interval", type=int,
                   default=_env_int("FT_LINE_INTERVAL_SEC"),
                   help="정선 수집 주기(초). loop 필수. 권장: 86400")
    p.add_argument("--fishery-interval", type=int,
                   default=_env_int("FT_FISHERY_INTERVAL_SEC"),
                   help="어장환경 수집 주기(초). loop 필수. 권장: 604800")
    p.add_argument("--sweep-interval", type=int,
                   default=_env_int("FT_SWEEP_INTERVAL_SEC"),
                   help="침묵 점검 주기(초). loop 필수. 권장: 600")
    p.add_argument("--error-interval", type=int,
                   default=_env_int("FT_ERROR_INTERVAL_SEC"),
                   help="오늘의 오차 산출 주기(초). loop 필수. 권장: 86400")
    return p.parse_args(argv)


def _validate_loop_intervals(args) -> None:
    """H2: loop 모드에서 모든 주기 인수가 지정됐는지 확인. 빠진 것이 있으면 SystemExit."""
    checks = [
        ("--tide-interval", args.tide_interval),
        ("--bulletin-season-interval", args.bulletin_season_interval),
        ("--bulletin-offseason-interval", args.bulletin_offseason_interval),
        ("--line-interval", args.line_interval),
        ("--fishery-interval", args.fishery_interval),
        ("--sweep-interval", args.sweep_interval),
        ("--error-interval", args.error_interval),
    ]
    missing = [name for name, val in checks if val is None]
    if missing:
        sys.exit(
            f"loop 모드에는 모든 주기 인수가 필요합니다 (인수 또는 FT_*_INTERVAL_SEC 환경 변수):\n"
            f"  {missing}"
        )


def main(argv=None):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )

    args = _parse_args(argv if argv is not None else sys.argv[1:])

    if args.mode == "replay" and not (args.replay_api and args.replay_date):
        sys.exit("replay 모드에는 --replay-api 와 --replay-date 가 필요합니다")

    # H2: loop 모드에서만 주기 검증 (once 모드는 필요 없음)
    if args.run == "loop":
        _validate_loop_intervals(args)

    from sqlalchemy import create_engine
    from common.config import database_url, load_definitions
    from common.repository import SqlRepository
    from common.queue import MemoryQueue
    from common.raw_store import init_store, LocalDiskStore

    engine = create_engine(database_url())
    repo = SqlRepository(engine)
    defs = load_definitions()

    # flowtest는 운영 S3/NATS에 연결하지 않는다 — 로컬 디스크·인메모리 구현을 명시적으로 주입 (2.1.1절, 개정 22)
    _raw_store_path = os.environ.get("FT_RAW_STORE_PATH", "flowtest_raw_store")
    init_store(LocalDiskStore(_raw_store_path))
    log.info("[flowtest] raw store: LocalDiskStore(%s)", _raw_store_path)

    log.info("[flowtest] 실행 전 점검 시작")
    operational = _preflight(repo, defs, collect_mode=(args.mode == "collect"))
    log.info("[flowtest] 실행 전 점검 통과")

    q = MemoryQueue()
    stats = _Stats()
    _setup_pipeline(repo, defs, operational, q, stats)
    log.info("[flowtest] 파이프라인 준비 완료")

    if args.run == "once":
        _run_once(args, repo, defs, operational, q, stats)
        _print_summary(repo, q, stats)
    else:
        _run_loop(args, repo, defs, operational, q, stats)


if __name__ == "__main__":
    main()

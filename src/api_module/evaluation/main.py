"""
evaluation — 세 진입점 (2.1절)
  evaluate : grade.done 컨슈머 → axis_status → result.updated
  sweep     : CronJob 10분 — 신선도·추정 지연·산출 지연 판정
  gate      : 운영 조정 스키마 검사 + 판정 재생 (2.0.6절)
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

from common.clock import kst_today
from common.contract_check import QUEUE_CONTRACT, accept_message
from common.farm_sites import AREA_RULE, assign_area
from common.queue._interface import Message
from common.repository.base import AbstractRepository as BaseRepository
from evaluation._state import (
    AXIS_ADAPTER,
    determine_state,
    should_write_status,
)

_AXES = list(AXIS_ADAPTER.keys())


def _now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def _load_cfg() -> dict:
    """
    운영 조정을 기동 시 한 번 읽는다 (OPERATIONAL_CONFIG_PATH, 2.0.6절).
    없거나 스키마와 다르면 멈춘다 — 키 누락·모르는 키·자리 표시·버전 불일치 (common.config)
    """
    from common.config import load_operational
    return load_operational()


def _stale_hours(cfg: dict, key: str) -> float | None:
    """stale_threshold_hours.<key> — <미결>이면 None."""
    val = cfg.get("stale_threshold_hours", {}).get(key)
    if val is None or str(val).strip().startswith("<"):
        return None
    return float(val)


def _eval_minutes(cfg: dict, key: str) -> float | None:
    val = cfg.get("evaluation", {}).get(key)
    if val is None or str(val).strip().startswith("<"):
        return None
    return float(val)


# 축 → 신선도 키 매핑
_AXIS_STALE_KEY: dict[str, str] = {
    "water_temp": "water_temp",
    "salinity": "salinity_tide",
    "tide_level": "tide_level",
    "wind_speed": "wind_speed",
    "air_temp": "air_temp",
    "red_tide": "red_tide_bulletin",
    "dissolved_oxygen": "dissolved_oxygen",
    "chlorophyll": "chlorophyll",
}

# chlorophyll 임계는 null (게시 감시로 판정) — 판정 정의
_CHLOROPHYLL_STALE_HOURS = None


def _write_status(
    repo: BaseRepository,
    farm_id: str,
    axis: str,
    state: str,
    reason: str | None,
    basis_utc: datetime | None,
    now: datetime,
    existing_map: dict[tuple[str, str], dict],
) -> dict | None:
    """basis_utc 쓰기 규칙을 적용 후 upsert할 행을 반환, 쓰지 않으면 None."""
    existing = existing_map.get((farm_id, axis))
    if not should_write_status(basis_utc, now, existing):
        return None
    return {
        "farm_id": farm_id,
        "axis": axis,
        "state": state,
        "reason": reason,
        "basis_utc": basis_utc,
        "last_checked_utc": now,
    }


def _farm_areas(repo: BaseRepository, farms: list[dict], now: datetime) -> dict[str, str | None]:
    """
    양식장 해역을 모듈이 정하고(common.farm_sites.assign_area) 결과 테이블 farm_areas에 알린다 (1.6·4.9절, 개정 15).
    웹 계약의 양식장 좌표에는 해역이 없다 — farm_sites.area_id를 읽지 않는다
    """
    areas = repo.get_areas()
    out: dict[str, str | None] = {}
    rows = []
    for f in farms:
        hit = assign_area(f["lat"], f["lng"], areas)
        out[f["farm_id"]] = hit["area_id"] if hit else None
        rows.append({
            "farm_id": f["farm_id"],
            "area_id": hit["area_id"] if hit else None,
            "distance_km": hit["distance_km"] if hit else None,
            "rule": AREA_RULE,
            "computed_at_utc": now,
        })
    if rows:
        repo.upsert_farm_areas(rows)
    return out


def handle_grade_done(
    payload: dict,
    repo: BaseRepository,
    queue: object,
    cfg: dict,
) -> None:
    """
    grade.done → axis_status 판정 → result.updated 발행.
    payload: {"schema", "topic", "grade_run_id", "axis", "farm_ids"}
    """
    if not accept_message(payload, "grade.done", repo):
        return
    axis: str = payload["axis"]
    farm_ids: list[str] = payload["farm_ids"]
    now = _now_utc()

    # red_tide_risk: 수집 원천 없음 — provenance=NONE → NOT_USABLE, 그 밖 → NORMAL (4.9절, 개정 20)
    if axis == "red_tide_risk":
        readings_all = repo.get_farm_readings(farm_ids)
        readings_map = {(r["farm_id"], r["axis"]): r for r in readings_all if r["axis"] == axis}
        existing_statuses = repo.get_axis_status(farm_ids)
        existing_map = {(r["farm_id"], r["axis"]): r for r in existing_statuses if r["axis"] == axis}
        rows_to_write: list[dict] = []
        for farm_id in farm_ids:
            farm_reading = readings_map.get((farm_id, axis))
            if farm_reading is not None and farm_reading.get("provenance") == "NONE":
                state = "NOT_USABLE"
                reason = farm_reading.get("none_reason")
                basis_utc = farm_reading.get("computed_at_utc")
            elif farm_reading is not None:
                state = "NORMAL"
                reason = None
                basis_utc = farm_reading.get("computed_at_utc")
            else:
                continue    # 지수 행이 없으면 판정할 값이 없다 — 이 축의 상태는 NOT_USABLE·GRADING_STALE·NORMAL뿐 (4.10절)
            row = _write_status(repo, farm_id, axis, state, reason, basis_utc, now, existing_map)
            if row is not None:
                rows_to_write.append(row)
        if rows_to_write:
            repo.upsert_axis_status(rows_to_write)
        axes_updated = [axis] if rows_to_write else []
        if axes_updated:
            queue.publish(Message(
                topic="result.updated",
                payload={
                    "schema": QUEUE_CONTRACT,
                    "topic": "result.updated",
                    "farm_ids": farm_ids,
                    "axes": axes_updated,
                    "updated_at_utc": now.isoformat(),
                },
            ))
        return

    # 설정
    stale_key = _AXIS_STALE_KEY.get(axis, axis)
    if axis == "chlorophyll":
        threshold_h = _CHLOROPHYLL_STALE_HOURS
    else:
        threshold_h = _stale_hours(cfg, stale_key)

    adapter = AXIS_ADAPTER.get(axis, axis)

    # 공통 읽기
    readings_all = repo.get_farm_readings(farm_ids)
    readings_map: dict[tuple[str, str], dict] = {
        (r["farm_id"], r["axis"]): r for r in readings_all if r["axis"] == axis
    }

    coverage_all = repo.get_axis_coverage()
    coverage_map: dict[tuple[str, str], dict] = {
        (r["area_id"], r["axis"]): r for r in coverage_all
    }

    health_all = repo.get_adapter_health()
    health_map: dict[str, dict] = {r["adapter"]: r for r in health_all}
    health_row = health_map.get(adapter)

    latest_result = repo.get_latest_ingest_result_by_adapter(adapter) if health_row and health_row.get("consecutive_failures", 0) else None

    pub_checks = repo.get_publication_checks(axis="chlorophyll") if axis == "chlorophyll" else []

    existing_statuses = repo.get_axis_status(farm_ids)
    existing_map: dict[tuple[str, str], dict] = {
        (r["farm_id"], r["axis"]): r for r in existing_statuses if r["axis"] == axis
    }

    farms_all = repo.get_farm_sites()
    farm_area_map = _farm_areas(repo, farms_all, now)

    # STALE_SUSPECT 플래그 — 루프 밖에서 한 번만 조회, station_id로 매핑
    obs_flags_by_station: dict[str, object] = {}
    if axis in ("water_temp", "tide_level", "wind_speed", "air_temp", "salinity"):
        obs_rows_stale = repo.get_latest_observations_by_metric(axis)
        obs_flags_by_station = {r["station_id"]: r.get("flags") for r in obs_rows_stale}

    rows_to_write: list[dict] = []
    for farm_id in farm_ids:
        farm_reading = readings_map.get((farm_id, axis))
        area_id = farm_area_map.get(farm_id)
        coverage_row = coverage_map.get((area_id, axis)) if area_id else None

        # STALE_SUSPECT — farm_reading.source_ref 관측소의 플래그만 사용
        stale_suspect_flags = None
        if axis in ("water_temp", "tide_level", "wind_speed", "air_temp", "salinity"):
            source_ref = farm_reading.get("source_ref") if farm_reading else None
            if source_ref:
                stale_suspect_flags = obs_flags_by_station.get(source_ref)

        state, reason, basis_utc = determine_state(
            axis=axis,
            farm_reading=farm_reading,
            coverage_row=coverage_row,
            adapter_health_row=health_row,
            latest_ingest_result=latest_result,
            pub_checks=pub_checks,
            stale_suspect_flags=stale_suspect_flags,
            stale_threshold_hours=threshold_h,
            ref_utc=now,
        )

        row = _write_status(repo, farm_id, axis, state, reason, basis_utc, now, existing_map)
        if row is not None:
            rows_to_write.append(row)

    if rows_to_write:
        repo.upsert_axis_status(rows_to_write)

    # result.updated 발행
    axes_updated = [axis] if rows_to_write else []
    if axes_updated:
        queue.publish(Message(
            topic="result.updated",
            payload={
                "schema": QUEUE_CONTRACT,
                "topic": "result.updated",
                "farm_ids": farm_ids,
                "axes": axes_updated,
                "updated_at_utc": now.isoformat(),
            },
        ))


def handle_sweep(repo: BaseRepository, cfg: dict) -> None:
    """
    evaluation-sweep: 신선도·추정 지연·산출 지연 판정. 값을 새로 만들지 않는다 (2.2절).
    """
    now = _now_utc()

    interpolation_stale_min = _eval_minutes(cfg, "interpolation_stale_minutes")
    grading_stale_min = _eval_minutes(cfg, "grading_stale_minutes")

    # 현재 farm_readings 전체
    all_readings = repo.get_farm_readings()
    readings_map: dict[tuple[str, str], dict] = {
        (r["farm_id"], r["axis"]): r for r in all_readings
    }

    # 최신 interpolation ref_time
    interp_run = repo.get_latest_interpolation_ref_time("water_temp")
    latest_interp_at = interp_run.get("ref_time_utc") if interp_run else None

    # 최신 ingest processed_at
    latest_ingest_at = repo.get_latest_ingest_processed_at()

    existing_statuses = repo.get_axis_status()
    existing_map: dict[tuple[str, str], dict] = {
        (r["farm_id"], r["axis"]): r for r in existing_statuses
    }

    health_all = repo.get_adapter_health()
    health_map: dict[str, dict] = {r["adapter"]: r for r in health_all}

    coverage_all = repo.get_axis_coverage()
    coverage_map: dict[tuple[str, str], dict] = {
        (r["area_id"], r["axis"]): r for r in coverage_all
    }

    farms_all = repo.get_farm_sites()
    farm_area_map = _farm_areas(repo, farms_all, now)

    rows_to_write: list[dict] = []

    for farm in farms_all:
        farm_id = farm["farm_id"]
        area_id = farm_area_map.get(farm_id)

        for axis in _AXES:
            coverage_row = coverage_map.get((area_id, axis)) if area_id else None

            # 커버리지 밖·계절 밖은 sweep에서도 우선
            if coverage_row is not None and not coverage_row.get("covered", True):
                continue
            if coverage_row is not None and not _is_in_season_check(
                coverage_row.get("season_months"), kst_today(now).month
            ):
                continue

            reading = readings_map.get((farm_id, axis))

            # 추정 지연 (water_temp, sweep만)
            if axis == "water_temp" and interpolation_stale_min is not None:
                if latest_interp_at is not None:
                    elapsed_min = (now - latest_interp_at).total_seconds() / 60
                    if elapsed_min > interpolation_stale_min:
                        row = _write_status(
                            repo, farm_id, axis, "INTERPOLATION_STALE", None,
                            latest_interp_at, now, existing_map,
                        )
                        if row:
                            rows_to_write.append(row)
                        continue

            # 산출 지연 (모든 축)
            if grading_stale_min is not None and latest_ingest_at is not None:
                if reading is not None:
                    computed_at = reading.get("computed_at_utc")
                    if computed_at is not None:
                        since_ingest = (latest_ingest_at - computed_at).total_seconds() / 60
                        if since_ingest > grading_stale_min:
                            row = _write_status(
                                repo, farm_id, axis, "GRADING_STALE", None,
                                latest_ingest_at, now, existing_map,
                            )
                            if row:
                                rows_to_write.append(row)
                            continue

            # 신선도 체크 — evaluate와 같은 로직
            adapter = AXIS_ADAPTER.get(axis, axis)
            health_row = health_map.get(adapter)
            stale_key = _AXIS_STALE_KEY.get(axis, axis)
            threshold_h = _CHLOROPHYLL_STALE_HOURS if axis == "chlorophyll" else _stale_hours(cfg, stale_key)

            state, reason, basis_utc = determine_state(
                axis=axis,
                farm_reading=reading,
                coverage_row=coverage_row,
                adapter_health_row=health_row,
                latest_ingest_result=None,
                pub_checks=[],
                stale_suspect_flags=None,
                stale_threshold_hours=threshold_h,
                ref_utc=now,
            )

            # sweep은 신선도 초과·OUTAGE류만 갱신 (NORMAL은 evaluate가 이미 씀)
            if state in ("STALE", "VALUE_FROZEN", "OUTAGE", "SERVER_TIMEOUT",
                         "REQUEST_ERROR", "PARSE_FAILURE"):
                row = _write_status(
                    repo, farm_id, axis, state, reason, basis_utc, now, existing_map,
                )
                if row:
                    rows_to_write.append(row)

    # red_tide_risk: 산출 지연(GRADING_STALE)만 판정한다 — 커버리지·계절·신선도 없음 (4.9절, 개정 20)
    if grading_stale_min is not None and latest_ingest_at is not None:
        for farm in farms_all:
            farm_id = farm["farm_id"]
            reading = readings_map.get((farm_id, "red_tide_risk"))
            if reading is not None:
                computed_at = reading.get("computed_at_utc")
                if computed_at is not None:
                    since_ingest = (latest_ingest_at - computed_at).total_seconds() / 60
                    if since_ingest > grading_stale_min:
                        row = _write_status(
                            repo, farm_id, "red_tide_risk", "GRADING_STALE", None,
                            latest_ingest_at, now, existing_map,
                        )
                        if row:
                            rows_to_write.append(row)

    if rows_to_write:
        repo.upsert_axis_status(rows_to_write)


def _is_in_season_check(season_months: object, month: int) -> bool:
    if season_months is None:
        return True
    if isinstance(season_months, list):
        return month in season_months
    return True


def run_evaluate(payload: dict, repo: BaseRepository, queue: object) -> None:
    cfg = _load_cfg()
    handle_grade_done(payload, repo, queue, cfg)


def run_sweep(repo: BaseRepository) -> None:
    cfg = _load_cfg()
    handle_sweep(repo, cfg)


def run_gate(cfg_path: str) -> int:
    from evaluation._gate import run_gate as _run_gate
    return _run_gate(cfg_path)


def startup_checks(repo) -> None:
    """기동 시 검사 — 테이블·컬럼, areas+axis_coverage 빈 시드 (2.0.3절, 개정 21). 없거나 다르면 멈춘다."""
    from common.contract_check import check_seed_tables
    repo.check_schema()
    check_seed_tables(repo, ["areas", "axis_coverage"])


def _repository():
    """DB 접근 계층 — DATABASE_URL로 만들고 기동 시 테이블 검사 (2.0.3절). 없거나 다르면 멈춘다"""
    from sqlalchemy import create_engine
    from common.config import database_url
    from common.repository import SqlRepository
    repo = SqlRepository(create_engine(database_url()))
    startup_checks(repo)
    return repo


def main(argv: list[str] | None = None) -> int:
    """
    명령 (2.1절 · handoff/k8s/evaluation.yaml):
      (없음) / evaluate — grade.done 컨슈머
      sweep            — 신선도·단계 지연 판정 1회 (CronJob)
      gate <설정 경로>   — 운영 조정 게이트
    """
    args = list(sys.argv[1:] if argv is None else argv)
    cmd = args[0] if args else "evaluate"
    if cmd == "gate":
        return run_gate(args[1] if len(args) > 1 else "")
    if cmd == "sweep":
        run_sweep(_repository())
        return 0
    if cmd == "evaluate":
        # QUEUE_DSN 있으면 NatsQueue, 없으면 멈춘다 (2.2절, 개정 22 — MemoryQueue 폴백 금지)
        from common.queue import NatsQueue
        repo = _repository()
        cfg = _load_cfg()                       # 기동 시 한 번 (2.0.6절)
        _nq = NatsQueue.from_env(
            consumer_name="evaluation-grade-done",
            subscribed_topic="grade.done",
            repo=repo,
        )
        _nq.run(lambda msg: handle_grade_done(msg.payload, repo, _nq, cfg))
        return 0
    print(f"알 수 없는 명령: {cmd}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())

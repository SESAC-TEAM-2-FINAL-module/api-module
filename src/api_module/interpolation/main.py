"""
interpolation 진입점 — 두 워크로드 (계획서 2.1절).
  1. 큐 컨슈머: obs.loaded (조위관측소 적재만)
  2. interpolation-error 명령: 하루 1회 오차 산출 (IDW 추정 없음)
"""
from __future__ import annotations

import logging
import sys
import uuid
from datetime import datetime, timezone

from common.config import database_url, load_definitions
from common.farm_sites import load_farm_sites
from common.queue import Message, Queue

from common.contract_check import QUEUE_CONTRACT, accept_message
from common.idw_inputs import filter_stations
from ._idw import idw_estimate
from ._loocv import compute_loocv

log = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _interp_cfg(defs: dict) -> dict:
    return defs.get("interpolation", {})


def _req(cfg: dict, key: str):
    """판정 정의 interpolation.<key> — 없으면 멈춘다. 코드 기본값으로 대체하지 않는다 (2.0.6절)"""
    if cfg.get(key) is None:
        raise RuntimeError(f"판정 정의 interpolation.{key} 없음 — 코드 기본값으로 대체하지 않는다")
    return cfg[key]


def _station_set_key(station_ids: list[str]) -> str:
    return ",".join(sorted(station_ids))


def _is_pending(val: object) -> bool:
    return val is None or str(val).strip() in ("<미결>", "")


# ─────────────────────────────────────────────────────────────────────────────
# 오차 조회 / 산출 (집합별 캐시)
# ─────────────────────────────────────────────────────────────────────────────

def _get_or_compute_error(repo, station_set_key: str, metric: str,
                          station_coords: dict, cfg: dict, today) -> float | None:
    """
    interpolation_error 조회 (오늘 날짜 + 집합 기준).
    없으면 LOOCV 산출 후 적재.
    error_window_days가 <미결>이면 None 반환.
    """
    window_days = cfg.get("error_window_days")
    if _is_pending(window_days):
        return None
    window_days = int(window_days)

    existing = repo.get_interpolation_error(station_set_key, metric, window_days, today)
    if existing is not None:
        return existing.get("p95")

    obs = repo.get_observations_for_loocv(metric, window_days)
    p95, mae, n_samples = compute_loocv(
        obs, station_coords,
        power_p=float(_req(cfg, "power_p")),
        n_neighbors=int(_req(cfg, "n_neighbors")),
    )

    repo.upsert_interpolation_error([{
        "station_set_key": station_set_key,
        "metric": metric,
        "window_days": window_days,
        "p95": p95,
        "mae": mae,
        "n_samples": n_samples,
        "computed_on": today,
    }])
    return p95


# ─────────────────────────────────────────────────────────────────────────────
# 큐 컨슈머 — obs.loaded (조위관측소만)
# ─────────────────────────────────────────────────────────────────────────────

def handle_obs_loaded(payload: dict, repo, queue: Queue, defs: dict) -> None:
    """
    obs.loaded 처리 — source=tide(조위관측소 적재)인 경우만 (queue-v1, 2.2절).
    IDW → 가중치 기록 → 오차 조회/산출 → 적재 → interp.done 발행.
    멱등: (load_id, metric) 고유 제약이 같은 알림을 막는다.
    """
    if not accept_message(payload, "obs.loaded", repo):
        return
    if payload.get("source") != "tide":
        return

    load_id = payload.get("load_id")
    ref_time_str = payload.get("observed_to_utc")
    if not load_id or not ref_time_str:
        log.warning("obs.loaded 페이로드 불완전 — load_id 또는 observed_to_utc 없음")
        return

    ref_time = datetime.fromisoformat(ref_time_str)
    metric = "water_temp"

    cfg = _interp_cfg(defs)
    align_window_min = int(_req(cfg, "align_window_min"))
    power_p = float(_req(cfg, "power_p"))
    n_neighbors = int(_req(cfg, "n_neighbors"))
    exclude_flatline = None if _is_pending(cfg.get("exclude_flatline")) else cfg.get("exclude_flatline")

    # 관측 및 관측소 좌표 조회
    obs_rows = repo.get_recent_observations(metric, ref_time, align_window_min + 1)
    station_rows = repo.get_stations(source_api="tide")
    station_coords = {r["id"]: {"lat": r["lat"], "lng": r["lng"]} for r in station_rows}

    # 필터 적용
    used_obs = filter_stations(obs_rows, station_coords, ref_time, align_window_min, exclude_flatline)
    if not used_obs:
        log.warning("사용 가능한 조위 관측소 없음 — load_id=%s", load_id)
        return

    station_set_key = _station_set_key([o["station_id"] for o in used_obs])
    now = _utcnow()
    today = now.date()

    error_p95 = _get_or_compute_error(
        repo, station_set_key, metric, station_coords, cfg, today
    )

    # 양식장별 IDW
    # run_id는 이 적재(load_id+metric)에 ONE — unique(load_id, metric) 제약과 대응
    run_id = str(uuid.uuid4())
    error_window_days_val = None if _is_pending(cfg.get("error_window_days")) else int(cfg["error_window_days"])

    farm_rows = repo.get_farm_sites()
    farms = load_farm_sites(farm_rows)

    weight_records: list[dict] = []
    farm_count = 0

    for farm in farms:
        if not farm.active or not farm.valid_coords:
            continue

        value, weights = idw_estimate(farm.lat, farm.lng, used_obs, power_p, n_neighbors)
        if value is None:
            continue

        farm_count += 1
        for w in weights:
            weight_records.append({
                "run_id": run_id,
                "farm_id": farm.farm_id,
                "station_id": w["station_id"],
                "distance_km": w["distance_km"],
                "weight": w["weight"],
            })

    if farm_count > 0:
        repo.upsert_interpolation_runs([{
            "run_id": run_id,
            "load_id": load_id,
            "metric": metric,
            "method": _req(cfg, "method"),
            "power_p": power_p,
            "n_neighbors": n_neighbors,
            "ref_time_utc": ref_time,
            "station_set_key": station_set_key,
            "error_p95": error_p95,
            "error_window_days": error_window_days_val,
            "computed_at_utc": now,
        }])
        repo.upsert_interpolation_weights(weight_records)

    queue.publish(Message(
        topic="interp.done",
        payload={
            "schema": QUEUE_CONTRACT,
            "topic": "interp.done",
            "run_id": run_id,
            "load_id": load_id,
            "farm_count": farm_count,
            "metric": metric,
            "error_p95": error_p95,
            "stations_used": len(used_obs),
        },
    ))


# ─────────────────────────────────────────────────────────────────────────────
# interpolation-error 명령 — 하루 1회 오차 산출
# ─────────────────────────────────────────────────────────────────────────────

def run_interpolation_error(repo, defs: dict) -> None:
    """
    하루 1회 오차 산출 — IDW 추정은 하지 않는다 (2.2절 예외).
    오늘 사용된 관측소 집합 기준으로 interpolation_error를 갱신.
    error_window_days가 <미결>이면 건너뜀.
    """
    cfg = _interp_cfg(defs)
    window_days = cfg.get("error_window_days")
    if _is_pending(window_days):
        log.info("error_window_days 미결 — interpolation-error 건너뜀")
        return

    window_days = int(window_days)
    metric = "water_temp"
    now = _utcnow()
    today = now.date()

    station_rows = repo.get_stations(source_api="tide")
    station_coords = {r["id"]: {"lat": r["lat"], "lng": r["lng"]} for r in station_rows}

    today_sets = repo.get_today_station_sets(metric, today)
    if not today_sets:
        today_sets = [_station_set_key(list(station_coords.keys()))]

    obs = repo.get_observations_for_loocv(metric, window_days)

    for station_set_key in today_sets:
        if repo.get_interpolation_error(station_set_key, metric, window_days, today):
            continue

        included = set(station_set_key.split(","))
        subset_coords = {sid: c for sid, c in station_coords.items() if sid in included}
        subset_obs = [o for o in obs if o["station_id"] in included]

        p95, mae, n_samples = compute_loocv(
            subset_obs, subset_coords,
            power_p=float(_req(cfg, "power_p")),
            n_neighbors=int(_req(cfg, "n_neighbors")),
        )

        repo.upsert_interpolation_error([{
            "station_set_key": station_set_key,
            "metric": metric,
            "window_days": window_days,
            "p95": p95,
            "mae": mae,
            "n_samples": n_samples,
            "computed_on": today,
        }])
        log.info("interpolation_error 적재: set=%s p95=%s n=%s", station_set_key, p95, n_samples)


# ─────────────────────────────────────────────────────────────────────────────
# 진입점
# ─────────────────────────────────────────────────────────────────────────────

def startup_checks(repo) -> None:
    """기동 시 검사 — 테이블·컬럼 검사 (2.0.3절). 없거나 다르면 멈춘다."""
    repo.check_schema()


def main(argv: list[str] | None = None) -> None:
    from sqlalchemy import create_engine
    from common.repository import SqlRepository

    engine = create_engine(database_url())
    repo = SqlRepository(engine)
    startup_checks(repo)

    defs = load_definitions()

    args = argv or sys.argv[1:]
    # "error"는 인계 매니페스트(handoff/k8s/interpolation.yaml)의 CronJob 명령
    if args and args[0] in ("interpolation-error", "error"):
        run_interpolation_error(repo, defs)
    else:
        from common.queue import MemoryQueue

        q = MemoryQueue()

        def _handler(msg: Message) -> None:
            handle_obs_loaded(msg.payload, repo, q, defs)

        q.subscribe("obs.loaded", _handler)
        log.info("interpolation 컨슈머 대기 중 (obs.loaded)")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()

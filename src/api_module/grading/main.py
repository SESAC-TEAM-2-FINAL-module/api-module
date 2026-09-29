"""
grading 진입점 — 두 큐 경로 (계획서 2.1절).
  obs.loaded (모든 축): 물때·풍속·기온·염분·DO·클로로필·적조
  interp.done (수온): IDW 가중치 재계산 → 수온 farm_readings 갱신
두 경로는 서로 기다리지 않는다.
"""
from __future__ import annotations

import logging
import sys
import uuid
from datetime import date, datetime, timezone

from common.config import load_definitions, load_env_config
from common.farm_sites import load_farm_sites, FarmSite
from common.queue import Message, Queue

from ._chlorophyll import find_chlorophyll_obs
from ._do import find_do_obs
from ._nearest import find_nearest_obs, is_alertable_obs
from ._red_tide import find_red_tide_reading
from ._water_temp import grade_water_temp
from ._zone import is_in_excluded_zone

log = logging.getLogger(__name__)

_AXIS_UNITS = {
    "water_temp": "°C",
    "salinity": "psu",
    "tide_level": "m",
    "wind_speed": "m/s",
    "air_temp": "°C",
    "red_tide": "cells/mL",
    "dissolved_oxygen": "mg/L",
    "chlorophyll": "μg/L",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _is_pending(val: object) -> bool:
    return val is None or str(val).strip() in ("<미결>", "")


def _grading_cfg(defs: dict) -> dict:
    return defs.get("grading", {})


def _bulletin_cfg(defs: dict) -> dict:
    return defs.get("bulletin", {})


def _line_cfg(defs: dict) -> dict:
    return defs.get("line", {})


# ─────────────────────────────────────────────────────────────────────────────
# obs.loaded 처리 — 인근 실측 + DO + 클로로필 + 적조
# ─────────────────────────────────────────────────────────────────────────────

def handle_obs_loaded(payload: dict, repo, queue: Queue, defs: dict) -> None:
    """
    obs.loaded → 물때·풍속·기온·염분·DO·클로로필·적조 축 갱신.
    수온은 interp.done 경로로 별도 갱신.
    """
    now = _utcnow()
    today = now.date()

    g_cfg = _grading_cfg(defs)
    b_cfg = _bulletin_cfg(defs)
    l_cfg = _line_cfg(defs)

    wt_thresholds = g_cfg.get("p95_thresholds", {}).get("water_temp", [1.0, 2.0, 3.0])
    salinity_mode = g_cfg.get("salinity_mode")  # <미결> 허용
    excluded_zones = g_cfg.get("excluded_zones")
    line_max_km = g_cfg.get("line_max_distance_km")
    fishery_max_km = g_cfg.get("fishery_max_distance_km")
    surface_rule = l_cfg.get("surface_rule")
    current_window_days = b_cfg.get("current_window_days")

    # 읽기
    farm_rows = repo.get_farm_sites()
    farms = load_farm_sites(farm_rows)

    station_rows = repo.get_stations()

    obs_by_metric: dict[str, list[dict]] = {}
    for axis in ("tide_level", "wind_speed", "air_temp", "salinity"):
        obs_by_metric[axis] = repo.get_latest_observations_by_metric(axis)

    line_surface_obs = repo.get_latest_line_surface_obs("dissolved_oxygen")
    survey_obs = repo.get_latest_survey_obs("chlorophyll", "CHL_S")

    areas = repo.get_areas()
    bulletins_raw = repo.get_bulletins_in_window(today, current_window_days if not _is_pending(current_window_days) else 0)
    cod_news_list = [b["cod_news"] for b in bulletins_raw]
    bulletin_details = repo.get_bulletin_details(cod_news_list) if cod_news_list else []
    bulletin_detail_areas = repo.get_bulletin_detail_areas(cod_news_list) if cod_news_list else []

    readings: list[dict] = []
    history: list[dict] = []
    farm_ids: list[str] = []

    for farm in farms:
        if not farm.active:
            continue

        if not farm.valid_coords:
            # 전 축 INVALID_COORDS
            for axis in ("tide_level", "wind_speed", "air_temp", "salinity",
                         "dissolved_oxygen", "chlorophyll", "red_tide"):
                row = _make_none_row(farm.farm_id, axis, now, "INVALID_COORDS")
                readings.append(row)
                history.append({**row, "ts_utc": now})
            farm_ids.append(farm.farm_id)
            continue

        in_excl = is_in_excluded_zone(farm.lat, farm.lng, excluded_zones)
        farm_ids.append(farm.farm_id)

        # ── 물때·풍속·기온 ────────────────────────────────────────────────
        for axis in ("tide_level", "wind_speed", "air_temp"):
            obs = obs_by_metric.get(axis, [])
            nearest = find_nearest_obs(farm.lat, farm.lng, obs, station_rows)
            if nearest is None:
                row = _make_none_row(farm.farm_id, axis, now, "NO_INPUT")
            else:
                alertable = is_alertable_obs(nearest)
                obs_at = nearest.get("observed_at_utc")
                row = {
                    "farm_id": farm.farm_id,
                    "axis": axis,
                    "value": nearest.get("value"),
                    "lower": None,
                    "upper": None,
                    "unit": _AXIS_UNITS.get(axis, ""),
                    "derivation": "MEASURED",
                    "provenance": "NEAREST",
                    "none_reason": None,
                    "validated_scope": None,
                    "grade": None,
                    "alertable": alertable,
                    "source_ref": nearest["station_id"],
                    "distance_km": nearest["distance_km"],
                    "observed_at_utc": obs_at,
                    "computed_at_utc": now,
                }
            readings.append(row)
            history.append({**row, "ts_utc": now})

        # ── 염분 ─────────────────────────────────────────────────────────
        salinity_obs = obs_by_metric.get("salinity", [])
        nearest_sal = find_nearest_obs(farm.lat, farm.lng, salinity_obs, station_rows)
        if nearest_sal is None:
            sal_row = _make_none_row(farm.farm_id, "salinity", now, "NO_INPUT")
        else:
            if _is_pending(salinity_mode):
                prov = "NONE"
                none_reason = "SALINITY_MODE_NONE"
                alertable = False
            elif salinity_mode == "NEAREST_TIDE":
                prov = "NEAREST"
                none_reason = None
                alertable = is_alertable_obs(nearest_sal)
            else:  # NONE
                prov = "NONE"
                none_reason = "SALINITY_MODE_NONE"
                alertable = False

            sal_row = {
                "farm_id": farm.farm_id,
                "axis": "salinity",
                "value": nearest_sal.get("value"),
                "lower": None,
                "upper": None,
                "unit": _AXIS_UNITS["salinity"],
                "derivation": "MEASURED",
                "provenance": prov,
                "none_reason": none_reason,
                "validated_scope": None,
                "grade": None,
                "alertable": alertable,
                "source_ref": nearest_sal["station_id"],
                "distance_km": nearest_sal["distance_km"],
                "observed_at_utc": nearest_sal.get("observed_at_utc"),
                "computed_at_utc": now,
            }
        readings.append(sal_row)
        history.append({**sal_row, "ts_utc": now})

        # ── DO ────────────────────────────────────────────────────────────
        if _is_pending(surface_rule):
            do_row = _make_none_row(farm.farm_id, "dissolved_oxygen", now, "SURFACE_RULE_UNDECIDED",
                                    derivation="SURVEY")
        else:
            do_obs = find_do_obs(
                farm.lat, farm.lng, line_surface_obs, station_rows,
                surface_rule, line_max_km,
            )
            if do_obs is None:
                do_row = _make_none_row(farm.farm_id, "dissolved_oxygen", now, "NO_INPUT",
                                        derivation="SURVEY")
            else:
                src = f"{do_obs['station_id']}@{do_obs.get('observed_at_utc') or do_obs.get('surveyed_on', '')}"
                do_row = {
                    "farm_id": farm.farm_id,
                    "axis": "dissolved_oxygen",
                    "value": do_obs.get("value"),
                    "lower": None,
                    "upper": None,
                    "unit": _AXIS_UNITS["dissolved_oxygen"],
                    "derivation": "SURVEY",
                    "provenance": "BASELINE",
                    "none_reason": None,
                    "validated_scope": None,
                    "grade": None,
                    "alertable": False,
                    "source_ref": src,
                    "distance_km": do_obs["distance_km"],
                    "observed_at_utc": do_obs.get("observed_at_utc"),
                    "computed_at_utc": now,
                }
        readings.append(do_row)
        history.append({**do_row, "ts_utc": now})

        # ── 클로로필 ─────────────────────────────────────────────────────
        chl_obs = find_chlorophyll_obs(
            farm.lat, farm.lng, survey_obs, station_rows, fishery_max_km,
        )
        if chl_obs is None:
            chl_row = _make_none_row(farm.farm_id, "chlorophyll", now, "NO_INPUT",
                                     derivation="SURVEY")
        else:
            surveyed_on = chl_obs.get("surveyed_on", "")
            src = f"{chl_obs['station_id']}@{surveyed_on}"
            chl_row = {
                "farm_id": farm.farm_id,
                "axis": "chlorophyll",
                "value": chl_obs.get("value"),
                "lower": None,
                "upper": None,
                "unit": _AXIS_UNITS["chlorophyll"],
                "derivation": "SURVEY",
                "provenance": "BASELINE",
                "none_reason": None,
                "validated_scope": None,
                "grade": None,
                "alertable": False,
                "source_ref": src,
                "distance_km": chl_obs["distance_km"],
                "observed_at_utc": None,
                "computed_at_utc": now,
            }
        readings.append(chl_row)
        history.append({**chl_row, "ts_utc": now})

        # ── 적조 ─────────────────────────────────────────────────────────
        rt = find_red_tide_reading(
            farm.lat, farm.lng,
            areas, bulletins_raw, bulletin_details, bulletin_detail_areas,
            current_window_days, today,
        )
        if rt is None:
            # 유효 기간 안 대응 속보 없음 → 정상적 침묵 (제안)
            rt_row = {
                "farm_id": farm.farm_id,
                "axis": "red_tide",
                "value": None,
                "lower": None,
                "upper": None,
                "unit": _AXIS_UNITS["red_tide"],
                "derivation": "OFFICIAL",
                "provenance": "OFFICIAL",
                "none_reason": None,
                "validated_scope": None,
                "grade": None,
                "alertable": False,
                "source_ref": None,
                "distance_km": None,
                "observed_at_utc": None,
                "computed_at_utc": now,
            }
        else:
            rt_row = {
                "farm_id": farm.farm_id,
                "axis": "red_tide",
                "value": rt["value"],
                "lower": None,
                "upper": None,
                "unit": _AXIS_UNITS["red_tide"],
                "derivation": "OFFICIAL",
                "provenance": rt["provenance"],
                "none_reason": rt["none_reason"],
                "validated_scope": None,
                "grade": rt["grade"],
                "alertable": rt["alertable"],
                "source_ref": rt["source_ref"],
                "distance_km": None,
                "observed_at_utc": None,
                "computed_at_utc": now,
            }
        readings.append(rt_row)
        history.append({**rt_row, "ts_utc": now})

    if readings:
        repo.upsert_farm_readings(readings)
        repo.upsert_farm_reading_history(history)

    grade_run_id = str(uuid.uuid4())
    queue.publish(Message(
        topic="grade.done",
        payload={
            "grade_run_id": grade_run_id,
            "axis": "obs.loaded",
            "farm_ids": farm_ids,
        },
    ))


# ─────────────────────────────────────────────────────────────────────────────
# interp.done 처리 — 수온
# ─────────────────────────────────────────────────────────────────────────────

def handle_interp_done(payload: dict, repo, queue: Queue, defs: dict) -> None:
    """
    interp.done → 수온 farm_readings 갱신.
    run_id로 가중치 읽어 station 관측값 × 가중치 = 양식장별 추정값 재계산.
    """
    run_id = payload.get("run_id")
    error_p95 = payload.get("error_p95")
    if not run_id:
        log.warning("interp.done 페이로드에 run_id 없음")
        return

    now = _utcnow()
    g_cfg = _grading_cfg(defs)
    thresholds = g_cfg.get("p95_thresholds", {}).get("water_temp", [1.0, 2.0, 3.0])
    excluded_zones = g_cfg.get("excluded_zones")

    run = repo.get_interpolation_run(run_id)
    if run is None:
        log.warning("interpolation_runs 행 없음: run_id=%s", run_id)
        return

    ref_time_utc = run["ref_time_utc"]
    weights_rows = repo.get_interpolation_weights_by_run(run_id)

    if not weights_rows:
        log.warning("interpolation_weights 없음: run_id=%s", run_id)
        return

    # 관측소별 최신 관측 (ref_time_utc 기준 조회는 이미 인터폴레이션이 수행 — 여기서는 가중치 재사용)
    station_obs = repo.get_latest_observations_by_metric("water_temp")
    obs_map: dict[str, float] = {}
    for obs in station_obs:
        if obs.get("value") is not None and obs.get("missing_reason") is None:
            obs_map[obs["station_id"]] = float(obs["value"])

    # farm_id별 가중치 그룹
    from collections import defaultdict
    farm_weights: dict[str, list[dict]] = defaultdict(list)
    for w in weights_rows:
        farm_weights[w["farm_id"]].append(w)

    farm_rows = repo.get_farm_sites()
    farms = {f.farm_id: f for f in load_farm_sites(farm_rows)}

    readings: list[dict] = []
    history: list[dict] = []
    farm_ids: list[str] = []

    for farm_id, wlist in farm_weights.items():
        farm = farms.get(farm_id)
        if farm is None:
            continue
        if not farm.active or not farm.valid_coords:
            continue

        in_excl = is_in_excluded_zone(farm.lat, farm.lng, excluded_zones)

        # 가중치 재적용으로 추정값 계산
        total_w = sum(w["weight"] for w in wlist if w["station_id"] in obs_map)
        if total_w <= 0:
            continue

        value = sum(
            float(obs_map[w["station_id"]]) * float(w["weight"])
            for w in wlist if w["station_id"] in obs_map
        ) / total_w

        prov, lower, upper, derivation, none_reason = grade_water_temp(value, error_p95, thresholds)

        if in_excl:
            prov = "NONE"
            none_reason = "EXCLUDED_ZONE"

        row = {
            "farm_id": farm_id,
            "axis": "water_temp",
            "value": value,
            "lower": lower,
            "upper": upper,
            "unit": _AXIS_UNITS["water_temp"],
            "derivation": derivation,
            "provenance": prov,
            "none_reason": none_reason,
            "validated_scope": "STATION_SITES",
            "grade": None,
            "alertable": False,  # 불변식 N11: derivation=COMPUTED → alertable=false
            "source_ref": run_id,
            "distance_km": None,
            "observed_at_utc": ref_time_utc,
            "computed_at_utc": now,
        }
        readings.append(row)
        history.append({**row, "ts_utc": now})
        farm_ids.append(farm_id)

    if readings:
        repo.upsert_farm_readings(readings)
        repo.upsert_farm_reading_history(history)

    grade_run_id = str(uuid.uuid4())
    queue.publish(Message(
        topic="grade.done",
        payload={
            "grade_run_id": grade_run_id,
            "axis": "water_temp",
            "farm_ids": farm_ids,
        },
    ))


# ─────────────────────────────────────────────────────────────────────────────
# 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

def _make_none_row(
    farm_id: str,
    axis: str,
    now: datetime,
    none_reason: str,
    derivation: str = "MEASURED",
) -> dict:
    return {
        "farm_id": farm_id,
        "axis": axis,
        "value": None,
        "lower": None,
        "upper": None,
        "unit": _AXIS_UNITS.get(axis, ""),
        "derivation": derivation,
        "provenance": "NONE",
        "none_reason": none_reason,
        "validated_scope": None,
        "grade": None,
        "alertable": False,
        "source_ref": None,
        "distance_km": None,
        "observed_at_utc": None,
        "computed_at_utc": now,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 진입점
# ─────────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> None:
    from sqlalchemy import create_engine
    from common.repository import SqlRepository

    env = load_env_config()
    engine = create_engine(env.database_url)
    repo = SqlRepository(engine)
    repo.check_schema()

    defs = load_definitions()

    from common.queue import MemoryQueue

    q = MemoryQueue()

    def _obs_handler(msg: Message) -> None:
        handle_obs_loaded(msg.payload, repo, q, defs)

    def _interp_handler(msg: Message) -> None:
        handle_interp_done(msg.payload, repo, q, defs)

    q.subscribe("obs.loaded", _obs_handler)
    q.subscribe("interp.done", _interp_handler)
    log.info("grading 컨슈머 대기 중 (obs.loaded · interp.done)")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()

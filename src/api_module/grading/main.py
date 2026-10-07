"""
grading 진입점 — 두 큐 경로 (계획서 2.1절).
  obs.loaded (모든 축): 물때·풍속·기온·염분·DO·클로로필·적조
  interp.done (수온): IDW 가중치 재계산 → 수온 farm_readings 갱신
두 경로는 서로 기다리지 않는다.
"""
from __future__ import annotations

import logging
import sys
from datetime import date, datetime, timezone

from common.clock import kst_today
from common.config import database_url, load_definitions
from common.contract_check import QUEUE_CONTRACT, accept_message
from common.farm_sites import load_farm_sites, FarmSite
from common.idw_inputs import filter_stations
from common.queue import Message, Queue
from common.run_ids import run_id_from

from ._chlorophyll import SURFACE_LAYER as CHL_SURFACE_LAYER, find_chlorophyll_obs
from ._do import find_do_obs
from ._nearest import find_nearest_obs, is_alertable_obs
from ._red_tide import find_red_tide_reading
from ._risk_index import compute_risk_index, check_risk_index_params
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


def _iso_utc(v) -> str:
    """source_ref 시각 표기 — UTC ISO `YYYY-MM-DDTHH:MM:SS` (5.5절). DB 값(datetime)·문자열 모두"""
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%dT%H:%M:%S")
    return str(v or "").replace(" ", "T")


def _is_pending(val: object) -> bool:
    return val is None or str(val).strip() in ("<미결>", "")


def _grading_cfg(defs: dict) -> dict:
    return defs.get("grading", {})


def _p95_thresholds(g_cfg: dict) -> list:
    """판정 정의 grading.p95_thresholds.water_temp — 없으면 멈춘다. 코드 기본값으로 대체하지 않는다 (2.0.6절)"""
    th = (g_cfg.get("p95_thresholds") or {}).get("water_temp")
    if not th:
        raise RuntimeError("판정 정의 grading.p95_thresholds.water_temp 없음 — 코드 기본값으로 대체하지 않는다")
    return th


def _bulletin_cfg(defs: dict) -> dict:
    return defs.get("bulletin", {})


def _line_cfg(defs: dict) -> dict:
    return defs.get("line", {})


# ─────────────────────────────────────────────────────────────────────────────
# obs.loaded 처리 — 인근 실측 + DO + 클로로필 + 적조
# ─────────────────────────────────────────────────────────────────────────────

def is_estuary_station(station_id: str, estuary_stations: list) -> bool:
    """
    하구 영향 조위관측소인가 (grading.estuary_stations, 4.8절).
    목록 값은 tide.stations와 같은 관측소 코드(DT_xxxx), station_id는 "tide:DT_xxxx" — 원천 접두어를 떼고 대조한다
    """
    code = station_id.split(":", 1)[1] if ":" in station_id else station_id
    return code in set(estuary_stations)


def handle_obs_loaded(payload: dict, repo, queue: Queue, defs: dict) -> None:
    """
    obs.loaded → 물때·풍속·기온·염분·DO·클로로필·적조 축 갱신.
    수온은 interp.done 경로로 별도 갱신.
    """
    if not accept_message(payload, "obs.loaded", repo):
        return
    now = _utcnow()
    today = kst_today(now)          # day_report(KST 날짜)와 비교하는 유효 기간 기준일

    g_cfg = _grading_cfg(defs)
    b_cfg = _bulletin_cfg(defs)
    l_cfg = _line_cfg(defs)

    wt_thresholds = _p95_thresholds(g_cfg)
    salinity_mode = g_cfg.get("salinity_mode")
    estuary_stations: list = g_cfg.get("estuary_stations") or []
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
    survey_obs = repo.get_latest_survey_obs("chlorophyll", CHL_SURFACE_LAYER)

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
                if is_estuary_station(nearest_sal["station_id"], estuary_stations):
                    prov = "NONE"
                    none_reason = "EXCLUDED_ZONE"
                    alertable = False
                else:
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
                src = f"{do_obs['station_id']}@{_iso_utc(do_obs.get('observed_at_utc'))}"
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
            src = f"{chl_obs['station_id']}@{_iso_utc(chl_obs.get('observed_at_utc'))}"   # 조사 시각 (5.5절, 개정 14)
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
                "observed_at_utc": chl_obs.get("observed_at_utc"),   # 조사 시각 — 모니터링 시간축 (개정 14)
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

    # 입력 축 행과 지수(세 표)·두 축의 이력을 한 트랜잭션에 쓴다. 지수는 같은 트랜잭션에서
    # 방금 쓴 입력 축 현재값으로 계산한다 (4.10절, 개정 20)
    with repo.transaction() as tr:
        if readings:
            tr.upsert_farm_readings(readings)
            tr.upsert_farm_reading_history(history)
        ri_farm_ids = _write_risk_index(tr, farm_ids, defs, now)

    # 갱신한 축마다 grade.done 하나 — evaluation은 axis 하나씩 판정한다 (2.2절)
    # grade_run_id: obs.loaded load_id에서 결정적으로 생성 — UUID v5 (재전달 멱등, 개정 22)
    load_id = payload.get("load_id", "")
    grade_run_id = run_id_from(f"obs.loaded:{load_id}")
    by_axis: dict[str, list[str]] = {}
    for r in readings:
        by_axis.setdefault(r["axis"], []).append(r["farm_id"])
    for axis, ids in by_axis.items():
        _publish_grade_done(queue, grade_run_id, axis, ids)
    if ri_farm_ids:
        _publish_grade_done(queue, grade_run_id, "red_tide_risk", ri_farm_ids)


# ─────────────────────────────────────────────────────────────────────────────
# interp.done 처리 — 수온
# ─────────────────────────────────────────────────────────────────────────────

def handle_interp_done(payload: dict, repo, queue: Queue, defs: dict) -> None:
    """
    interp.done → 수온 farm_readings 갱신.
    run_id의 기준 시각·가중치와 IDW와 같은 입력 선택 규칙으로 그 실행의 추정값을 재현한다.
    가중치를 받은 관측소의 값을 못 찾으면 남은 가중치로 다시 나누지 않는다 — NONE (최근접 대체 금지).
    """
    if not accept_message(payload, "interp.done", repo):
        return
    run_id = payload.get("run_id")
    error_p95 = payload.get("error_p95")
    if not run_id:
        log.warning("interp.done 페이로드에 run_id 없음")
        return

    now = _utcnow()
    g_cfg = _grading_cfg(defs)
    thresholds = _p95_thresholds(g_cfg)
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

    i_cfg = defs.get("interpolation", {})
    align_window_min = int(i_cfg["align_window_min"])
    exclude_flatline = i_cfg.get("exclude_flatline")
    if _is_pending(exclude_flatline):
        exclude_flatline = None
    station_coords = {r["id"]: {"lat": r["lat"], "lng": r["lng"]} for r in repo.get_stations(source_api="tide")}
    obs_map: dict[str, float] = {
        o["station_id"]: o["value"]
        for o in filter_stations(
            repo.get_recent_observations("water_temp", ref_time_utc, align_window_min + 1),
            station_coords, ref_time_utc, align_window_min, exclude_flatline,
        )
    }

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

        missing = [w["station_id"] for w in wlist if w["station_id"] not in obs_map]
        if missing:
            log.error("run_id=%s farm=%s 가중치 관측소의 기준 시각 관측 없음: %s — 재현 불가, NONE",
                      run_id, farm_id, missing)
            row = {**_make_none_row(farm_id, "water_temp", now, "NO_INPUT", derivation="COMPUTED"),
                   "validated_scope": "STATION_SITES", "source_ref": run_id, "observed_at_utc": ref_time_utc}
            readings.append(row)
            history.append({**row, "ts_utc": now})
            farm_ids.append(farm_id)
            continue

        value = sum(float(obs_map[w["station_id"]]) * float(w["weight"]) for w in wlist)

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

    # 수온 행과 지수(세 표)·두 축의 이력을 한 트랜잭션에 쓴다 — 지수는 방금 쓴 수온으로 계산 (4.10절)
    ri_farm_ids: list[str] = []
    if readings:
        with repo.transaction() as tr:
            tr.upsert_farm_readings(readings)
            tr.upsert_farm_reading_history(history)
            ri_farm_ids = _write_risk_index(tr, farm_ids, defs, now)

    # grade_run_id: interp.done run_id에서 결정적으로 생성 — UUID v5 (재전달 멱등, 개정 22)
    grade_run_id = run_id_from(f"interp.done:{run_id}")
    _publish_grade_done(queue, grade_run_id, "water_temp", farm_ids)
    if ri_farm_ids:
        _publish_grade_done(queue, grade_run_id, "red_tide_risk", ri_farm_ids)


# ─────────────────────────────────────────────────────────────────────────────
# 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

def _write_risk_index(tr, farm_ids: list[str], defs: dict, now) -> list[str]:
    """
    트랜잭션 안에서 양식장마다 지수를 계산해 세 표와 지수 이력을 쓴다 (4.10절).
    tr은 입력 축 행을 이미 쓴 트랜잭션의 저장소다 — 계산은 그 현재값을 읽는다. 반환: 지수를 쓴 양식장
    """
    readings: list[dict] = []
    factor_rows: list[dict] = []
    level_rows: list[dict] = []
    delete_factor_ids: list[str] = []
    delete_level_ids: list[str] = []
    for farm_id in farm_ids:
        reading, factors, level = _compute_risk_for_farm(farm_id, tr, defs, now)
        readings.append(reading)
        if factors:
            factor_rows.extend(factors)
        else:
            delete_factor_ids.append(farm_id)
        if level is not None:
            level_rows.append(level)
        else:
            delete_level_ids.append(farm_id)
    if readings:
        tr.upsert_farm_readings(readings)
        tr.upsert_farm_reading_history([{**r, "ts_utc": now} for r in readings])
    if delete_factor_ids:
        tr.delete_risk_index_factors_by_farm(delete_factor_ids)
    if factor_rows:
        tr.upsert_risk_index_factors(factor_rows)
    if delete_level_ids:
        tr.delete_risk_index_levels_by_farm(delete_level_ids)
    if level_rows:
        tr.upsert_risk_index_levels(level_rows)
    return [r["farm_id"] for r in readings]


def _compute_risk_for_farm(
    farm_id: str,
    repo,
    defs: dict,
    now,
):
    """
    한 양식장의 적조 위험도 지수를 계산한다 (4.10절).
    repo는 트랜잭션 안의 repo여야 한다 — 입력 축 farm_readings를 그 트랜잭션의 현재값으로 읽는다.
    """
    axis_rows = repo.get_farm_readings_for_risk_index(farm_id)
    input_readings: dict[str, dict | None] = {r["axis"]: r for r in axis_rows}
    for ax in ("red_tide", "water_temp", "salinity", "chlorophyll"):
        input_readings.setdefault(ax, None)

    # OK 조건 ③ flags 조회 (salinity·chlorophyll만)
    input_flags: dict[str, object | None] = {
        "red_tide": None, "water_temp": None, "salinity": None, "chlorophyll": None,
    }
    sal_row = input_readings.get("salinity")
    if sal_row and sal_row.get("source_ref") and sal_row.get("observed_at_utc"):
        input_flags["salinity"] = repo.get_obs_flags(
            sal_row["source_ref"], sal_row["observed_at_utc"], "salinity"
        )
    chl_row = input_readings.get("chlorophyll")
    if chl_row and chl_row.get("source_ref") and chl_row.get("observed_at_utc"):
        # source_ref = "station_id@observed_at_utc"
        src = chl_row["source_ref"]
        at_sep = src.rfind("@")
        if at_sep > 0:
            chl_station = src[:at_sep]
            input_flags["chlorophyll"] = repo.get_survey_obs_flags(
                chl_station, chl_row["observed_at_utc"], CHL_SURFACE_LAYER, "chlorophyll"
            )

    return compute_risk_index(farm_id, input_readings, input_flags, defs, now)


def _publish_grade_done(queue: Queue, grade_run_id: str, axis: str, farm_ids: list[str]) -> None:
    """grade.done — 계약 queue-v2 grade_done (schema·topic·grade_run_id·axis·farm_ids)"""
    queue.publish(Message(
        topic="grade.done",
        payload={
            "schema": QUEUE_CONTRACT,
            "topic": "grade.done",
            "grade_run_id": grade_run_id,
            "axis": axis,
            "farm_ids": sorted(set(farm_ids)),
        },
    ))


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

def startup_checks(repo, defs: dict | None = None) -> dict:
    """기동 시 검사 — 테이블·컬럼, 빈 해역 시드, 지수 파라미터 전제 (2.0.3·2.1절, L2: 원래 순서 복원).
    defs가 None이면 내부에서 로드 (check_seed_tables 이후 — 원래 순서). defs를 반환한다."""
    repo.check_schema()
    from common.contract_check import check_seed_tables
    check_seed_tables(repo, ["areas"])
    if defs is None:
        defs = load_definitions()
    # K9: 값이 정해진 위험도 지수 파라미터만 검사 (<미결>이면 건너뜀)
    violations = check_risk_index_params(defs)
    if violations:
        raise SystemExit("risk_index 파라미터 전제 위반 — 기동 멈춤:\n" + "\n".join(f"  {v}" for v in violations))
    return defs


def main(argv: list[str] | None = None) -> None:
    from sqlalchemy import create_engine
    from common.repository import SqlRepository

    engine = create_engine(database_url())
    repo = SqlRepository(engine)
    defs = startup_checks(repo)  # defs는 startup_checks 내부에서 로드 (원래 순서)

    # obs.loaded·interp.done 두 컨슈머를 한 큐에서 돌아가며 받는다 — QUEUE_DSN 없으면 멈춘다 (2.2절, 개정 22)
    from common.queue import open_queue
    q = open_queue("grading", repo)
    try:
        q.subscribe("obs.loaded", lambda msg: handle_obs_loaded(msg.payload, repo, q, defs))
        q.subscribe("interp.done", lambda msg: handle_interp_done(msg.payload, repo, q, defs))
        q.run()
    finally:
        q.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()

"""축 상태 판정 로직 (4.9절). 순수 함수 — DB 접근 없음."""
from __future__ import annotations

from datetime import datetime

from common.clock import kst_today

# 축 → 어댑터 매핑 (판정 정의)
AXIS_ADAPTER: dict[str, str] = {
    "water_temp": "tide",
    "salinity": "tide",
    "tide_level": "tide",
    "wind_speed": "tide",
    "air_temp": "tide",
    "red_tide": "bulletin",
    "dissolved_oxygen": "line",
    "chlorophyll": "fishery",
}

# 응답 상태(ingest_runs.status) → 3번 묶음 state (3.2절)
_CODE_STATE: dict[str, str] = {
    "HTTP_ERROR": "OUTAGE",
    "NET_ERROR": "OUTAGE",
    "QUOTA": "OUTAGE",
    "TIMEOUT_05": "SERVER_TIMEOUT",
    "BAD_REQUEST": "REQUEST_ERROR",
    "NO_SERVICE": "REQUEST_ERROR",
    "KEY_ERROR": "REQUEST_ERROR",
    "PARSE_FAILURE": "PARSE_FAILURE",
    "INCOMPLETE": "PARSE_FAILURE",
    "FILTER_IGNORED": "FILTER_IGNORED",
    "SUSPENDED": "ITEM_SUSPENDED",
    "NO_DATA": "NO_MATCH",
}


def _has_stale_suspect(flags: object) -> bool:
    if isinstance(flags, dict):
        return bool(flags.get("STALE_SUSPECT"))
    if isinstance(flags, list):
        return "STALE_SUSPECT" in flags
    return False


def _is_in_season(season_months: object, month: int) -> bool:
    if season_months is None:
        return True
    if isinstance(season_months, list):
        return month in season_months
    return True


def _is_publication_pending(pub_checks: list[dict]) -> bool:
    """가장 최근 publication_checks 행에서 total_count=0이면 게시 대기."""
    if not pub_checks:
        return True
    latest = max(
        pub_checks,
        key=lambda r: r.get("checked_at_utc") or datetime.min,
    )
    return (latest.get("total_count") or 0) == 0


def _adapter_state(health: dict | None, latest_result: dict | None) -> str | None:
    """연속 실패 중이면 최근 처리 결과의 응답 상태로 3번 묶음 state를 반환, 아니면 None."""
    if health is None or not health.get("consecutive_failures", 0):
        return None
    last_ok = health.get("last_success_utc")
    last_fail = health.get("last_failure_utc")
    if last_fail is None:
        return None
    if last_ok is not None and last_ok >= last_fail:
        return None

    if latest_result is not None:
        # ingest_runs.status = 응답 상태 이름(5.3절 결정 D6). result_code는 원래 코드("05" 등)라 이 표의 키가 아니다
        state = _CODE_STATE.get(latest_result.get("status") or "")
        if state:
            return state
    return "OUTAGE"


def determine_state(
    axis: str,
    farm_reading: dict | None,
    coverage_row: dict | None,
    adapter_health_row: dict | None,
    latest_ingest_result: dict | None,
    pub_checks: list[dict],
    stale_suspect_flags: object,
    stale_threshold_hours: float | None,
    ref_utc: datetime,
) -> tuple[str, str | None, datetime | None]:
    """
    우선순위 순서로 state를 결정한다 (4.9절).
    Returns: (state, reason, basis_utc)
    basis_utc = 판정에 쓴 가장 새 입력의 시각
    """
    # 1. OUT_OF_COVERAGE
    if coverage_row is not None and not coverage_row.get("covered", True):
        return ("OUT_OF_COVERAGE", coverage_row.get("reason"), None)

    # 2. OUT_OF_SEASON
    if coverage_row is not None:
        if not _is_in_season(coverage_row.get("season_months"), kst_today(ref_utc).month):
            return ("OUT_OF_SEASON", None, None)

    # 3. 원천·호출 문제
    adapter_st = _adapter_state(adapter_health_row, latest_ingest_result)
    if adapter_st is not None:
        return (adapter_st, None, None)

    # 5. NOT_USABLE
    if farm_reading is not None and farm_reading.get("provenance") == "NONE":
        basis = farm_reading.get("computed_at_utc")
        return ("NOT_USABLE", farm_reading.get("none_reason"), basis)

    if farm_reading is None:
        return ("STALE", None, None)

    basis = farm_reading.get("computed_at_utc")

    # 적조 신선도 — last_success_utc 기준 (P15)
    if axis == "red_tide":
        if adapter_health_row is not None and stale_threshold_hours is not None:
            last_ok = adapter_health_row.get("last_success_utc")
            if last_ok is not None:
                elapsed = (ref_utc - last_ok).total_seconds() / 3600
                if elapsed > stale_threshold_hours:
                    return ("STALE", None, last_ok)
        if farm_reading.get("value") is None:
            return ("NORMAL_SILENCE", None, basis)
        return ("NORMAL", None, basis)

    # 6. STALE — observed_at_utc 신선도
    obs_at = farm_reading.get("observed_at_utc")
    if obs_at is not None and stale_threshold_hours is not None:
        elapsed = (ref_utc - obs_at).total_seconds() / 3600
        if elapsed > stale_threshold_hours:
            return ("STALE", None, obs_at)

    # 7. VALUE_FROZEN
    if _has_stale_suspect(stale_suspect_flags):
        return ("VALUE_FROZEN", None, basis)

    # 8. PUBLICATION_PENDING
    if axis == "chlorophyll" and _is_publication_pending(pub_checks):
        return ("PUBLICATION_PENDING", None, basis)

    # 8. NORMAL_SILENCE
    if farm_reading.get("value") is None:
        return ("NORMAL_SILENCE", None, basis)

    # 9. NORMAL
    return ("NORMAL", None, basis)


def should_write_status(
    new_basis: datetime | None,
    new_checked: datetime,
    existing: dict | None,
) -> bool:
    """basis_utc 쓰기 규칙 (4.9절): 새 basis가 더 새롭거나, 같으면 checked가 더 나중."""
    if existing is None:
        return True
    ex_basis = existing.get("basis_utc")
    ex_checked = existing.get("last_checked_utc")

    # 기존에 basis가 없으면 항상 쓴다
    if ex_basis is None:
        return True
    if new_basis is None:
        # 새 판정에 basis 없음 — 기존에 basis 있으면 쓰지 않는다
        return False

    if new_basis > ex_basis:
        return True
    if new_basis == ex_basis:
        return ex_checked is None or new_checked > ex_checked
    return False

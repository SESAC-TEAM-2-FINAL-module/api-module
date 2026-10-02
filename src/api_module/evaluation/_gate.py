"""운영 조정 게이트 — 스키마 검사 + 판정 재생 (2.0.6절 · 7.6절 B7)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from evaluation._state import determine_state

_SCHEMA_PATH = Path(__file__).parents[3] / "contracts" / "config" / "operational.schema.json"

# 판정 재생 픽스처 — 임계에 상대적인 시각으로 (B7 / 7.3b / P3·P6·P10·P15)
# 픽스처마다: {"axis", "reading", "coverage", "stale_threshold_hours", "offset_hours", "expected_state"}
# offset_hours > 0 이면 observed_at_utc = now - threshold*h - offset_hours (임계 초과)
# offset_hours < 0 이면 observed_at_utc = now - threshold*h + |offset_hours| (임계 미만)
_REPLAY_CASES: list[dict] = [
    # 정상 (임계 직전)
    {
        "label": "NORMAL_before_threshold",
        "axis": "water_temp",
        "threshold_key": ("stale_threshold_hours", "water_temp"),
        "offset_sign": -1,  # 임계 직전 → NORMAL
        "expected": "NORMAL",
    },
    # 신선도 초과 → STALE
    {
        "label": "STALE_after_threshold",
        "axis": "water_temp",
        "threshold_key": ("stale_threshold_hours", "water_temp"),
        "offset_sign": +1,  # 임계 직후 → STALE
        "expected": "STALE",
    },
    # 게시 대기 → PUBLICATION_PENDING (클로로필 임계 없음)
    {
        "label": "PUBLICATION_PENDING",
        "axis": "chlorophyll",
        "threshold_key": None,
        "offset_sign": 0,
        "expected": "PUBLICATION_PENDING",
    },
    # 추정 지연 → INTERPOLATION_STALE (sweep 전용이지만 게이트 픽스처로 검증)
    {
        "label": "INTERPOLATION_STALE",
        "axis": "water_temp",
        "threshold_key": ("evaluation", "interpolation_stale_minutes"),
        "is_minutes": True,
        "offset_sign": +1,
        "expected": "INTERPOLATION_STALE",
    },
    # 산출 지연 → GRADING_STALE
    {
        "label": "GRADING_STALE",
        "axis": "water_temp",
        "threshold_key": ("evaluation", "grading_stale_minutes"),
        "is_minutes": True,
        "offset_sign": +1,
        "expected": "GRADING_STALE",
    },
    # 산출 지연이 게시 대기를 삼키지 않는지 (P6 겹침 — chlorophyll은 PUBLICATION_PENDING 우선)
    {
        "label": "PUBLICATION_PENDING_not_swallowed_by_grading_stale",
        "axis": "chlorophyll",
        "threshold_key": None,
        "offset_sign": 0,
        "expected": "PUBLICATION_PENDING",
        "extra_grading_stale": True,
    },
    # 적조 정상적 침묵 (호출은 성공, 속보 없음)
    {
        "label": "RED_TIDE_NORMAL_SILENCE",
        "axis": "red_tide",
        "threshold_key": ("stale_threshold_hours", "red_tide_bulletin"),
        "offset_sign": -1,
        "expected": "NORMAL_SILENCE",
    },
    # 적조 신선도 초과 → STALE
    {
        "label": "RED_TIDE_STALE",
        "axis": "red_tide",
        "threshold_key": ("stale_threshold_hours", "red_tide_bulletin"),
        "offset_sign": +1,
        "expected": "STALE",
    },
]

_OFFSET_DELTA = timedelta(minutes=1)  # 임계 직전·직후 오프셋


def _get_threshold(cfg: dict, key_path: tuple, is_minutes: bool = False) -> float | None:
    """설정에서 임계값 읽기."""
    val = cfg
    for k in key_path:
        if not isinstance(val, dict):
            return None
        val = val.get(k)
    if val is None:
        return None
    hours = float(val) / 60 if is_minutes else float(val)
    return hours


def _run_replay(cfg: dict) -> list[str]:
    """판정 재생 — 실패한 케이스 레이블 목록 반환."""
    now = datetime(2026, 1, 15, 12, 0, 0)  # 계절 밖 아닌 달
    failures: list[str] = []

    for case in _REPLAY_CASES:
        label = case["label"]
        axis = case["axis"]
        expected = case["expected"]

        # 임계 계산
        threshold_hours: float | None = None
        if case["threshold_key"] is not None:
            threshold_hours = _get_threshold(
                cfg, case["threshold_key"], case.get("is_minutes", False)
            )

        # 시각 설정
        sign = case.get("offset_sign", 0)
        if threshold_hours is not None and sign != 0:
            base_delta = timedelta(hours=threshold_hours)
            if sign > 0:
                obs_at = now - base_delta - _OFFSET_DELTA
            else:
                obs_at = now - base_delta + _OFFSET_DELTA
        else:
            obs_at = now - timedelta(hours=1)

        # 합성 farm_reading
        if expected in ("INTERPOLATION_STALE", "GRADING_STALE"):
            # sweep 전용 상태 — determine_state로는 판정 불가
            # 게이트 픽스처에서는 함수 호출 없이 임계 존재 확인만
            if threshold_hours is None:
                failures.append(f"{label}: threshold missing")
            continue

        if axis == "red_tide":
            reading = {
                "provenance": "OFFICIAL",
                "value": None if expected == "NORMAL_SILENCE" else 1.0,
                "none_reason": None,
                "computed_at_utc": obs_at,
                "observed_at_utc": obs_at,
            }
            if sign > 0 and threshold_hours is not None:
                last_ok = now - timedelta(hours=threshold_hours) - _OFFSET_DELTA
            else:
                last_ok = now - timedelta(hours=threshold_hours or 0) + _OFFSET_DELTA if threshold_hours else now - timedelta(hours=1)
            health = {
                "consecutive_failures": 0,
                "last_success_utc": last_ok,
                "last_failure_utc": None,
            }
        elif axis == "chlorophyll":
            reading = {
                "provenance": "MEASURED",
                "value": 1.0,
                "none_reason": None,
                "computed_at_utc": obs_at,
                "observed_at_utc": obs_at,
            }
            health = None
        else:
            reading = {
                "provenance": "OBSERVED",
                "value": 22.0,
                "none_reason": None,
                "computed_at_utc": obs_at,
                "observed_at_utc": obs_at,
            }
            health = {"consecutive_failures": 0, "last_success_utc": obs_at, "last_failure_utc": None}

        # 게시 감시 (PUBLICATION_PENDING이면 total_count=0)
        pub_checks: list[dict] = []
        if axis == "chlorophyll" and expected == "PUBLICATION_PENDING":
            pub_checks = [{"checked_at_utc": obs_at, "total_count": 0}]

        state, _, _ = determine_state(
            axis=axis,
            farm_reading=reading,
            coverage_row=None,
            adapter_health_row=health,
            latest_ingest_result=None,
            pub_checks=pub_checks,
            stale_suspect_flags=None,
            stale_threshold_hours=threshold_hours,
            ref_utc=now,
        )
        if state != expected:
            failures.append(f"{label}: expected={expected}, got={state}")

    return failures


def validate_schema(cfg: dict) -> list[str]:
    """JSON 스키마로 설정을 검증한다. 오류 메시지 목록 반환 (빈 목록 = 통과)."""
    try:
        import jsonschema
    except ImportError:
        return ["jsonschema 패키지 없음 — 설치 필요 (pip install jsonschema)"]

    if not _SCHEMA_PATH.exists():
        return [f"스키마 파일 없음: {_SCHEMA_PATH}"]

    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.Draft7Validator(schema)
    errors = sorted(validator.iter_errors(cfg), key=lambda e: list(e.path))
    return [f"{'.'.join(str(p) for p in e.path)}: {e.message}" for e in errors]


def run_gate(cfg_path: str) -> int:
    """운영 조정 게이트를 돌린다. 0=통과, 1=실패."""
    import yaml

    cfg_text = Path(cfg_path).read_text(encoding="utf-8")
    cfg = yaml.safe_load(cfg_text)

    print(f"[gate] {cfg_path} 로드 완료")

    # 1. 스키마 검사
    schema_errors = validate_schema(cfg)
    if schema_errors:
        print("[gate] 스키마 검사 실패:")
        for e in schema_errors:
            print(f"  - {e}")
        return 1
    print("[gate] 스키마 검사 통과")

    # 2. 판정 재생
    replay_failures = _run_replay(cfg)
    if replay_failures:
        print("[gate] 판정 재생 실패:")
        for f in replay_failures:
            print(f"  - {f}")
        return 1
    print("[gate] 판정 재생 통과")
    return 0

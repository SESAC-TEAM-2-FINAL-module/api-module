"""
조위관측소 어댑터 검사 (I-2)
Q5: 값 멈춤 감지 (STALE_SUSPECT) — tide.flatline_minutes에 상대적
STATION_INACTIVE: 최근 24h 전 행 결측
0.000 결측 (R0): water_temp·salinity만 ZERO_SENTINEL
KST → UTC 변환
"""
import os
import pytest
from datetime import datetime, timedelta

from common.classifier import ParsedResponse
from processor.adapters.tide._adapter import (
    TideProcessorAdapter,
    _kst_to_utc,
    _parse_value,
    _apply_flatline_flags,
    _apply_station_inactive,
)

_ADAPTER = TideProcessorAdapter()


# ── 헬퍼 ────────────────────────────────────────────────────────────────────

def _utc(dt_str: str) -> str:
    """KST 문자열 → UTC ISO 문자열"""
    return _kst_to_utc(dt_str)


def _make_row(station_id="tide:DT_0016", observed_at_utc="2026-01-01T00:00:00",
              metric="water_temp", value=20.0, missing_reason=None):
    return {
        "station_id": station_id,
        "observed_at_utc": observed_at_utc,
        "metric": metric,
        "value": value,
        "missing_reason": missing_reason,
        "flags": [],
        "raw_id": "test_raw",
    }


def _item(obs_code="DT_0016", obs_dt="2026-01-01 09:00:00", **fields):
    base = {"obsCode": obs_code, "obsrvnDt": obs_dt,
            "wtem": "20.0", "slntQty": "33.0",
            "bscTdlvHgt": "1.5", "wspd": "5.0",
            "wdir": "180", "artmp": "15.0"}
    base.update(fields)
    return base


# ── KST → UTC 변환 ──────────────────────────────────────────────────────────

def test_kst_to_utc_basic():
    """09:00 KST → 00:00 UTC"""
    assert _kst_to_utc("2026-01-01 09:00:00") == "2026-01-01T00:00:00"

def test_kst_to_utc_midnight():
    """00:00 KST → 전날 15:00 UTC"""
    assert _kst_to_utc("2026-01-02 00:00:00") == "2026-01-01T15:00:00"

def test_kst_to_utc_t_separator():
    """T 구분자 허용"""
    assert _kst_to_utc("2026-01-01T09:00:00") == "2026-01-01T00:00:00"

def test_kst_to_utc_empty():
    assert _kst_to_utc("") == ""


# ── 0.000 결측 (R0) ─────────────────────────────────────────────────────────

def test_zero_sentinel_water_temp():
    v, reason = _parse_value("0.000", "water_temp")
    assert v is None
    assert reason == "ZERO_SENTINEL"

def test_zero_sentinel_salinity():
    v, reason = _parse_value(0.0, "salinity")
    assert v is None
    assert reason == "ZERO_SENTINEL"

def test_zero_not_sentinel_tide_level():
    """조위 0.0은 결측 아님"""
    v, reason = _parse_value("0.000", "tide_level")
    assert v == 0.0
    assert reason is None

def test_zero_not_sentinel_wind_speed():
    """풍속 0.0은 결측 아님"""
    v, reason = _parse_value("0.0", "wind_speed")
    assert v == 0.0
    assert reason is None

def test_zero_not_sentinel_wind_dir():
    v, reason = _parse_value("0", "wind_dir")
    assert v == 0.0
    assert reason is None

def test_zero_not_sentinel_air_temp():
    v, reason = _parse_value("0.0", "air_temp")
    assert v == 0.0
    assert reason is None

def test_empty_value():
    v, reason = _parse_value("", "water_temp")
    assert v is None
    assert reason == "MISSING"

def test_none_value():
    v, reason = _parse_value(None, "salinity")
    assert v is None
    assert reason == "MISSING"

def test_normal_value():
    v, reason = _parse_value("25.5", "water_temp")
    assert v == 25.5
    assert reason is None


# ── interpret ────────────────────────────────────────────────────────────────

def test_interpret_produces_6_metric_rows():
    """item 1개 → 6개 metric 행"""
    pr = ParsedResponse(format="json", result_code="00", total_count=1,
                        items=[_item()], parse_status="OK")
    rows = _ADAPTER.interpret(pr, {"raw_id": "r1"})
    assert len(rows) == 6
    metrics = {r["metric"] for r in rows}
    assert metrics == {"water_temp", "salinity", "tide_level", "wind_speed", "wind_dir", "air_temp"}

def test_interpret_station_id_prefix():
    """station_id = 'tide:' + obsCode"""
    pr = ParsedResponse(format="json", result_code="00", total_count=1,
                        items=[_item(obs_code="DT_0049")], parse_status="OK")
    rows = _ADAPTER.interpret(pr, {})
    assert all(r["station_id"] == "tide:DT_0049" for r in rows)

def test_interpret_kst_to_utc():
    """obsrvnDt 09:00 KST → 00:00 UTC"""
    pr = ParsedResponse(format="json", result_code="00", total_count=1,
                        items=[_item(obs_dt="2026-06-01 09:00:00")], parse_status="OK")
    rows = _ADAPTER.interpret(pr, {})
    assert all(r["observed_at_utc"] == "2026-06-01T00:00:00" for r in rows)

def test_interpret_skips_item_without_obs_code():
    """obsCode 없는 item은 건너뜀"""
    pr = ParsedResponse(format="json", result_code="00", total_count=1,
                        items=[{"obsrvnDt": "2026-01-01 09:00:00", "wtem": "20.0"}],
                        parse_status="OK")
    rows = _ADAPTER.interpret(pr, {})
    assert rows == []


# ── normalize: 기본 ──────────────────────────────────────────────────────────

def test_normalize_zero_sentinel_in_water_temp():
    rows = [_make_row(metric="water_temp", value=None, missing_reason=None)]
    rows[0]["_raw_value"] = "0.000"
    rows_with_raw = [{**r, "_raw_value": r.pop("_raw_value", None)} for r in rows]
    # interpret()를 거치지 않고 직접 normalize 테스트 — _raw_value 포함 행 필요
    pre_rows = [{"station_id": "tide:DT_0016", "observed_at_utc": "2026-01-01T00:00:00",
                 "metric": "water_temp", "_raw_value": "0.000", "flags": [], "missing_reason": None,
                 "raw_id": "r1"}]
    result = _ADAPTER.normalize(pre_rows)
    assert result[0]["value"] is None
    assert result[0]["missing_reason"] == "ZERO_SENTINEL"


# ── Q5: 값 멈춤 감지 ────────────────────────────────────────────────────────

def _flatline_rows(n_minutes: int, value: float = 20.0,
                   station_id="tide:DT_0016", metric="water_temp"):
    """n_minutes 간격으로 같은 값을 가진 rows 생성"""
    base_dt = datetime(2026, 1, 1, 0, 0, 0)
    rows = []
    for i in range(n_minutes + 1):
        rows.append(_make_row(
            station_id=station_id,
            observed_at_utc=(base_dt + timedelta(minutes=i)).strftime("%Y-%m-%dT%H:%M:%S"),
            metric=metric,
            value=value,
        ))
    return rows


def test_Q5_below_threshold_no_flag():
    """flatline_minutes 직전 — STALE_SUSPECT 없음"""
    flatline_minutes = 30
    rows = _flatline_rows(flatline_minutes - 1)
    _apply_flatline_flags(rows, flatline_minutes)
    flagged = [r for r in rows if "STALE_SUSPECT" in r.get("flags", [])]
    assert flagged == []


def test_Q5_at_threshold_flag():
    """flatline_minutes 도달 — STALE_SUSPECT"""
    flatline_minutes = 30
    rows = _flatline_rows(flatline_minutes)
    _apply_flatline_flags(rows, flatline_minutes)
    flagged = [r for r in rows if "STALE_SUSPECT" in r.get("flags", [])]
    assert len(flagged) >= 1


def test_Q5_value_change_resets():
    """값이 바뀌면 streak 초기화 — 직전 구간에 플래그 없음"""
    flatline_minutes = 10
    base_dt = datetime(2026, 1, 1, 0, 0, 0)
    rows = []
    # 0~9분: 20.0 (9분 streak — 직전)
    for i in range(10):
        rows.append(_make_row(
            observed_at_utc=(base_dt + timedelta(minutes=i)).strftime("%Y-%m-%dT%H:%M:%S"),
            value=20.0,
        ))
    # 10분: 21.0 (값 변경)
    rows.append(_make_row(
        observed_at_utc=(base_dt + timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S"),
        value=21.0,
    ))
    _apply_flatline_flags(rows, flatline_minutes)
    flagged = [r for r in rows if "STALE_SUSPECT" in r.get("flags", [])]
    assert flagged == []


def test_Q5_missing_value_breaks_streak():
    """결측(value=None)은 streak을 끊음"""
    flatline_minutes = 5
    base_dt = datetime(2026, 1, 1, 0, 0, 0)
    rows = [
        _make_row(observed_at_utc=(base_dt).strftime("%Y-%m-%dT%H:%M:%S"), value=20.0),
        _make_row(observed_at_utc=(base_dt + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%S"), value=20.0),
        # 결측으로 streak 초기화
        _make_row(observed_at_utc=(base_dt + timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%S"), value=None),
        _make_row(observed_at_utc=(base_dt + timedelta(minutes=3)).strftime("%Y-%m-%dT%H:%M:%S"), value=20.0),
        _make_row(observed_at_utc=(base_dt + timedelta(minutes=4)).strftime("%Y-%m-%dT%H:%M:%S"), value=20.0),
    ]
    _apply_flatline_flags(rows, flatline_minutes)
    flagged = [r for r in rows if "STALE_SUSPECT" in r.get("flags", [])]
    assert flagged == []


def test_Q5_different_metrics_independent():
    """metric별 독립 — water_temp streak이 salinity streak에 영향 없음"""
    flatline_minutes = 5
    base_dt = datetime(2026, 1, 1, 0, 0, 0)

    wt_rows = _flatline_rows(flatline_minutes, value=20.0, metric="water_temp")
    sal_rows = _flatline_rows(flatline_minutes - 1, value=33.0, metric="salinity")
    all_rows = wt_rows + sal_rows

    _apply_flatline_flags(all_rows, flatline_minutes)

    wt_flagged = [r for r in all_rows if r["metric"] == "water_temp" and "STALE_SUSPECT" in r["flags"]]
    sal_flagged = [r for r in all_rows if r["metric"] == "salinity" and "STALE_SUSPECT" in r["flags"]]
    assert len(wt_flagged) >= 1
    assert sal_flagged == []


# ── STATION_INACTIVE ─────────────────────────────────────────────────────────

def test_station_inactive_all_missing_24h():
    """최근 24h 전 행이 모두 결측 → station_inactive=True"""
    base_dt = datetime(2026, 1, 1, 12, 0, 0)
    rows = []
    for i in range(24):
        rows.append(_make_row(
            observed_at_utc=(base_dt - timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%S"),
            value=None, missing_reason="ZERO_SENTINEL",
        ))
    _apply_station_inactive(rows)
    assert all(r.get("station_inactive") is True for r in rows)


def test_station_inactive_has_valid_value():
    """정상 값이 하나라도 있으면 STATION_INACTIVE 아님"""
    base_dt = datetime(2026, 1, 1, 12, 0, 0)
    rows = [
        _make_row(observed_at_utc=(base_dt).strftime("%Y-%m-%dT%H:%M:%S"), value=20.0),
    ]
    for i in range(1, 10):
        rows.append(_make_row(
            observed_at_utc=(base_dt - timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%S"),
            value=None, missing_reason="ZERO_SENTINEL",
        ))
    _apply_station_inactive(rows)
    assert all(not r.get("station_inactive") for r in rows)


def test_station_inactive_beyond_24h_ignored():
    """24h 이전 결측은 STATION_INACTIVE 판정에 사용하지 않음"""
    base_dt = datetime(2026, 1, 2, 12, 0, 0)
    rows = [
        # 최신 (24h 내): 정상
        _make_row(observed_at_utc=base_dt.strftime("%Y-%m-%dT%H:%M:%S"), value=20.0),
        # 25시간 전: 결측 (24h 밖 → 판정 제외)
        _make_row(observed_at_utc=(base_dt - timedelta(hours=25)).strftime("%Y-%m-%dT%H:%M:%S"),
                  value=None, missing_reason="ZERO_SENTINEL"),
    ]
    _apply_station_inactive(rows)
    assert all(not r.get("station_inactive") for r in rows)


def test_station_inactive_multiple_stations_independent():
    """관측소별 독립 판정 — DT_0049 inactive, DT_0016 정상"""
    base_dt = datetime(2026, 1, 1, 12, 0, 0)
    rows = []
    # DT_0049: 전부 결측
    for i in range(5):
        rows.append(_make_row(
            station_id="tide:DT_0049",
            observed_at_utc=(base_dt - timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%S"),
            value=None, missing_reason="ZERO_SENTINEL",
        ))
    # DT_0016: 정상
    rows.append(_make_row(
        station_id="tide:DT_0016",
        observed_at_utc=base_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        value=25.0,
    ))
    _apply_station_inactive(rows)

    dt0049_rows = [r for r in rows if r["station_id"] == "tide:DT_0049"]
    dt0016_rows = [r for r in rows if r["station_id"] == "tide:DT_0016"]
    assert all(r.get("station_inactive") is True for r in dt0049_rows)
    assert all(not r.get("station_inactive") for r in dt0016_rows)


# ── F11 — CI 게이트 밖, 로컬 수동 실행 ──────────────────────────────────────

@pytest.mark.skipif(
    not os.environ.get("IDW_OUTPUT_DIR"),
    reason="IDW_OUTPUT_DIR 미설정 — F11 로컬 수동 실행만 (CI 게이트 밖)"
)
def test_F11_station_inactive_dt0049_dt0092():
    """
    F11: DT_0049·DT_0092 전 기간 STATION_INACTIVE.
    IDW_OUTPUT_DIR=<$SRC_IDW/output> 환경변수로 실행.
    """
    import csv
    from pathlib import Path

    obs_path = Path(os.environ["IDW_OUTPUT_DIR"]) / "observations.csv"
    assert obs_path.exists(), f"F11 파일 없음: {obs_path}"

    stations_all_missing: dict[str, bool] = {}
    with obs_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sid = row.get("station_id", "")
            if sid not in ("tide:DT_0049", "tide:DT_0092"):
                continue
            if sid not in stations_all_missing:
                stations_all_missing[sid] = True
            wt = row.get("water_temp", "")
            sal = row.get("salinity", "")
            # 빈 값 또는 0.000이 아닌 값이 하나라도 있으면 False
            if wt not in ("", "0.0", "0.000") or sal not in ("", "0.0", "0.000"):
                stations_all_missing[sid] = False

    for sid in ("tide:DT_0049", "tide:DT_0092"):
        assert stations_all_missing.get(sid, True) is True, \
            f"{sid}: 0.000 아닌 관측값 있음 — STATION_INACTIVE 조건 불일치"


@pytest.mark.skipif(
    not os.environ.get("IDW_OUTPUT_DIR"),
    reason="IDW_OUTPUT_DIR 미설정 — F11 로컬 수동 실행만"
)
def test_F11_dt0061_consecutive_missing_518min():
    """
    F11: DT_0061 염분 최장 연속 결측 518분 이상.
    """
    import csv
    from pathlib import Path

    obs_path = Path(os.environ["IDW_OUTPUT_DIR"]) / "observations.csv"
    assert obs_path.exists()

    # DT_0061의 salinity=0.000 행 수집 → 연속 결측 구간 계산
    sal_times: list[str] = []
    with obs_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("station_id") != "tide:DT_0061":
                continue
            if row.get("metric") == "salinity":
                sal_times.append((row.get("observed_at_utc", ""), row.get("value")))

    sal_times.sort(key=lambda x: x[0])

    max_streak_min = 0
    streak_start: str | None = None
    streak_end: str | None = None

    for ts, val in sal_times:
        is_missing = (val is None or str(val).strip() in ("", "0.0", "0.000"))
        if is_missing:
            if streak_start is None:
                streak_start = ts
            streak_end = ts
        else:
            if streak_start and streak_end and streak_start != streak_end:
                try:
                    t0 = datetime.fromisoformat(streak_start)
                    t1 = datetime.fromisoformat(streak_end)
                    gap_min = int((t1 - t0).total_seconds() / 60)
                    max_streak_min = max(max_streak_min, gap_min)
                except ValueError:
                    pass
            streak_start = None
            streak_end = None

    assert max_streak_min >= 518, f"DT_0061 최장 연속 결측 {max_streak_min}분 < 518분"

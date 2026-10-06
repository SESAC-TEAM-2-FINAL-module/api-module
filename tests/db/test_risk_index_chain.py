"""
I-16 연결 테스트 — 실제 진입점으로 확인 (계획서 7.9절)

① grading 진입점(handle_obs_loaded·handle_interp_done)을 거쳐
   farm_readings·risk_index_factors·risk_index_levels·grade.done 생성
② evaluation 진입점(handle_grade_done)으로
   axis_status·red_tide_risk 처리 확인; 원천 상태(OUTAGE 등)를 받지 않음
③ 운영 판정 정의(전부 <미결>)로 grading → RULE_UNDECIDED, 분해·단계 없음
④ 7.4: 새 표 두 개가 DDL에 있고, 없는 DB에서 기동 시 check_schema()가 멈춤

판별력: 각 케이스마다 해당 동작을 끊은 상태로 실패를 확인한다
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml
from sqlalchemy import text

from common.queue import MemoryQueue


# ─────────────────────────────────────────────────────────────────────────────
# 공용 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

def _rows(engine, sql: str) -> list[dict]:
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(text(sql)).mappings().all()]


def _op() -> dict:
    return yaml.safe_load(
        (Path(__file__).parents[2] / "config" / "operational.initial.yaml").read_text("utf-8")
    )


def _defs_test() -> dict:
    """시험용 판정 정의 — 가중치·규칙·단계 모두 있어 지수 계산이 가능하다."""
    from common.config import load_definitions
    defs = load_definitions()
    defs["risk_index"] = {
        "weights": {
            "nearby_bulletin": 0.4,
            "water_temp_band": 0.3,
            "salinity_band": 0.15,
            "chlorophyll_level": 0.15,
        },
        "factors": {
            "nearby_bulletin": {"grade_scores": {
                "NONE": 0.0, "PRE_ADVISORY": 0.25,
                "ADVISORY": 0.5, "WARNING": 1.0,
                "NOT_GRADED": 0.0, "UNKNOWN": 0.0,
            }},
            "water_temp_band": {"bands": [
                {"min": None, "max": 20.0, "score": 0.0},
                {"min": 20.0, "max": 25.0, "score": 0.5},
                {"min": 25.0, "max": None, "score": 1.0},
            ]},
            "salinity_band": {"bands": [
                {"min": None, "max": 32.0, "score": 1.0},
                {"min": 32.0, "max": None, "score": 0.0},
            ]},
            "chlorophyll_level": {"bands": [
                {"min": None, "max": 5.0, "score": 0.0},
                {"min": 5.0, "max": None, "score": 1.0},
            ]},
        },
        "min_factors_ok": 2,
        "levels": {"entries": [
            {"min": None, "code": "VERY_LOW"},
            {"min": 0.0, "code": "VERY_LOW"},
            {"min": 0.2, "code": "LOW"},
            {"min": 0.4, "code": "MODERATE"},
            {"min": 0.6, "code": "HIGH"},
            {"min": 0.8, "code": "VERY_HIGH"},
        ]},
    }
    return defs


_FARM_ID = "farm_ri_test"
_NOW = datetime(2026, 10, 2, 0, 0, 0)


def _seed_farm_reading(repo, axis: str, value, provenance: str,
                       none_reason=None, grade=None):
    """farm_readings에 테스트용 축 값을 직접 적재한다."""
    repo.upsert_farm_readings([{
        "farm_id": _FARM_ID,
        "axis": axis,
        "value": value,
        "lower": None,
        "upper": None,
        "unit": None,
        "derivation": "COMPUTED" if axis == "red_tide_risk" else "MEASURED",
        "provenance": provenance,
        "none_reason": none_reason,
        "validated_scope": None,
        "grade": grade,
        "alertable": False if axis == "red_tide_risk" else (provenance not in ("NONE", None)),
        "source_ref": None,
        "distance_km": None,
        "observed_at_utc": _NOW,
        "computed_at_utc": _NOW,
    }])


# ─────────────────────────────────────────────────────────────────────────────
# 픽스처
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def farm_sites(schema_engine, clean_db):
    """farm_sites 테이블을 만들고 테스트 양식장 한 곳을 넣는다."""
    with schema_engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS farm_sites ("
            "farm_id VARCHAR(64) PRIMARY KEY, lat DOUBLE PRECISION, "
            "lng DOUBLE PRECISION, active BOOLEAN, updated_at_utc TIMESTAMP, area_id VARCHAR(64))"
        ))
        conn.execute(text(
            "INSERT INTO farm_sites VALUES (:fid, 34.68, 127.69, TRUE, '2026-07-01 00:00:00', NULL) "
            "ON CONFLICT DO NOTHING"
        ), {"fid": _FARM_ID})
    yield _FARM_ID
    with schema_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS farm_sites"))


# ─────────────────────────────────────────────────────────────────────────────
# ① handle_obs_loaded → 세 표 + grade.done
# ─────────────────────────────────────────────────────────────────────────────

class TestConnection1ObsLoaded:
    """① handle_obs_loaded를 실제 진입점으로 실행 — 세 표·grade.done 확인."""

    def _obs_payload(self) -> dict:
        return {
            "schema": "queue-v2",
            "topic": "obs.loaded",
            "load_id": "L1",
            "api": "dtRecent",
            "source": "tide",
            "station_ids": [],
            "observed_from_utc": "2026-10-02T00:00:00",
            "observed_to_utc": "2026-10-02T00:00:00",
            "row_count": 0,
        }

    def test_farm_reading_red_tide_risk_created(self, schema_engine, repo, farm_sites):
        """handle_obs_loaded 후 farm_readings에 red_tide_risk 행이 생긴다."""
        import grading.main as gr
        q = MemoryQueue()
        gr.handle_obs_loaded(self._obs_payload(), repo, q, _defs_test())
        rows = _rows(schema_engine,
                     f"SELECT * FROM farm_readings WHERE farm_id = '{_FARM_ID}' AND axis = 'red_tide_risk'")
        assert len(rows) == 1
        assert rows[0]["derivation"] == "COMPUTED"
        assert rows[0]["alertable"] is False

    def test_grade_done_published_for_red_tide_risk(self, schema_engine, repo, farm_sites):
        """handle_obs_loaded가 grade.done(axis=red_tide_risk)을 발행한다."""
        import grading.main as gr
        q = MemoryQueue()
        gr.handle_obs_loaded(self._obs_payload(), repo, q, _defs_test())
        ri_msgs = [m for m in q.drain("grade.done") if m.payload["axis"] == "red_tide_risk"]
        assert len(ri_msgs) == 1
        assert _FARM_ID in ri_msgs[0].payload["farm_ids"]

    def test_risk_index_factors_written_with_test_defs(self, schema_engine, repo, farm_sites):
        """시험용 판정 정의로 돌리면 risk_index_factors 4행이 생긴다."""
        import grading.main as gr
        q = MemoryQueue()
        gr.handle_obs_loaded(self._obs_payload(), repo, q, _defs_test())
        factors = _rows(schema_engine,
                        f"SELECT * FROM risk_index_factors WHERE farm_id = '{_FARM_ID}'")
        assert len(factors) == 4

    def test_risk_index_factors_not_written_with_pending_defs(self, schema_engine, repo, farm_sites):
        """판별력: 운영 정의(가중치 전부 <미결>)로 돌리면 factors 행이 없다."""
        import grading.main as gr
        from common.config import load_definitions
        q = MemoryQueue()
        gr.handle_obs_loaded(self._obs_payload(), repo, q, load_definitions())
        factors = _rows(schema_engine,
                        f"SELECT * FROM risk_index_factors WHERE farm_id = '{_FARM_ID}'")
        assert len(factors) == 0  # <미결> → ① 경우, factors 없음

    def test_with_preseeded_inputs_computes_non_trivial_index(
            self, schema_engine, repo, farm_sites):
        """입력 축 값을 미리 적재해 두면 OK 인자가 생겨 의미있는 지수를 낸다."""
        import grading.main as gr
        # 입력 축 farm_readings 미리 적재 (red_tide·water_temp·salinity)
        _seed_farm_reading(repo, "red_tide", None, "OFFICIAL")        # grade=None → score 0
        _seed_farm_reading(repo, "water_temp", 26.0, "INTERPOLATED")  # score 1.0 → contrib 0.3
        _seed_farm_reading(repo, "salinity", 31.0, "NEAREST")         # score 1.0 → contrib 0.15

        q = MemoryQueue()
        gr.handle_obs_loaded(self._obs_payload(), repo, q, _defs_test())

        ri_rows = _rows(schema_engine,
                        f"SELECT * FROM farm_readings WHERE farm_id = '{_FARM_ID}' AND axis = 'red_tide_risk'")
        assert len(ri_rows) == 1
        # water_temp(0.3) + salinity(0.15) = 2 OK 인자 → provenance=INTERPOLATED
        assert ri_rows[0]["provenance"] == "INTERPOLATED"
        assert ri_rows[0]["value"] is not None

        factors = _rows(schema_engine,
                        f"SELECT * FROM risk_index_factors WHERE farm_id = '{_FARM_ID}'")
        assert len(factors) == 4
        ok_factors = [f for f in factors if f["ok"]]
        # nearby_bulletin(red_tide OFFICIAL grade=None→score 0) + water_temp + salinity = 3
        assert len(ok_factors) >= 2

        level_rows = _rows(schema_engine,
                           f"SELECT * FROM risk_index_levels WHERE farm_id = '{_FARM_ID}'")
        assert len(level_rows) == 1
        assert level_rows[0]["level"] in ("VERY_LOW", "LOW", "MODERATE", "HIGH", "VERY_HIGH")

    def test_discriminability_no_factor_rows_when_weight_missing(
            self, schema_engine, repo, farm_sites):
        """판별력: 가중치 하나라도 <미결>이면 factor 행이 없다 (경우 ①)."""
        import grading.main as gr
        defs = _defs_test()
        defs["risk_index"]["weights"]["nearby_bulletin"] = None  # 하나를 <미결>로
        q = MemoryQueue()
        gr.handle_obs_loaded(self._obs_payload(), repo, q, defs)
        factors = _rows(schema_engine,
                        f"SELECT * FROM risk_index_factors WHERE farm_id = '{_FARM_ID}'")
        assert len(factors) == 0


# ─────────────────────────────────────────────────────────────────────────────
# K4 — obs.loaded 순서가 달라도 최종 결과가 같다 (upsert 멱등성)
# ─────────────────────────────────────────────────────────────────────────────

class TestK4ObsOrder:
    """K4: 같은 obs.loaded를 두 번 실행해도 farm_readings는 한 행뿐이다."""

    def test_idempotent_second_run(self, schema_engine, repo, farm_sites):
        import grading.main as gr
        defs = _defs_test()
        payload = {
            "schema": "queue-v2", "topic": "obs.loaded", "load_id": "L1",
            "api": "dtRecent", "source": "tide", "station_ids": [],
            "observed_from_utc": "2026-10-02T00:00:00",
            "observed_to_utc": "2026-10-02T00:00:00", "row_count": 0,
        }
        q = MemoryQueue()
        gr.handle_obs_loaded(payload, repo, q, defs)
        gr.handle_obs_loaded(payload, repo, q, defs)
        rows = _rows(schema_engine,
                     f"SELECT * FROM farm_readings WHERE farm_id = '{_FARM_ID}' AND axis = 'red_tide_risk'")
        assert len(rows) == 1  # upsert → 중복 없음


# ─────────────────────────────────────────────────────────────────────────────
# ① handle_interp_done → red_tide_risk grade.done
# ─────────────────────────────────────────────────────────────────────────────

class TestConnection1InterpDone:
    """handle_interp_done도 red_tide_risk grade.done을 발행해야 한다."""

    def test_interp_done_publishes_risk_grade_done(self, schema_engine, repo, farm_sites):
        import grading.main as gr
        defs = _defs_test()
        run_id = "ri_test_run"
        ref = datetime(2026, 10, 2, 0, 0, 0)

        repo.upsert_stations([{
            "id": "tide:DT_0014", "source_api": "tide",
            "name": "통영", "lat": 34.87, "lng": 128.43,
            "sea_area": None, "active": True,
        }])
        repo.upsert_observations([{
            "station_id": "tide:DT_0014", "observed_at_utc": ref,
            "metric": "water_temp", "value": 22.0,
            "missing_reason": None, "flags": None, "raw_id": None,
        }])
        repo.upsert_interpolation_runs([{
            "run_id": run_id, "load_id": "L1", "metric": "water_temp",
            "method": "IDW", "power_p": 2.0, "n_neighbors": 5,
            "ref_time_utc": ref, "station_set_key": "test_key",
            "error_p95": 0.5, "error_window_days": 30, "computed_at_utc": ref,
        }])
        repo.upsert_interpolation_weights([{
            "run_id": run_id, "farm_id": _FARM_ID,
            "station_id": "tide:DT_0014", "distance_km": 5.0, "weight": 1.0,
        }])

        q = MemoryQueue()
        gr.handle_interp_done({
            "schema": "queue-v2", "topic": "interp.done",
            "run_id": run_id, "error_p95": 0.5, "stations_used": 1,
        }, repo, q, defs)

        ri_msgs = [m for m in q.drain("grade.done") if m.payload["axis"] == "red_tide_risk"]
        assert len(ri_msgs) == 1, "interp.done도 red_tide_risk grade.done을 발행해야 한다"
        assert _FARM_ID in ri_msgs[0].payload["farm_ids"]

        # 지수는 같은 트랜잭션에서 방금 쓴 수온으로 계산된다 — 이전 값(빈 DB면 입력 없음)이 아니다 (4.10절)
        wt = _rows(schema_engine,
                   f"SELECT value FROM farm_readings WHERE farm_id = '{_FARM_ID}' AND axis = 'water_temp'")
        f = _rows(schema_engine,
                  f"SELECT * FROM risk_index_factors WHERE farm_id = '{_FARM_ID}' AND factor = 'water_temp_band'")
        assert len(wt) == 1 and len(f) == 1
        assert f[0]["excluded_reason"] != "NO_INPUT", "지수가 갱신 전 입력으로 계산됐다"
        assert f[0]["input_value"] == pytest.approx(wt[0]["value"])


# ─────────────────────────────────────────────────────────────────────────────
# ② evaluation handle_grade_done — red_tide_risk axis_status
# ─────────────────────────────────────────────────────────────────────────────

class TestConnection2EvaluationGradeDone:
    """② handle_grade_done이 red_tide_risk를 올바른 상태로 판정한다."""

    def _grade_done_payload(self) -> dict:
        return {
            "schema": "queue-v2", "topic": "grade.done",
            "grade_run_id": "G1", "axis": "red_tide_risk",
            "farm_ids": [_FARM_ID],
        }

    def test_interpolated_gives_normal(self, schema_engine, repo, farm_sites):
        """provenance=INTERPOLATED → NORMAL."""
        import evaluation.main as ev
        _seed_farm_reading(repo, "red_tide_risk", 0.3, "INTERPOLATED")
        q = MemoryQueue()
        ev.handle_grade_done(self._grade_done_payload(), repo, q, _op())
        rows = _rows(schema_engine,
                     f"SELECT * FROM axis_status WHERE farm_id = '{_FARM_ID}' AND axis = 'red_tide_risk'")
        assert len(rows) == 1
        assert rows[0]["state"] == "NORMAL"

    def test_provenance_none_gives_not_usable(self, schema_engine, repo, farm_sites):
        """provenance=NONE → NOT_USABLE(reason=none_reason)."""
        import evaluation.main as ev
        _seed_farm_reading(repo, "red_tide_risk", None, "NONE", none_reason="RULE_UNDECIDED")
        q = MemoryQueue()
        ev.handle_grade_done(self._grade_done_payload(), repo, q, _op())
        rows = _rows(schema_engine,
                     f"SELECT * FROM axis_status WHERE farm_id = '{_FARM_ID}' AND axis = 'red_tide_risk'")
        assert rows[0]["state"] == "NOT_USABLE"
        assert rows[0]["reason"] == "RULE_UNDECIDED"

    def test_no_reading_writes_no_state(self, schema_engine, repo, farm_sites):
        """지수 행 없음 → 판정할 값이 없어 상태를 쓰지 않는다 — 이 축은 NOT_USABLE·GRADING_STALE·NORMAL만 쓴다 (4.10절)"""
        import evaluation.main as ev
        q = MemoryQueue()
        ev.handle_grade_done(self._grade_done_payload(), repo, q, _op())
        rows = _rows(schema_engine,
                     f"SELECT * FROM axis_status WHERE farm_id = '{_FARM_ID}' AND axis = 'red_tide_risk'")
        assert rows == []

    def test_does_not_get_outage_from_adapter_health(self, schema_engine, repo, farm_sites):
        """② 이 축이 원천 상태(OUTAGE)를 받지 않는다 — adapter_health 연속 실패 무관."""
        import evaluation.main as ev
        repo.upsert_adapter_health([{
            "adapter": "red_tide",
            "last_success_utc": None,
            "last_failure_utc": datetime(2026, 10, 2, 0, 0, 0),
            "consecutive_failures": 99,
            "retry_recovered": 0,
        }])
        _seed_farm_reading(repo, "red_tide_risk", 0.3, "INTERPOLATED")
        q = MemoryQueue()
        ev.handle_grade_done(self._grade_done_payload(), repo, q, _op())
        rows = _rows(schema_engine,
                     f"SELECT * FROM axis_status WHERE farm_id = '{_FARM_ID}' AND axis = 'red_tide_risk'")
        assert rows[0]["state"] == "NORMAL", "OUTAGE 어댑터 실패가 red_tide_risk에 전파되면 안 된다"

    def test_discriminability_none_provenance_is_not_normal(self, schema_engine, repo, farm_sites):
        """판별력: provenance=NONE이면 NORMAL이 아니다."""
        import evaluation.main as ev
        _seed_farm_reading(repo, "red_tide_risk", None, "NONE", none_reason="INSUFFICIENT_FACTORS")
        q = MemoryQueue()
        ev.handle_grade_done(self._grade_done_payload(), repo, q, _op())
        rows = _rows(schema_engine,
                     f"SELECT * FROM axis_status WHERE farm_id = '{_FARM_ID}' AND axis = 'red_tide_risk'")
        assert rows[0]["state"] != "NORMAL"


# ─────────────────────────────────────────────────────────────────────────────
# ③ 운영 판정 정의(전부 <미결>)로 RULE_UNDECIDED, 분해·단계 없음
# ─────────────────────────────────────────────────────────────────────────────

class TestConnection3PendingDefs:
    """③ 운영 정의(전부 <미결>)로 grading → RULE_UNDECIDED, 분해·단계 없음."""

    def test_pending_defs_gives_rule_undecided_no_factors_no_levels(
            self, schema_engine, repo, farm_sites):
        import grading.main as gr
        from common.config import load_definitions
        q = MemoryQueue()
        gr.handle_obs_loaded({
            "schema": "queue-v2", "topic": "obs.loaded", "load_id": "L1",
            "api": "dtRecent", "source": "tide", "station_ids": [],
            "observed_from_utc": "2026-10-02T00:00:00",
            "observed_to_utc": "2026-10-02T00:00:00", "row_count": 0,
        }, repo, q, load_definitions())

        ri_rows = _rows(schema_engine,
                        f"SELECT * FROM farm_readings WHERE farm_id = '{_FARM_ID}' AND axis = 'red_tide_risk'")
        assert len(ri_rows) == 1
        assert ri_rows[0]["provenance"] == "NONE"
        assert ri_rows[0]["none_reason"] == "RULE_UNDECIDED"

        factor_rows = _rows(schema_engine,
                            f"SELECT * FROM risk_index_factors WHERE farm_id = '{_FARM_ID}'")
        assert len(factor_rows) == 0, "가중치 <미결>이면 분해 행이 없어야 한다"

        level_rows = _rows(schema_engine,
                           f"SELECT * FROM risk_index_levels WHERE farm_id = '{_FARM_ID}'")
        assert len(level_rows) == 0, "단계 행도 없어야 한다"

    def test_pending_weights_detected_correctly(self):
        """판별력: 운영 정의의 가중치가 실제로 <미결>인지 확인한다."""
        from grading import _risk_index as ri_mod
        from common.config import load_definitions
        defs = load_definitions()
        ri_cfg = defs.get("risk_index") or {}
        weights = {f: ri_mod._get_weight(ri_cfg, f) for f in ri_mod.FACTOR_ORDER}
        assert all(w is None for w in weights.values()), \
            "운영 정의 risk_index.weights가 <미결>이 아니다 — 정의를 확인하라"


# ─────────────────────────────────────────────────────────────────────────────
# 7.4 — 새 표 두 개가 DDL에 있고, 없는 DB에서 check_schema()가 멈춤
# ─────────────────────────────────────────────────────────────────────────────

class TestSchema74:
    def test_risk_index_tables_in_pg_ddl(self):
        """schema_pg.sql에 risk_index_factors·risk_index_levels가 있다."""
        ddl = (Path(__file__).parents[2] / "contracts" / "tables" / "schema_pg.sql").read_text("utf-8", errors="replace")
        assert "risk_index_factors" in ddl, "schema_pg.sql에 risk_index_factors가 없다"
        assert "risk_index_levels" in ddl, "schema_pg.sql에 risk_index_levels가 없다"

    def test_risk_index_tables_in_my_ddl(self):
        """schema_my.sql에도 두 표가 있다."""
        ddl = (Path(__file__).parents[2] / "contracts" / "tables" / "schema_my.sql").read_text("utf-8", errors="replace")
        assert "risk_index_factors" in ddl, "schema_my.sql에 risk_index_factors가 없다"
        assert "risk_index_levels" in ddl, "schema_my.sql에 risk_index_levels가 없다"

    def test_risk_index_tables_created_by_metadata(self, schema_engine):
        """schema_engine(create_all 적용)에 두 표가 실제로 있다."""
        from sqlalchemy import inspect
        insp = inspect(schema_engine)
        tables = set(insp.get_table_names())
        assert "risk_index_factors" in tables
        assert "risk_index_levels" in tables

    def test_schema_check_fails_without_risk_tables(self, pg_engine):
        """risk_index_factors·levels 없는 DB에서 check_schema() → SystemExit."""
        from sqlalchemy import create_engine
        from sqlalchemy import text as _text
        from common.repository import tables as t
        from common.repository.sql import SqlRepository

        schema_name = "test_no_risk_7_4"
        with pg_engine.begin() as conn:
            conn.execute(_text(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE"))
            conn.execute(_text(f"CREATE SCHEMA {schema_name}"))

        # connect_args로 search_path 설정 — URL 문자열 조작을 피한다
        engine2 = create_engine(
            pg_engine.url,
            connect_args={"options": f"-csearch_path={schema_name}"},
            pool_pre_ping=True,
        )
        try:
            for name, tbl in t.metadata.tables.items():
                if name in ("risk_index_factors", "risk_index_levels"):
                    continue
                try:
                    tbl.create(engine2, checkfirst=True)
                except Exception:
                    pass
            repo2 = SqlRepository(engine2)
            with pytest.raises(SystemExit):
                repo2.check_schema()
        finally:
            with pg_engine.begin() as conn:
                conn.execute(_text(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE"))
            engine2.dispose()

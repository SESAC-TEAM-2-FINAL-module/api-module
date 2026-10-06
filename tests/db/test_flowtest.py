"""
flowtest 통과 기준 FT2~FT5 — 실제 DB (testcontainer, 계획서 7.10절, 개정 21)
FT1·FT6 는 tests/unit/test_flowtest_unit.py (DB 없는 단위 테스트)

FT2: 실제 DB + fake HTTP — once 모드 전 파이프라인. farm_readings·axis_status·raw_index·ingest_runs 적재,
     water_temp COMPUTED·alertable=False 확인. 구별: 구독 하나 제거 시 실패.
FT3: 실행 전 점검 6가지 실패 조건. 각 조건: DB 행 0 (ops_events 포함), HTTP 0, 비정상 종료.
     구별: 점검 하나 비활성화 시 실패.
FT4: FT2 원문을 새 DB에 replay → HTTP 0, 동일 값(value·provenance·state).
FT5: 핸들러 하나 예외 → 다른 소스는 완료, 요약의 실패 수 > 0.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from sqlalchemy import text

from common.queue import MemoryQueue, Message
from common.contract_check import QUEUE_CONTRACT


# ─ 공용 픽스처 ────────────────────────────────────────────────────────────────

OPERATIONAL = yaml.safe_load(
    (Path(__file__).parents[2] / "config" / "operational.initial.yaml").read_text("utf-8")
)


def _rows(engine, sql: str) -> list[dict]:
    with engine.connect() as c:
        return [dict(r) for r in c.execute(text(sql)).mappings()]


@pytest.fixture()
def ft_farm_sites(schema_engine):
    """webservice 소유 farm_sites — 테스트 컨테이너에만 합성 (1.6·2.0.3절)."""
    with schema_engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS farm_sites "
            "(farm_id VARCHAR(64) PRIMARY KEY, lat DOUBLE PRECISION, "
            "lng DOUBLE PRECISION, active BOOLEAN, updated_at_utc TIMESTAMP)"
        ))
        conn.execute(text(
            "INSERT INTO farm_sites VALUES "
            "('syn_gam_001', 34.68, 127.69, TRUE, '2026-07-01 00:00:00') "
            "ON CONFLICT DO NOTHING"
        ))
    yield
    with schema_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS farm_sites"))


def _inject_tide_and_publish(raw_store, q, tide) -> str:
    """합성 dtRecent 원문을 raw_store 에 저장하고 raw.fetched 발행 → 체인 시작."""
    obs = [
        (code, "2026-08-01 09:00:00", 24.0 + i * 0.3)
        for i, code in enumerate(tide.STATIONS)
    ]
    raw_key = raw_store.put("dtRecent", "all", tide.raw(tide.body(obs)))
    q.publish(Message(
        topic="raw.fetched",
        payload={
            "schema": QUEUE_CONTRACT,
            "topic": "raw.fetched",
            "raw_id": raw_key,
            "api": "dtRecent",
            "tag": "all",
            "fetched_at_utc": "2026-08-01T00:10:00",
        },
    ))
    return raw_key


# ─ FT2: once 모드 전 파이프라인 (fake HTTP) ────────────────────────────────────

class TestFT2EndToEnd:
    """FT2: 실제 DB + fake HTTP — once 모드 전 파이프라인 (7.10절)."""

    def test_once_end_to_end_populates_db(
        self, processor_up, raw_store, schema_engine, tide, ft_farm_sites, clean_db_class
    ):
        """
        fake HTTP(raw_store 주입) → processor → interpolation → grading → evaluation.
        farm_readings·axis_status·raw_index·ingest_runs 적재.
        water_temp: derivation=COMPUTED, alertable=False (N11).
        """
        import interpolation.main as ip
        import grading.main as gr
        import evaluation.main as ev
        from flowtest.main import _bind_handler, _wrap, _Stats, _do_interpolation_error, _do_evaluation_sweep
        from common.config import load_definitions

        pm, repo = processor_up
        defs = load_definitions()
        stats = _Stats()
        q = MemoryQueue()

        # flowtest._setup_pipeline 방식으로 구독 연결 (pm.startup 은 processor_up 이 이미 호출)
        q.subscribe("raw.fetched", _wrap("processor", "raw.fetched",
            _bind_handler(pm.handle_raw_fetched, q), stats))
        q.subscribe("obs.loaded", _wrap("interpolation", "obs.loaded",
            _bind_handler(ip.handle_obs_loaded, repo, q, defs), stats))
        q.subscribe("obs.loaded", _wrap("grading", "obs.loaded",
            _bind_handler(gr.handle_obs_loaded, repo, q, defs), stats))
        q.subscribe("interp.done", _wrap("grading", "interp.done",
            _bind_handler(gr.handle_interp_done, repo, q, defs), stats))
        q.subscribe("grade.done", _wrap("evaluation", "grade.done",
            _bind_handler(ev.handle_grade_done, repo, q, OPERATIONAL), stats))

        # fake HTTP: raw_store 에 합성 원문 주입 → raw.fetched 발행
        raw_key = _inject_tide_and_publish(raw_store, q, tide)

        # 후처리 워크로드
        _do_interpolation_error(repo, defs, stats)
        _do_evaluation_sweep(repo, OPERATIONAL, stats)

        # ─ 검증 ────────────────────────────────────────────────────────────────
        # raw_index · ingest_runs
        assert _rows(schema_engine, "SELECT * FROM raw_index WHERE api = 'dtRecent'")
        assert _rows(schema_engine, "SELECT * FROM ingest_runs")

        # farm_readings: water_temp COMPUTED, alertable=False (N11)
        wt = _rows(schema_engine,
            "SELECT * FROM farm_readings "
            "WHERE farm_id = 'syn_gam_001' AND axis = 'water_temp'")
        assert wt, "farm_readings에 water_temp 행 있어야 함"
        assert wt[0]["derivation"] == "COMPUTED"
        assert wt[0]["alertable"] is False

        # axis_status
        assert _rows(schema_engine,
            "SELECT * FROM axis_status WHERE farm_id = 'syn_gam_001'")

        # 단계 실패 없음
        assert not stats.failures

    def test_missing_subscription_breaks_chain(
        self, processor_up, raw_store, schema_engine, tide, ft_farm_sites, clean_db_class
    ):
        """
        구별: grade.done 구독을 제거하면 evaluation 이 돌지 않아
        axis_status 에 행이 생기지 않는다.
        """
        import interpolation.main as ip
        import grading.main as gr
        from flowtest.main import _bind_handler, _wrap, _Stats
        from common.config import load_definitions

        pm, repo = processor_up
        defs = load_definitions()
        stats = _Stats()
        q = MemoryQueue()

        # grade.done 구독을 의도적으로 빠뜨린다
        q.subscribe("raw.fetched", _wrap("processor", "raw.fetched",
            _bind_handler(pm.handle_raw_fetched, q), stats))
        q.subscribe("obs.loaded", _wrap("interpolation", "obs.loaded",
            _bind_handler(ip.handle_obs_loaded, repo, q, defs), stats))
        q.subscribe("obs.loaded", _wrap("grading", "obs.loaded",
            _bind_handler(gr.handle_obs_loaded, repo, q, defs), stats))
        q.subscribe("interp.done", _wrap("grading", "interp.done",
            _bind_handler(gr.handle_interp_done, repo, q, defs), stats))
        # ← grade.done 구독 없음

        _inject_tide_and_publish(raw_store, q, tide)

        # axis_status 행이 없어야 한다 (evaluation 이 돌지 않음)
        assert not _rows(schema_engine,
            "SELECT * FROM axis_status WHERE farm_id = 'syn_gam_001'"), (
            "grade.done 구독이 없으면 axis_status 에 행이 생기지 않아야 한다"
        )


# ─ FT3: 실행 전 점검 6가지 실패 조건 — 진입점(flowtest.main.main)으로 ───────────

_REPO = Path(__file__).parents[2]
_COLLECT_ENV = ["DTRECENT_URL", "DTRECENT_KEY", "NIFS_URL",
                "NIFS_KEY_BULLETIN", "NIFS_KEY_LINE", "NIFS_KEY_FISHERY_SEA"]


def _table_counts(engine) -> dict[str, int]:
    from common.repository.tables import metadata
    with engine.connect() as c:
        return {t.name: c.execute(text(f"SELECT COUNT(*) FROM {t.name}")).scalar()
                for t in metadata.sorted_tables
                if engine.dialect.has_table(c, t.name)}


@pytest.fixture()
def ft3_env(schema_engine, clean_db, tmp_path, monkeypatch):
    """정상 상태 — 모듈 스키마 + 해역 시드 + farm_sites 활성 1건 + 운영 조정 파일 + 더미 수집 변수.
    각 경우는 이 상태에서 하나만 깨뜨린다. HTTP 송신은 세어서 막는다."""
    import httpx
    with schema_engine.begin() as c:
        c.exec_driver_sql((_REPO / "contracts/tables/seeds_pg.sql").read_text(encoding="utf-8"))
        c.execute(text("CREATE TABLE IF NOT EXISTS farm_sites (farm_id VARCHAR(64) PRIMARY KEY, "
                       "lat DOUBLE PRECISION, lng DOUBLE PRECISION, active BOOLEAN, updated_at_utc TIMESTAMP)"))
        c.execute(text("INSERT INTO farm_sites VALUES ('syn_gam_001', 34.68, 127.69, TRUE, '2026-07-01 00:00:00')"))
    monkeypatch.setenv("DATABASE_URL", schema_engine.url.render_as_string(hide_password=False))
    monkeypatch.setenv("OPERATIONAL_CONFIG_PATH", str(_REPO / "config/operational.initial.yaml"))
    monkeypatch.setenv("RAW_STORE_PATH", str(tmp_path / "raw"))
    for v in _COLLECT_ENV:
        monkeypatch.setenv(v, "dummy-ft3")
    calls = []

    def _no_send(self, request, *a, **k):
        calls.append(str(request.url.host))
        raise httpx.ConnectError("FT3 — 실행 전 점검 실패 경우에는 송신하면 안 된다")
    monkeypatch.setattr(httpx.Client, "send", _no_send)
    yield calls
    from common.repository.tables import metadata
    with schema_engine.begin() as c:
        c.execute(text("DROP TABLE IF EXISTS farm_sites"))
    metadata.create_all(schema_engine)       # ① 경우에서 지운 표를 되돌린다


def _break(case: str, engine, monkeypatch) -> None:
    with engine.begin() as c:
        if case == "missing_table":
            c.execute(text("DROP TABLE farm_areas"))
        elif case == "empty_seed":
            c.execute(text("DELETE FROM axis_coverage"))
            c.execute(text("DELETE FROM area_aliases"))
            c.execute(text("DELETE FROM areas"))
        elif case == "no_farm_sites":
            c.execute(text("DROP TABLE farm_sites"))
        elif case == "zero_active_farm":
            c.execute(text("UPDATE farm_sites SET active = FALSE"))
    if case == "no_operational":
        monkeypatch.setenv("OPERATIONAL_CONFIG_PATH", "/nonexistent/operational.yaml")
    elif case == "missing_key_var":
        monkeypatch.delenv("DTRECENT_KEY")


_EXPECT = {
    "missing_table": "스키마 불일치", "empty_seed": "해역 시드 표가 비었다",
    "no_operational": "운영 조정 파일 없음", "no_farm_sites": "farm_sites 표 없음",
    "zero_active_farm": "활성 행", "missing_key_var": "DTRECENT_KEY",
}


class TestFT3Preflight:
    """FT3: 한 가지씩 깨뜨리고 진입점을 collect·once로 돌린다 → 0이 아닌 종료,
    어느 표에도 행이 늘지 않음(ops_events 포함), HTTP 송신 0건 (7.10절)."""

    @pytest.mark.parametrize("case", ["missing_table", "empty_seed", "no_operational",
                                      "no_farm_sites", "zero_active_farm", "missing_key_var"])
    def test_preflight_failure_writes_nothing(self, case, schema_engine, ft3_env, monkeypatch):
        import flowtest.main as ft
        _break(case, schema_engine, monkeypatch)
        before = _table_counts(schema_engine)
        with pytest.raises(SystemExit) as ei:
            ft.main(["--mode", "collect", "--run", "once"])
        assert ei.value.code not in (0, None)
        assert _EXPECT[case] in str(ei.value.code), f"{case}: 다른 점검에서 멈췄다 — {ei.value.code}"
        assert _table_counts(schema_engine) == before, f"{case}: 점검 실패인데 행이 늘었다"
        assert ft3_env == [], f"{case}: 점검 실패인데 HTTP 송신이 있었다"

    def test_discrimination_healthy_state_passes_and_writes(self, schema_engine, ft3_env):
        """판별력 — 깨뜨리지 않은 상태에서는 점검을 통과하고 기동 기록(ops_events)을 쓴다.
        (replay·빈 원문 저장소로 돌려 HTTP는 0건) — 위 검사의 '행 없음'이 우연이 아님을 보인다"""
        import flowtest.main as ft
        before = _table_counts(schema_engine)
        ft.main(["--mode", "replay", "--run", "once", "--replay-api", "dtRecent", "--replay-date", "2026/10/06"])
        after = _table_counts(schema_engine)
        assert after["ops_events"] > before["ops_events"]
        assert ft3_env == []


# ─ FT4: replay 모드 — 동일 값 검증 ──────────────────────────────────────────

class TestFT4Replay:
    """FT4: FT2 원문을 새 DB 에 replay → HTTP 0, 동일 value·provenance·state (7.10절)."""

    def _run_chain_with_key(self, raw_key, pm, repo, q, defs):
        """raw.fetched 발행 → 체인 실행 헬퍼."""
        import interpolation.main as ip
        import grading.main as gr
        import evaluation.main as ev
        from flowtest.main import _bind_handler, _wrap, _Stats

        stats = _Stats()
        q.subscribe("raw.fetched", _wrap("processor", "raw.fetched",
            _bind_handler(pm.handle_raw_fetched, q), stats))
        q.subscribe("obs.loaded", _wrap("interpolation", "obs.loaded",
            _bind_handler(ip.handle_obs_loaded, repo, q, defs), stats))
        q.subscribe("obs.loaded", _wrap("grading", "obs.loaded",
            _bind_handler(gr.handle_obs_loaded, repo, q, defs), stats))
        q.subscribe("interp.done", _wrap("grading", "interp.done",
            _bind_handler(gr.handle_interp_done, repo, q, defs), stats))
        q.subscribe("grade.done", _wrap("evaluation", "grade.done",
            _bind_handler(ev.handle_grade_done, repo, q, OPERATIONAL), stats))

        q.publish(Message(
            topic="raw.fetched",
            payload={
                "schema": QUEUE_CONTRACT,
                "topic": "raw.fetched",
                "raw_id": raw_key,
                "api": "dtRecent",
                "tag": "all",
                "fetched_at_utc": "2026-08-01T00:10:00",
            },
        ))
        return stats

    def test_replay_into_wiped_db_reproduces_results(
        self, processor_up, raw_store, schema_engine, tide, ft_farm_sites, clean_db, monkeypatch
    ):
        """1차 체인 → 결과 저장 → 모듈 표를 비운 DB(새 DB와 같음)에 _do_replay(키 접두 경로) →
        단계 시각 함수를 고정한 채 value·provenance·state가 같다(산출 시각 제외), HTTP 0"""
        from datetime import datetime
        import httpx
        import processor.main as pm_mod
        import interpolation.main as ip
        import grading.main as gr
        import evaluation.main as ev
        from common.config import load_definitions
        from common.repository.tables import metadata
        from flowtest.main import _do_replay, _Stats

        fixed = datetime(2026, 8, 1, 0, 30, 0)
        for mod, name in [(pm_mod, "_now_utc"), (ip, "_utcnow"), (gr, "_utcnow"), (ev, "_now_utc")]:
            monkeypatch.setattr(mod, name, lambda: fixed)
        sent = []
        monkeypatch.setattr(httpx.Client, "send", lambda self, req, *a, **k: sent.append(req) or (_ for _ in ()).throw(RuntimeError("no http")))

        pm, repo = processor_up
        defs = load_definitions()
        obs = [(code, "2026-08-01 09:00:00", 24.0 + i * 0.3) for i, code in enumerate(tide.STATIONS)]
        raw_key = raw_store.put("dtRecent", "all", tide.raw(tide.body(obs)))
        self._run_chain_with_key(raw_key, pm, repo, MemoryQueue(), defs)

        q_sql = ("SELECT r.axis, r.value, r.provenance, s.state FROM farm_readings r "
                 "LEFT JOIN axis_status s ON s.farm_id = r.farm_id AND s.axis = r.axis "
                 "WHERE r.farm_id = 'syn_gam_001' ORDER BY r.axis")
        obs_sql = "SELECT station_id, observed_at_utc, metric, value FROM observations ORDER BY 1,2,3"
        first, first_obs = _rows(schema_engine, q_sql), _rows(schema_engine, obs_sql)
        assert any(r["axis"] == "water_temp" and r["value"] is not None for r in first)

        with schema_engine.begin() as c:                       # 새 DB와 같게 — 모듈 표를 전부 비운다
            for t in reversed(metadata.sorted_tables):
                c.execute(t.delete())
        pm.startup(definitions=defs, operational=OPERATIONAL, repo=repo)

        q = MemoryQueue()
        from flowtest.main import _bind_handler, _wrap
        st = _Stats()
        q.subscribe("raw.fetched", _wrap("processor", "raw.fetched", _bind_handler(pm.handle_raw_fetched, q), st))
        q.subscribe("obs.loaded", _wrap("interpolation", "obs.loaded", _bind_handler(ip.handle_obs_loaded, repo, q, defs), st))
        q.subscribe("obs.loaded", _wrap("grading", "obs.loaded", _bind_handler(gr.handle_obs_loaded, repo, q, defs), st))
        q.subscribe("interp.done", _wrap("grading", "interp.done", _bind_handler(gr.handle_interp_done, repo, q, defs), st))
        q.subscribe("grade.done", _wrap("evaluation", "grade.done", _bind_handler(ev.handle_grade_done, repo, q, OPERATIONAL), st))
        _do_replay("dtRecent", "2026/09/20", q, st)

        assert not st.failures
        assert _rows(schema_engine, obs_sql) == first_obs
        assert _rows(schema_engine, q_sql) == first
        assert sent == []

    def test_replay_http_call_count_is_zero(
        self, processor_up, raw_store, schema_engine, tide, ft_farm_sites, clean_db
    ):
        """replay 는 HTTP 호출 없이 실행된다 (_do_replay 가 common.http.fetch 를 호출하지 않음)."""
        from common.config import load_definitions
        from flowtest.main import _do_replay, _Stats

        pm, repo = processor_up
        defs = load_definitions()
        obs = [
            (code, "2026-08-01 09:00:00", 24.0 + i * 0.3)
            for i, code in enumerate(tide.STATIONS)
        ]
        raw_store.put("dtRecent", "all", tide.raw(tide.body(obs)))

        with patch("common.http._client.fetch") as mock_fetch:
            stats = _Stats()
            q = MemoryQueue()
            _do_replay("dtRecent", "2026/09/20", q, stats)
            assert mock_fetch.call_count == 0, "replay 중 HTTP 호출이 발생했다"


# ─ FT5: 체인에서 예외 하나 → 나머지 완료 ────────────────────────────────────

class TestFT5ChainException:
    """FT5: 핸들러 하나 예외 → 다른 소스는 완료, 실패 수 > 0 (7.10절)."""

    def test_one_failing_handler_does_not_block_others(
        self, processor_up, raw_store, schema_engine, tide, ft_farm_sites, clean_db
    ):
        """
        interpolation 핸들러가 예외를 던져도 grading·evaluation 은 완료.
        stats.failures["interpolation"] > 0, 단계 실패 카운트 기록.
        """
        import grading.main as gr
        import evaluation.main as ev
        from flowtest.main import _bind_handler, _wrap, _Stats
        from common.config import load_definitions

        pm, repo = processor_up
        defs = load_definitions()
        stats = _Stats()
        q = MemoryQueue()

        def bad_ip_handler(msg):
            raise RuntimeError("interpolation 의도적 실패")

        q.subscribe("raw.fetched", _wrap("processor", "raw.fetched",
            _bind_handler(pm.handle_raw_fetched, q), stats))
        q.subscribe("obs.loaded", _wrap("interpolation", "obs.loaded",
            bad_ip_handler, stats))
        q.subscribe("obs.loaded", _wrap("grading", "obs.loaded",
            _bind_handler(gr.handle_obs_loaded, repo, q, defs), stats))
        q.subscribe("interp.done", _wrap("grading", "interp.done",
            _bind_handler(gr.handle_interp_done, repo, q, defs), stats))
        q.subscribe("grade.done", _wrap("evaluation", "grade.done",
            _bind_handler(ev.handle_grade_done, repo, q, OPERATIONAL), stats))

        _inject_tide_and_publish(raw_store, q, tide)

        # interpolation 실패 기록
        assert stats.failures.get("interpolation", 0) > 0, (
            "interpolation 예외가 실패로 기록되지 않았다"
        )
        # grading 은 obs.loaded 를 받아 완료 (grade.done 발행)
        grade_done = [m for m in q.drain("grade.done")]
        assert grade_done, "grading 은 interpolation 실패와 무관하게 grade.done 을 내야 한다"

    def test_failure_count_in_summary_includes_stage_failures(
        self, processor_up, schema_engine, clean_db, ft_farm_sites
    ):
        """요약 출력의 stage_failures 에 실패 카운트가 포함된다."""
        from flowtest.main import _Stats, _print_summary
        from common.repository.sql import SqlRepository

        _, repo = processor_up
        stats = _Stats()
        stats.failures["processor"] = 3
        stats.failures["grading"] = 1
        stats.runs = 2

        q = MemoryQueue()
        import io, json
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            _print_summary(repo, q, stats)

        output = buf.getvalue()
        # JSON 한 줄 (마지막 줄) 파싱
        json_line = [l for l in output.strip().splitlines() if l.startswith("{")]
        assert json_line
        summary = json.loads(json_line[-1])
        assert summary["stage_failures"]["processor"] == 3
        assert summary["stage_failures"]["grading"] == 1
        assert summary["runs"] == 2

        # M2: 결과 테이블 행 수 포함
        assert "result_table_rows" in summary
        assert "farm_readings" in summary["result_table_rows"]
        assert "raw_index" in summary["result_table_rows"]
        assert "ingest_runs" in summary["result_table_rows"]

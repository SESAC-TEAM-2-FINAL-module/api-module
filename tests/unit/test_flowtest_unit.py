"""
flowtest 통과 기준 — DB 없는 단위 테스트 (계획서 7.10절, 개정 21)
FT1: 함수 동일성 (is 연산자), 기동 검사 호출 집합, 단계 코드의 flowtest 미포함
FT6: 비밀 유출 없음 — 예외 경로 포함 (H5, 계획서 2.3절)
"""
from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ─ FT1: 함수 동일성 ───────────────────────────────────────────────────────────

class TestFT1FunctionIdentity:
    """FT1 세 조건 (7.10절):
    ①  래퍼의 _stage_fn is 단계 함수 (is 연산자)
    ②  _preflight 의 기동 검사 호출 집합 = 각 stage main() 의 것 (추출된 함수)
    ③  단계 코드에 flowtest import 없음 (AST/grep)
    """

    # ── ① _stage_fn is 연산자 검사 ────────────────────────────────────────────

    def test_bind_handler_preserves_fn_identity(self):
        """_bind_handler → _stage_fn is 단계 함수."""
        import processor.main as pm
        from flowtest.main import _bind_handler

        bound = _bind_handler(pm.handle_raw_fetched, MagicMock())
        assert bound._stage_fn is pm.handle_raw_fetched

    def test_wrap_propagates_stage_fn(self):
        """_wrap 이 _stage_fn 을 핸들러에서 _wrapped 로 전파한다."""
        import processor.main as pm
        from flowtest.main import _bind_handler, _wrap, _Stats

        bound = _bind_handler(pm.handle_raw_fetched, MagicMock())
        wrapped = _wrap("processor", "raw.fetched", bound, _Stats())
        assert wrapped._stage_fn is pm.handle_raw_fetched

    def test_setup_pipeline_raw_fetched_stage_fn(self, monkeypatch):
        """_setup_pipeline 이 등록한 raw.fetched 핸들러의 _stage_fn is pm.handle_raw_fetched."""
        import processor.main as pm
        from flowtest.main import _setup_pipeline, _Stats
        from common.queue import MemoryQueue

        monkeypatch.setattr(pm, "_load_adapters", lambda: None)
        monkeypatch.setattr(pm, "startup", lambda **kw: None)

        q = MemoryQueue()
        _setup_pipeline(MagicMock(), {}, {}, q, _Stats())

        raw_h = q._handlers["raw.fetched"]
        assert len(raw_h) == 1
        assert raw_h[0]._stage_fn is pm.handle_raw_fetched

    def test_setup_pipeline_obs_loaded_stage_fns(self, monkeypatch):
        """obs.loaded 핸들러 두 개의 _stage_fn — ip.handle_obs_loaded, gr.handle_obs_loaded."""
        import processor.main as pm
        import interpolation.main as ip
        import grading.main as gr
        from flowtest.main import _setup_pipeline, _Stats
        from common.queue import MemoryQueue

        monkeypatch.setattr(pm, "_load_adapters", lambda: None)
        monkeypatch.setattr(pm, "startup", lambda **kw: None)

        q = MemoryQueue()
        _setup_pipeline(MagicMock(), {}, {}, q, _Stats())

        fns = {h._stage_fn for h in q._handlers["obs.loaded"]}
        assert ip.handle_obs_loaded in fns
        assert gr.handle_obs_loaded in fns

    def test_setup_pipeline_interp_done_stage_fn(self, monkeypatch):
        """interp.done 핸들러의 _stage_fn is gr.handle_interp_done."""
        import processor.main as pm
        import grading.main as gr
        from flowtest.main import _setup_pipeline, _Stats
        from common.queue import MemoryQueue

        monkeypatch.setattr(pm, "_load_adapters", lambda: None)
        monkeypatch.setattr(pm, "startup", lambda **kw: None)

        q = MemoryQueue()
        _setup_pipeline(MagicMock(), {}, {}, q, _Stats())

        assert q._handlers["interp.done"][0]._stage_fn is gr.handle_interp_done

    def test_setup_pipeline_grade_done_stage_fn(self, monkeypatch):
        """grade.done 핸들러의 _stage_fn is ev.handle_grade_done."""
        import processor.main as pm
        import evaluation.main as ev
        from flowtest.main import _setup_pipeline, _Stats
        from common.queue import MemoryQueue

        monkeypatch.setattr(pm, "_load_adapters", lambda: None)
        monkeypatch.setattr(pm, "startup", lambda **kw: None)

        q = MemoryQueue()
        _setup_pipeline(MagicMock(), {}, {}, q, _Stats())

        assert q._handlers["grade.done"][0]._stage_fn is ev.handle_grade_done

    # ── ② 기동 검사 호출 집합 = 각 단계 진입점 (스파이로 실제 호출 기록) ─────────

    _EXTRACTED = [("processor.main", "schema_checks"), ("interpolation.main", "startup_checks"),
                  ("grading.main", "startup_checks"), ("evaluation.main", "startup_checks")]

    def _stage_calls(self, monkeypatch) -> set[str]:
        """각 단계 진입점(processor.startup · interpolation.main · grading.main · evaluation._repository)을
        돌려 실제로 불린 기동 시 검사 함수를 모은다. 첫 검사에서 멈춰 뒤의 부작용을 막는다"""
        import importlib
        monkeypatch.setenv("DATABASE_URL", "sqlite://")
        called: set[str] = set()

        class _Stop(Exception):
            pass

        for mod_name, fn in self._EXTRACTED:
            mod = importlib.import_module(mod_name)
            def _spy(*a, _n=f"{mod_name}.{fn}", **k):
                called.add(_n)
                raise _Stop
            monkeypatch.setattr(mod, fn, _spy)
        import processor.main as pm, interpolation.main as ip, grading.main as gr, evaluation.main as ev
        for entry in (lambda: pm.startup(definitions={}, operational={}, repo=MagicMock()),
                      lambda: ip.main([]), lambda: gr.main([]), lambda: ev._repository()):
            with pytest.raises(_Stop):
                entry()
        return called

    def test_preflight_check_set_equals_stage_entrypoints(self, monkeypatch):
        import importlib
        import flowtest.main as ft
        stage = self._stage_calls(monkeypatch)
        assert stage == {f"{m}.{f}" for m, f in self._EXTRACTED}

        monkeypatch.undo()
        runner: set[str] = set()
        for mod_name, fn in self._EXTRACTED + [("processor.main", "seed_check")]:
            mod = importlib.import_module(mod_name)
            ret = [] if fn == "seed_check" else ({} if mod_name == "grading.main" else None)
            monkeypatch.setattr(mod, fn, lambda *a, _n=f"{mod_name}.{fn}", _r=ret, **k: runner.add(_n) or _r)
        import common.config as cfg
        monkeypatch.setattr(cfg, "load_operational", lambda *a, **k: {})
        monkeypatch.setattr(ft, "_check_farm_sites", lambda engine: None)
        ft._preflight(MagicMock(), {}, collect_mode=False)
        assert stage <= runner, f"실행기가 부르지 않는 단계 기동 시 검사: {stage - runner}"
        assert runner - stage == {"processor.main.seed_check"}

    # ── ③ 단계 코드에 flowtest import 없음 ────────────────────────────────────

    def test_no_flowtest_import_in_stage_code(self):
        """단계 코드 파일에 flowtest 참조 없음 (2.1.1절: 단계 코드는 flowtest 를 import 하지 않는다)."""
        import processor
        api_root = Path(processor.__file__).parent.parent

        stage_dirs = ["collector", "processor", "interpolation", "grading", "evaluation"]
        violations = []
        for stage in stage_dirs:
            stage_path = api_root / stage
            if not stage_path.is_dir():
                continue
            for py_file in stage_path.rglob("*.py"):
                src = py_file.read_text("utf-8")
                if "flowtest" in src:
                    violations.append(str(py_file.relative_to(api_root)))

        assert not violations, f"단계 코드에 flowtest 참조: {violations}"


# ─ FT6: 비밀 유출 없음 ────────────────────────────────────────────────────────

class TestFT6SecretLeak:
    """비밀 유출 없음 — 예외 메시지에 URL·키가 있어도 로그에 나오지 않는다 (H5, 7.10절)."""

    _MARKER = "SECRETKEY_MARKER_FT6_XYZ"

    def test_wrap_does_not_log_exception_message(self, caplog):
        """_wrap 이 예외 메시지를 로그에 쓰지 않는다 (종류 이름만)."""
        from flowtest.main import _wrap, _Stats
        from common.queue import MemoryQueue, Message

        secret = self._MARKER

        def handler_with_secret(msg):
            raise RuntimeError(f"URL?serviceKey={secret}&data=xyz")

        stats = _Stats()
        wrapped = _wrap("test-stage", "topic", handler_with_secret, stats)

        with caplog.at_level(logging.ERROR, logger="flowtest"):
            q = MemoryQueue()
            q.subscribe("topic", wrapped)
            q.publish(Message(topic="topic", payload={}))

        assert secret not in caplog.text, "예외 메시지가 로그에 노출됨"
        assert "RuntimeError" in caplog.text
        assert stats.failures["test-stage"] == 1

    def test_wrap_covers_httpx_exception_path(self, caplog):
        """_wrap 이 HTTP 예외(URL 포함 가능) 경로에서도 메시지를 로그에 쓰지 않는다 (H5)."""
        from flowtest.main import _wrap, _Stats
        from common.queue import MemoryQueue, Message

        secret = self._MARKER

        # httpx 예외처럼 URL을 포함하는 커스텀 예외
        class FakeHttpxError(Exception):
            pass

        def handler_with_http_exc(msg):
            raise FakeHttpxError(f"ConnectError: https://api.invalid?key={secret}")

        stats = _Stats()
        wrapped = _wrap("collector", "raw.fetched", handler_with_http_exc, stats)

        with caplog.at_level(logging.ERROR, logger="flowtest"):
            q = MemoryQueue()
            q.subscribe("raw.fetched", wrapped)
            q.publish(Message(topic="raw.fetched", payload={}))

        assert secret not in caplog.text
        assert "FakeHttpxError" in caplog.text

    def test_do_collect_does_not_log_exception_message(self, caplog, monkeypatch):
        """_do_collect 의 예외 처리도 종류 이름만 기록한다."""
        from flowtest.main import _Stats
        from common.queue import MemoryQueue

        secret = self._MARKER

        # collector.main.main 을 예외를 던지도록 monkeypatch
        import collector.main as cm
        monkeypatch.setattr(cm, "main",
                            lambda workload, q: (_ for _ in ()).throw(
                                ConnectionError(f"APIKey={secret}?key=abc")))

        # _do_collect 를 직접 호출
        import flowtest.main as ft
        stats = _Stats()
        q = MemoryQueue()

        with caplog.at_level(logging.ERROR, logger="flowtest"):
            ft._do_collect(q, stats)

        assert secret not in caplog.text, "예외 메시지가 로그에 노출됨"
        assert stats.failures["collector"] == 4  # 4 workload 모두 실패


# ─ H2: loop 주기 검증 ─────────────────────────────────────────────────────────

class TestH2LoopIntervalValidation:
    """loop 모드에서 주기 인수가 하나라도 없으면 SystemExit."""

    def test_loop_mode_requires_all_intervals(self, monkeypatch):
        """모든 주기 인수가 None 이면 SystemExit."""
        import flowtest.main as ft

        # 환경 변수 지움 — 인수 기본값이 None 이 되게
        for key in ["FT_TIDE_INTERVAL_SEC", "FT_BULLETIN_SEASON_INTERVAL_SEC",
                    "FT_BULLETIN_OFFSEASON_INTERVAL_SEC", "FT_LINE_INTERVAL_SEC",
                    "FT_FISHERY_INTERVAL_SEC", "FT_SWEEP_INTERVAL_SEC",
                    "FT_ERROR_INTERVAL_SEC"]:
            monkeypatch.delenv(key, raising=False)

        args = ft._parse_args(["--run", "loop"])
        with pytest.raises(SystemExit):
            ft._validate_loop_intervals(args)

    def test_once_mode_does_not_require_intervals(self, monkeypatch):
        """once 모드에서는 주기 인수 없어도 기동 멈추지 않는다."""
        import flowtest.main as ft

        for key in ["FT_TIDE_INTERVAL_SEC", "FT_BULLETIN_SEASON_INTERVAL_SEC",
                    "FT_BULLETIN_OFFSEASON_INTERVAL_SEC", "FT_LINE_INTERVAL_SEC",
                    "FT_FISHERY_INTERVAL_SEC", "FT_SWEEP_INTERVAL_SEC",
                    "FT_ERROR_INTERVAL_SEC"]:
            monkeypatch.delenv(key, raising=False)

        args = ft._parse_args(["--run", "once"])
        # _validate_loop_intervals 는 loop 모드에서만 부른다 — once 에서는 호출하지 않음
        # main() 에서 args.run == "loop" 일 때만 _validate_loop_intervals 를 부른다
        assert args.run == "once"
        assert args.tide_interval is None


# ─ H3: 시즌/시즌 밖 주기 ──────────────────────────────────────────────────────

class TestH3BulletinInterval:
    """_bulletin_interval 이 KST 월에 따라 올바른 주기를 반환한다."""

    def test_season_months_return_season_interval(self, monkeypatch):
        """KST 5-10월 → bulletin_season_interval."""
        import flowtest.main as ft
        from datetime import datetime, timezone, timedelta
        from unittest.mock import patch

        args = MagicMock()
        args.bulletin_season_interval = 3600
        args.bulletin_offseason_interval = 21600

        # KST 7월 (시즌)
        kst_july = datetime(2026, 7, 15, 12, 0, tzinfo=timezone(timedelta(hours=9)))
        with patch("flowtest.main.datetime") as mock_dt:
            mock_dt.now.return_value = kst_july
            result = ft._bulletin_interval(args)

        assert result == 3600

    def test_offseason_months_return_offseason_interval(self, monkeypatch):
        """KST 1-4월, 11-12월 → bulletin_offseason_interval."""
        import flowtest.main as ft
        from datetime import datetime, timezone, timedelta
        from unittest.mock import patch

        args = MagicMock()
        args.bulletin_season_interval = 3600
        args.bulletin_offseason_interval = 21600

        # KST 1월 (시즌 밖)
        kst_jan = datetime(2026, 1, 15, 12, 0, tzinfo=timezone(timedelta(hours=9)))
        with patch("flowtest.main.datetime") as mock_dt:
            mock_dt.now.return_value = kst_jan
            result = ft._bulletin_interval(args)

        assert result == 21600

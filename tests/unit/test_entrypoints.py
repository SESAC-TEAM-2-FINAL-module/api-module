"""
실행 진입점 — 인계 매니페스트(handoff/k8s/*.yaml)의 명령을 받는다 (2.1절)
DB 연결은 DATABASE_URL 하나 — 없으면 멈춘다. 수집용 URL은 요구하지 않는다
"""
import pytest


def test_database_url_required(monkeypatch):
    from common.config import database_url
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(SystemExit):
        database_url()


def test_database_url_does_not_need_collector_urls(monkeypatch):
    from common.config import database_url
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.delenv("DTRECENT_URL", raising=False)
    monkeypatch.delenv("NIFS_URL", raising=False)
    assert database_url() == "sqlite://"


@pytest.mark.parametrize("module", ["grading.main", "interpolation.main"])
def test_consumers_stop_without_database(monkeypatch, module):
    """grading·interpolation 진입점 — env.database_url(없는 속성) 대신 DATABASE_URL"""
    import importlib
    monkeypatch.delenv("DATABASE_URL", raising=False)
    mod = importlib.import_module(module)
    with pytest.raises(SystemExit):
        mod.main([])


def test_interpolation_error_command_alias(monkeypatch):
    """매니페스트 CronJob 명령 'error' → 오늘의 오차 산출 (컨슈머로 뜨지 않는다)"""
    import interpolation.main as ip
    called = {}
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setattr(ip, "create_engine", lambda url: object(), raising=False)

    class _Repo:
        def __init__(self, engine):
            pass

        def check_schema(self):
            pass

    import common.repository as cr
    monkeypatch.setattr(cr, "SqlRepository", _Repo)
    monkeypatch.setattr(ip, "run_interpolation_error", lambda repo, defs: called.setdefault("error", True))
    ip.main(["error"])
    assert called == {"error": True}


def test_evaluation_unknown_command():
    import evaluation.main as ev
    assert ev.main(["nope"]) == 1


@pytest.mark.parametrize("cmd", [[], ["evaluate"], ["sweep"]])
def test_evaluation_commands_need_database(monkeypatch, cmd):
    """명령 없음(컨슈머)·evaluate·sweep — 매니페스트 명령을 받고, DB가 없으면 멈춘다"""
    import evaluation.main as ev
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(SystemExit):
        ev.main(cmd)

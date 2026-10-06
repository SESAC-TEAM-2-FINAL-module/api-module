"""
I-15 SD1·SD3 연결 검사 — 검사 함수가 아니라 실제 진입점으로 (계획서 7.9절 취지)

- SD1: 빈 시드 DB에서 grading `main`, evaluation `evaluate`·`sweep`이 기동을 멈추고,
       evaluation `gate`와 processor 기동(`startup`)은 멈추지 않는다. 시드를 넣으면 기동한다
- SD3: `python -m processor.main seed-check` — 시드와 다른 DB에서 종료 1, 같은 DB에서 종료 0, DB에 쓰지 않는다
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from sqlalchemy import text

ROOT = Path(__file__).parents[2]
OPERATIONAL = ROOT / "config" / "operational.initial.yaml"


@pytest.fixture()
def db_env(schema_engine, monkeypatch):
    """진입점이 DATABASE_URL로 테스트 DB에 붙게 한다(값은 출력하지 않는다)"""
    url = schema_engine.url.render_as_string(hide_password=False)
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("OPERATIONAL_CONFIG_PATH", str(OPERATIONAL))
    return url


def _counts(engine) -> dict[str, int]:
    from common.repository.tables import metadata
    with engine.connect() as conn:
        return {t.name: conn.execute(text(f"SELECT COUNT(*) FROM {t.name}")).scalar_one()
                for t in metadata.sorted_tables}


class TestSD1Entrypoints:
    def test_grading_main_stops_on_empty_areas(self, db_env, clean_db):
        import grading.main as gr
        with pytest.raises(SystemExit, match="해역 시드"):
            gr.main([])

    @pytest.mark.parametrize("cmd", [["evaluate"], ["sweep"], []])
    def test_evaluation_stops_on_empty_seeds(self, db_env, clean_db, cmd):
        import evaluation.main as ev
        with pytest.raises(SystemExit, match="해역 시드"):
            ev.main(cmd)

    def test_evaluation_stops_when_only_axis_coverage_empty(self, db_env, clean_db, repo):
        import evaluation.main as ev
        from common.seeds import read_areas
        repo.upsert_areas(read_areas())
        with pytest.raises(SystemExit, match="axis_coverage"):
            ev.main(["sweep"])

    def test_evaluation_gate_does_not_touch_db(self, monkeypatch):
        """gate는 DB 없이 돈다 — 빈 시드 검사(_repository)를 타지 않는다"""
        import evaluation.main as ev
        import evaluation._gate as gate
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setattr(ev, "_repository", lambda: (_ for _ in ()).throw(AssertionError("gate가 DB를 열었다")))
        monkeypatch.setattr(gate, "run_gate", lambda path: 0)
        assert ev.main(["gate", str(OPERATIONAL)]) == 0

    def test_processor_startup_runs_on_empty_seeds(self, db_env, clean_db, repo):
        import processor.main as pm
        from common.config import load_definitions
        pm.startup(definitions=load_definitions(),
                   operational=yaml.safe_load(OPERATIONAL.read_text("utf-8")), repo=repo)

    def test_seeded_db_starts(self, db_env, clean_db, repo, monkeypatch):
        import common.queue as cq
        import evaluation.main as ev
        import grading.main as gr
        from common.seeds import load_seeds

        class _FakeNats:
            @classmethod
            def from_env(cls, **kwargs):
                return cls()
            def run(self, handler):
                pass

        monkeypatch.setattr(cq, "NatsQueue", _FakeNats)

        load_seeds(repo)
        gr.main([])
        assert ev.main(["evaluate"]) == 0
        # sweep 본문은 웹 소유 farm_sites를 읽는다 — 여기서는 기동 검사를 지나 판정에 닿는지만 본다
        reached = {}
        monkeypatch.setattr(ev, "handle_sweep", lambda repo, cfg: reached.setdefault("sweep", True))
        assert ev.main(["sweep"]) == 0
        assert reached == {"sweep": True}


class TestSD3SeedCheckCommand:
    def _run(self, url: str) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env["DATABASE_URL"] = url
        env["PYTHONPATH"] = str(ROOT / "src" / "api_module")
        env["PYTHONIOENCODING"] = "utf-8"
        env.pop("OPERATIONAL_CONFIG_PATH", None)        # 운영 조정 없이 돈다
        return subprocess.run([sys.executable, "-m", "processor.main", "seed-check"],
                              cwd=str(ROOT), env=env, capture_output=True, text=True,
                              encoding="utf-8", timeout=120)

    def test_exit_1_on_empty_db_and_no_writes(self, db_env, clean_db, schema_engine):
        before = _counts(schema_engine)
        r = self._run(db_env)
        assert r.returncode == 1, r.stderr[-500:]
        assert "areas 빠진 행" in r.stdout
        assert _counts(schema_engine) == before

    def test_exit_0_on_matching_db_and_no_writes(self, db_env, clean_db, repo, schema_engine):
        from common.seeds import load_seeds
        load_seeds(repo)
        before = _counts(schema_engine)
        r = self._run(db_env)
        assert r.returncode == 0, (r.stdout[-500:], r.stderr[-500:])
        assert "차이 0건" in r.stdout
        assert _counts(schema_engine) == before

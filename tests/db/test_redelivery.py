"""
7.11 J2 — 소비자별 "커밋 성공 → 다음 알림 발행 실패 → 재전달" (개정 22, 검수 H2·N6).
큐 구현과 무관한 핸들러의 멱등을 본다 — 발행이 한 번 실패하는 인메모리 큐로 같은 메시지를 두 번 처리한다.
`completeness-check`(결과 행·이벤트 한 벌, 다음 알림 없음)는 test_completeness_e2e.py
`test_E7_duplicate_notice_changes_nothing`이 같은 알림 두 번으로 본다.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from sqlalchemy import text

from common.queue import MemoryQueue, load_spec, msg_id_of
from common.repository.tables import metadata

from .test_pipeline_chain import farm_sites  # noqa: F401 — 고정물

_ROOT = Path(__file__).parents[2]
_SPEC = load_spec()


class _FlakyQueue(MemoryQueue):
    """`fail_topic`의 첫 발행만 실패한다 — 핸들러의 DB 커밋이 끝난 뒤 발행에서 죽는 경우"""

    def __init__(self, fail_topic: str | None = None) -> None:
        super().__init__()
        self._fail = fail_topic

    def publish(self, msg) -> None:
        if msg.topic == self._fail:
            self._fail = None
            raise ConnectionError("발행 실패 주입")
        super().publish(msg)


def _counts(engine) -> dict:
    with engine.connect() as conn:
        return {t.name: conn.execute(text(f"SELECT COUNT(*) FROM {t.name}")).scalar_one()
                for t in metadata.sorted_tables}


def _ids(msgs, topic) -> list[str | None]:
    return sorted(str(msg_id_of(topic, m.payload, _SPEC)) for m in msgs)


def _redeliver(handler, payload, topic: str, engine):
    """1회차: 커밋 뒤 발행 실패 → 예외. 2회차(재전달): 예외 없이 끝나야 한다. (1회차 행 수, 2회차 행 수, 2회차 큐)"""
    q1 = _FlakyQueue(topic)
    with pytest.raises(ConnectionError):
        handler(payload, q1)
    after_first = _counts(engine)
    q2 = MemoryQueue()
    handler(payload, q2)
    return after_first, _counts(engine), q2


def _tide_raw(raw_store, tide):
    obs = [(code, "2026-08-01 09:00:00", 24.0 + i * 0.3) for i, code in enumerate(tide.STATIONS)]
    return raw_store.put("dtRecent", "all", tide.raw(tide.body(obs)))


def test_j2_processor(processor_up, raw_store, schema_engine, tide):
    pm, _ = processor_up
    key = _tide_raw(raw_store, tide)
    first, second, q = _redeliver(lambda p, q: pm.process(p["raw_id"], p["api"], q),
                                  {"raw_id": key, "api": "dtRecent"}, "obs.loaded", schema_engine)
    assert first == second                                 # 관측·색인 한 벌
    loaded = q.drain("obs.loaded")
    assert len(loaded) == 1
    # 1회차가 냈어야 할 알림과 같은 Msg-Id — 서버 중복 제거로 걸러진다
    replay = MemoryQueue()
    pm.process(key, "dtRecent", replay)
    assert _ids(loaded, "obs.loaded") == _ids(replay.drain("obs.loaded"), "obs.loaded")


def test_j2_interpolation(processor_up, raw_store, schema_engine, tide, farm_sites):  # noqa: F811
    import interpolation.main as ip
    from common.config import load_definitions
    from common.repository.tables import interpolation_runs
    pm, repo = processor_up
    defs = load_definitions()
    q0 = MemoryQueue()
    pm.process(_tide_raw(raw_store, tide), "dtRecent", q0)
    payload = q0.drain("obs.loaded")[0].payload
    first, second, q = _redeliver(lambda p, q: ip.handle_obs_loaded(p, repo, q, defs), payload,
                                  "interp.done", schema_engine)
    assert first == second and first["interpolation_runs"] >= 1 and first["interpolation_weights"] >= 1
    done = q.drain("interp.done")
    assert len(done) == 1
    with schema_engine.connect() as conn:
        run_ids = [r[0] for r in conn.execute(text("SELECT run_id FROM interpolation_runs"))]
    assert done[0].payload["run_id"] in run_ids
    assert all(len(r) <= interpolation_runs.c.run_id.type.length for r in run_ids)


@pytest.mark.parametrize("entry", ["obs.loaded", "interp.done"])
def test_j2_grading(processor_up, raw_store, schema_engine, tide, farm_sites, entry):  # noqa: F811
    import grading.main as gr
    import interpolation.main as ip
    from common.config import load_definitions
    pm, repo = processor_up
    defs = load_definitions()
    q0 = MemoryQueue()
    pm.process(_tide_raw(raw_store, tide), "dtRecent", q0)
    loaded = q0.drain("obs.loaded")[0].payload
    if entry == "obs.loaded":
        handler, payload = (lambda p, q: gr.handle_obs_loaded(p, repo, q, defs)), loaded
    else:
        ip.handle_obs_loaded(loaded, repo, q0, defs)
        handler, payload = (lambda p, q: gr.handle_interp_done(p, repo, q, defs)), q0.drain("interp.done")[0].payload
    first, second, q = _redeliver(handler, payload, "grade.done", schema_engine)
    history_growth = second.pop("farm_reading_history") - first.pop("farm_reading_history")
    assert first == second and first["farm_readings"] >= 1          # farm_readings 한 벌
    assert history_growth >= 0                                      # 이력은 늘 수 있다 — 허용(보고)
    done = q.drain("grade.done")
    assert done
    ids = _ids(done, "grade.done")
    assert len(ids) == len(set(ids))                                # 축마다 1건


def test_j2_evaluation(processor_up, raw_store, schema_engine, tide, farm_sites):  # noqa: F811
    import evaluation.main as ev
    import grading.main as gr
    from common.config import load_definitions
    pm, repo = processor_up
    defs = load_definitions()
    op = yaml.safe_load((_ROOT / "config" / "operational.initial.yaml").read_text("utf-8"))
    q0 = MemoryQueue()
    pm.process(_tide_raw(raw_store, tide), "dtRecent", q0)
    gr.handle_obs_loaded(q0.drain("obs.loaded")[0].payload, repo, q0, defs)
    payload = q0.drain("grade.done")[0].payload
    first, second, q = _redeliver(lambda p, q: ev.handle_grade_done(p, repo, q, op), payload,
                                  "result.updated", schema_engine)
    assert first == second and first["axis_status"] >= 1             # axis_status 한 벌
    # 현재 동작 기록: evaluation은 axis_status를 새로 쓸 때만 result.updated를 내므로(basis_utc 쓰기 규칙),
    # 1회차가 커밋 뒤 발행에서 죽으면 재전달은 알림을 다시 내지 않는다 — 유실. 계획서가 정하지 않은 동작이라
    # 보고서 "결정 대기"로 올린다(2.2절 result.updated는 웹의 선택 구독·캐시 무효화)
    assert q.drain("result.updated") == []

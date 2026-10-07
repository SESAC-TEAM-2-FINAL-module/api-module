"""
이름 대조 검사 — 부품 사이의 연결 (2026-10-01 점검 후속)

부품 단위 검사만으로는 "매니페스트 명령 → 진입점 → 어댑터 → 다음 단계"가 이어지는지 드러나지 않았다
(진입점 레지스트리 분리, 워크로드 이름 불일치, 소비자 없는 api_id). 이름이 서로 맞는지를 정적으로 대조한다.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).parents[2]
_K8S = _ROOT / "handoff" / "k8s"


def _commands() -> list[list[str]]:
    """인계 매니페스트의 컨테이너 command 배열 전부"""
    out = []

    def walk(o):
        if isinstance(o, dict):
            if isinstance(o.get("command"), list):
                out.append([str(x) for x in o["command"]])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    for f in sorted(_K8S.glob("*.yaml")):
        for doc in yaml.safe_load_all(f.read_text("utf-8")):
            walk(doc)
    return out


def _by_module(module: str) -> list[list[str]]:
    return [c[3:] for c in _commands() if c[:3] == ["python", "-m", module]]


def test_every_manifest_command_targets_known_module():
    known = {"collector.main", "collector.fishery_watch", "processor.main",
             "interpolation.main", "grading.main", "evaluation.main"}
    cmds = _commands()
    assert cmds, "매니페스트에서 command를 찾지 못함"
    for c in cmds:
        assert c[:2] == ["python", "-m"] and c[2] in known, c


def test_collector_workloads_resolve_to_registered_adapters():
    import collector.main as cm
    cm._load_adapters()
    args = _by_module("collector.main")
    assert args
    for a in args:
        assert len(a) == 1, a
        adapters = cm.resolve(a[0])          # 없으면 SystemExit
        assert adapters


def test_collector_fishery_watch_module_is_runnable():
    src = (_ROOT / "src" / "api_module" / "collector" / "fishery_watch.py").read_text("utf-8")
    assert 'if __name__ == "__main__":' in src


def _fake_processor_connections(monkeypatch):
    """processor `__main__`의 연결(판정 정의·운영 조정·DB·원문 저장소·큐)을 가짜로 — 명령 인자 해석만 본다.
    진입점이 함수 안에서 `from common.queue import open_queue`로 가져오므로 모듈 속성 패치가 먹는다"""
    import common.config as cc
    import common.queue as cq
    import common.raw_store as crs
    import processor.main as pm
    opened = []

    class _FakeQueue(cq.MemoryQueue):
        def __init__(self, workload):
            super().__init__()
            self.workload, self.ran, self.closed = workload, False, False
            opened.append(self)

        def run(self):
            self.ran = True

        def close(self):
            self.closed = True

    monkeypatch.setattr(pm, "_load_adapters", lambda: None)
    monkeypatch.setattr(pm, "startup", lambda *a, **k: None)
    monkeypatch.setattr(pm, "_repository_from_env", lambda: object())
    monkeypatch.setattr(pm, "schema_checks", lambda repo: None)
    monkeypatch.setattr(cc, "load_definitions", lambda *a, **k: {})
    monkeypatch.setattr(cc, "load_operational", lambda *a, **k: {})
    monkeypatch.setattr(crs, "open_raw_store", lambda image: None)
    monkeypatch.setattr(cq, "open_queue", lambda workload, repo=None: _FakeQueue(workload))
    return opened


def test_processor_manifest_commands_parse(monkeypatch):
    """processor 매니페스트 명령(없음 / reprocess)이 진입점 인자로 해석된다"""
    import runpy
    import sys
    import processor.main as pm
    seen = []
    opened = _fake_processor_connections(monkeypatch)
    monkeypatch.setattr(pm, "reprocess_range", lambda a, b, queue: seen.append((a, b)) or 0)

    for args in _by_module("processor.main"):
        if args[:1] == ["reprocess"]:
            args = args + ["--raw-id-from", "1", "--raw-id-to", "2"]   # 매니페스트 주석: 인프라가 설정
        monkeypatch.setattr(sys, "argv", ["processor.main", *args])
        runpy.run_module("processor.main", run_name="__main__")
    assert seen == [(1, 2)]
    assert opened and all(q.workload == "processor" and q.closed for q in opened)
    consumers = [q for q in opened if q.ran]          # 명령 없음 = raw.fetched 컨슈머
    assert consumers and all(set(q._handlers) == {"raw.fetched"} for q in consumers)


@pytest.mark.parametrize("module,accepted", [
    ("evaluation.main", {(), ("sweep",), ("evaluate",), ("gate",)}),
    ("interpolation.main", {(), ("error",), ("interpolation-error",)}),
    ("grading.main", {()}),
])
def test_stage_manifest_commands_are_accepted(module, accepted):
    for args in _by_module(module):
        assert tuple(args[:1]) in accepted, (module, args)


def test_every_collected_api_has_a_consumer():
    """collector가 raw.fetched에 싣는 api는 processor가 받거나, 설계 대기(PENDING_APIS)로 명시돼 있다"""
    import collector.main as cm
    import processor.main as pm
    cm._load_adapters()
    pm._load_adapters()
    published = set(cm._REGISTRY) | {"femoSeaList"}     # 감시는 같은 실행에서 femoSeaList 전량 원문도 낸다
    for api in sorted(published):
        if getattr(cm._REGISTRY.get(api), "uses_completeness_run", False):
            continue                                    # 분할 합산 — raw.fetched를 내지 않는다(검사 아래)
        handled = api in pm._REGISTRY or api in pm._ADAPTER_ALIAS
        assert handled or api in pm.PENDING_APIS, f"소비자 없는 api_id: {api}"


def test_pending_apis_are_really_unhandled():
    """설계 대기 목록이 처리 가능한 api를 가리면 안 된다"""
    import processor.main as pm
    pm._load_adapters()
    assert not (pm.PENDING_APIS & set(pm._REGISTRY))


def test_no_pending_apis_after_rev17():
    """개정 17 이후 설계 대기는 비어 있다 (7.9 E2)"""
    import processor.main as pm
    assert pm.PENDING_APIS == frozenset()


def test_completeness_check_command_parses(monkeypatch):
    """검사기 명령은 매니페스트가 아직 없어 E1이 못 본다 — 진입점 인자로 기동되는지 여기서 확인 (7.9 E7)"""
    import runpy
    import sys
    opened = _fake_processor_connections(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["processor.main", "completeness-check"])
    runpy.run_module("processor.main", run_name="__main__")
    assert len(opened) == 1
    q = opened[0]
    assert q.workload == "completeness-check" and q.ran and q.closed
    assert set(q._handlers) == {"completeness.collected"}



def test_dialect_branches_only_in_dialect_module():
    """C14 — 방언 이름·방언 모듈은 common/repository/dialect.py 밖에 쓰지 않는다 (12절)"""
    import re
    pattern = re.compile(r"""['"](postgresql|mysql)['"]|dialects\.(postgresql|mysql)""")
    allowed = _ROOT / "src" / "api_module" / "common" / "repository" / "dialect.py"
    hits = [str(p.relative_to(_ROOT)) for p in (_ROOT / "src").rglob("*.py")
            if p != allowed and pattern.search(p.read_text("utf-8"))]
    assert hits == []

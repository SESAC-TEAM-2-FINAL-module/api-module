"""
CI 게이트 — 계획서 7.7절 ① 판정 정의 대조 + ①′ 운영 조정 검사.
② 건수 보존은 pytest tests/gate/test_counts.py 에서 별도 수행.

사용:
  python ci/gate/run_gate.py [--warn-pending]

  --warn-pending : <미결> 항목이 있어도 실패 대신 경고 (인계 전까지).
                   기본값: 경고. S12 진입 시 이 플래그를 제거한다.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]
DEFINITIONS = ROOT / "config" / "definitions.yaml"
EXPECTED = ROOT / "ci" / "gate" / "expected.yaml"
OPERATIONAL_INITIAL = ROOT / "config" / "operational.initial.yaml"
EVALUATION_MODULE = ROOT / "src" / "api_module"


# ─────────────────────────────────────────────────────────────────────────────
# ① 판정 정의 대조 — config/definitions.yaml vs ci/gate/expected.yaml (settings)
# ─────────────────────────────────────────────────────────────────────────────

def _get_nested(obj: object, dot_key: str) -> tuple[bool, object]:
    """점 표기법 키로 중첩 YAML에서 값을 읽는다. (found, value) 반환."""
    keys = dot_key.split(".")
    cur = obj
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return False, None
        cur = cur[k]
    return True, cur


def _check_definitions(warn_pending: bool) -> tuple[bool, list[str]]:
    """
    ① 설정값 대조.
    반환: (통과, 메시지 목록)
    """
    import yaml

    if not DEFINITIONS.exists():
        return False, [f"판정 정의 파일 없음: {DEFINITIONS}"]
    if not EXPECTED.exists():
        return False, [f"기준 문서 없음: {EXPECTED}"]

    defs = yaml.safe_load(DEFINITIONS.read_text(encoding="utf-8"))
    expected_doc = yaml.safe_load(EXPECTED.read_text(encoding="utf-8"))
    expected_settings: dict = expected_doc.get("settings", {})

    msgs: list[str] = []
    passed = True

    for key, exp_val in expected_settings.items():
        found, actual = _get_nested(defs, key)
        if not found:
            msgs.append(f"  [누락] {key}")
            passed = False
            continue

        # <미결> 처리
        if str(exp_val).strip() == "<미결>" or str(actual).strip() == "<미결>":
            if warn_pending:
                msgs.append(f"  [경고·미결] {key}: {actual!r}")
            else:
                msgs.append(f"  [실패·미결] {key}: {actual!r} (S12 전 결정 필요)")
                passed = False
            continue

        if actual != exp_val:
            msgs.append(f"  [불일치] {key}: 실제={actual!r}, 기준={exp_val!r}")
            passed = False

    return passed, msgs


# ─────────────────────────────────────────────────────────────────────────────
# ①′ 운영 조정 검사 — 스키마 검사 + evaluation gate (판정 재생)
# ─────────────────────────────────────────────────────────────────────────────

def _check_operational(warn_pending: bool) -> tuple[bool, list[str]]:
    """
    ①′ 운영 조정 검사.
    이 저장소 CI는 config/operational.initial.yaml 로 검사한다.
    반환: (통과, 메시지 목록)
    """
    import yaml

    if not OPERATIONAL_INITIAL.exists():
        return False, [f"운영 조정 초기값 파일 없음: {OPERATIONAL_INITIAL}"]

    cfg = yaml.safe_load(OPERATIONAL_INITIAL.read_text(encoding="utf-8"))

    # <미결> 값 포함 여부 확인
    cfg_text = OPERATIONAL_INITIAL.read_text(encoding="utf-8")
    has_pending = "<미결>" in cfg_text
    if has_pending and not warn_pending:
        return False, ["  [실패] 운영 조정 <미결> 잔존 — S12 진입 전 모두 결정 필요"]
    if has_pending:
        # 계획서 7.7절: <미결> 잔존 동안 스키마 검사를 경고로 두고 gate는 건너뜀
        return True, [
            "  [경고] 운영 조정 <미결> 잔존 — S12 진입 전 결정 필요. 스키마 검사·판정 재생 건너뜀.",
        ]
    pending_note: list[str] = []

    # evaluation gate 실행 (스키마 검사 + 판정 재생)
    gate_result = subprocess.run(
        [
            sys.executable, "-m", "evaluation.main", "gate",
            str(OPERATIONAL_INITIAL),
        ],
        capture_output=True,
        cwd=ROOT,
        env={
            **__import__("os").environ,
            "PYTHONPATH": str(EVALUATION_MODULE),
        },
    )
    stdout = (gate_result.stdout or b"").decode("utf-8", errors="replace")
    stderr = (gate_result.stderr or b"").decode("utf-8", errors="replace")

    msgs = pending_note[:]
    if gate_result.returncode != 0:
        msgs.append("  [실패] evaluation gate 불통과:")
        for line in stdout.splitlines():
            msgs.append(f"    {line}")
        if stderr:
            for line in stderr.splitlines():
                msgs.append(f"    (stderr) {line}")
        return False, msgs

    msgs.append("  evaluation gate 통과")
    for line in stdout.splitlines():
        msgs.append(f"    {line}")
    return True, msgs


# ─────────────────────────────────────────────────────────────────────────────
# 진입점
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="CI 게이트 ① ①′")
    parser.add_argument(
        "--warn-pending",
        action="store_true",
        default=False,
        help="<미결> 항목을 실패 대신 경고로 처리 (인계 전까지)",
    )
    args = parser.parse_args()

    overall = True

    print("=" * 60)
    print("① 판정 정의 대조 (config/definitions.yaml vs ci/gate/expected.yaml)")
    ok, msgs = _check_definitions(args.warn_pending)
    for m in msgs:
        print(m)
    if ok:
        print("  → 통과")
    else:
        print("  → 실패")
        overall = False

    print()
    print("=" * 60)
    print("①′ 운영 조정 검사 (config/operational.initial.yaml)")
    ok, msgs = _check_operational(args.warn_pending)
    for m in msgs:
        print(m)
    if ok:
        print("  → 통과")
    else:
        print("  → 실패")
        overall = False

    print()
    print("=" * 60)
    if overall:
        print("게이트 통과")
        return 0
    else:
        print("게이트 실패")
        return 1


if __name__ == "__main__":
    sys.exit(main())

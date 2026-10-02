"""
Q6: adapter_health 갱신 규칙 (4.9절, 7.8절) — processor._health.next_adapter_health를 검사한다
"""
from datetime import datetime, timedelta

import pytest

from processor._health import next_adapter_health

_T0 = datetime(2026, 9, 28, 0, 0, 0)


def _run(statuses):
    """순서대로 상태를 넣고 각 단계의 행을 돌려준다"""
    h, out = None, []
    for i, (status, retried) in enumerate(statuses):
        h = next_adapter_health(h, "dtRecent", status, _T0 + timedelta(minutes=i), retried=retried)
        out.append(h)
    return out


def test_Q6_sequence():
    """OK → NET_ERROR → NET_ERROR → PARSE_FAILURE → OK_EMPTY
    last_success_utc는 1·5번째에만 갱신, consecutive_failures는 0→1→2→2→0"""
    hs = _run([("OK", False), ("NET_ERROR", False), ("NET_ERROR", False),
               ("PARSE_FAILURE", False), ("OK_EMPTY", False)])
    assert [h["consecutive_failures"] for h in hs] == [0, 1, 2, 2, 0]
    assert hs[0]["last_success_utc"] == _T0
    assert hs[3]["last_success_utc"] == _T0                       # 파싱 실패는 성공 시각을 갱신하지 않는다
    assert hs[4]["last_success_utc"] == _T0 + timedelta(minutes=4)
    assert hs[2]["last_failure_utc"] == _T0 + timedelta(minutes=2)


def test_Q6_timeout_retry_recovered():
    """05 후 재시도 성공 — 저장 원문은 재시도 응답이라 최종 상태 OK + _retried → retry_recovered 1 증가, 실패 아님"""
    h = next_adapter_health(None, "dtRecent", "OK", _T0, retried=True)
    assert h["retry_recovered"] == 1
    assert h["consecutive_failures"] == 0
    assert h["last_failure_utc"] is None


@pytest.mark.parametrize("retried", [True, False])
def test_Q6_timeout_no_recovery(retried):
    """최종 응답이 05(재시도 후에도 05) → 실패와 같게, 복구로 세지 않는다 (4.9절)"""
    h = next_adapter_health(None, "dtRecent", "TIMEOUT_05", _T0, retried=retried)
    assert h["consecutive_failures"] == 1
    assert h["last_failure_utc"] == _T0
    assert h["retry_recovered"] == 0


@pytest.mark.parametrize("status", [
    "SUSPENDED", "PARSE_FAILURE", "BAD_REQUEST",
    "NO_SERVICE", "KEY_ERROR", "QUOTA", "INCOMPLETE", "FILTER_IGNORED",
])
def test_Q6_neither_success_nor_failure(status):
    prev = {"adapter": "dtRecent", "last_success_utc": _T0, "last_failure_utc": None,
            "consecutive_failures": 2, "retry_recovered": 0}
    h = next_adapter_health(prev, "dtRecent", status, _T0 + timedelta(hours=1))
    assert h["last_success_utc"] == _T0
    assert h["consecutive_failures"] == 2
    assert prev["consecutive_failures"] == 2   # 입력 행은 바꾸지 않는다


def test_success_after_retry_counts_recovery():
    """재시도 후 성공(메타 _retried) → 성공 갱신 + retry_recovered 1 증가 (v1.5 12절 별도 카운터)"""
    h = next_adapter_health(None, "tide", "OK", _T0, retried=True)
    assert h["last_success_utc"] == _T0
    assert h["retry_recovered"] == 1
    assert h["consecutive_failures"] == 0

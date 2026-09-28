"""
Q6: adapter_health 갱신 규칙 (4.9절)
성공/실패/별도 분류별 갱신 규칙을 상태 이름으로 검사
"""
import pytest


# adapter_health 갱신 규칙 (③-11)
# - 성공 (OK·OK_EMPTY·NO_DATA): last_success_utc 갱신, consecutive_failures 초기화
# - 실패 (HTTP_ERROR·NET_ERROR): last_failure_utc 갱신, consecutive_failures 증가
# - 별도 TIMEOUT_05: 재시도 복구 → retry_recovered만 올리고 실패로 세지 않음
#                    재시도 후에도 05 → 실패와 같게
# - 어느 쪽도 아님 (SUSPEND·PARSE_FAILURE·BAD_REQUEST 등): last_success_utc 갱신 안 함

class _Health:
    def __init__(self):
        self.last_success_utc = None
        self.last_failure_utc = None
        self.consecutive_failures = 0
        self.retry_recovered = 0

    def update(self, status: str, retried: bool = False):
        if status in ("OK", "OK_EMPTY", "NO_DATA"):
            self.last_success_utc = "2026-09-28T00:00:00"
            self.consecutive_failures = 0
        elif status in ("HTTP_ERROR", "NET_ERROR"):
            self.last_failure_utc = "2026-09-28T00:00:01"
            self.consecutive_failures += 1
        elif status == "TIMEOUT_05":
            if retried:
                # 재시도 복구: retry_recovered만 올림, 실패 아님
                self.retry_recovered += 1
            else:
                # 재시도 후에도 05: 실패와 같게
                self.last_failure_utc = "2026-09-28T00:00:01"
                self.consecutive_failures += 1
        # SUSPENDED·PARSE_FAILURE·BAD_REQUEST·NO_SERVICE·KEY_ERROR·QUOTA 등: 아무것도 갱신 안 함


def test_Q6_sequence():
    """순서: OK→NET_ERROR→NET_ERROR→PARSE_FAILURE→OK_EMPTY"""
    h = _Health()

    h.update("OK")
    assert h.last_success_utc is not None
    assert h.consecutive_failures == 0

    h.update("NET_ERROR")
    assert h.consecutive_failures == 1

    h.update("NET_ERROR")
    assert h.consecutive_failures == 2

    prev_success = h.last_success_utc
    h.update("PARSE_FAILURE")
    # 파싱 실패는 성공 시각 갱신 안 함
    assert h.last_success_utc == prev_success
    assert h.consecutive_failures == 2  # 파싱 실패는 실패 카운트에도 안 포함

    h.update("OK_EMPTY")
    assert h.consecutive_failures == 0
    assert h.last_success_utc is not None


def test_Q6_timeout_retry_recovered():
    """TIMEOUT_05 재시도 성공 → retry_recovered만 증가, 실패 아님"""
    h = _Health()
    h.update("TIMEOUT_05", retried=True)
    assert h.retry_recovered == 1
    assert h.consecutive_failures == 0
    assert h.last_failure_utc is None


def test_Q6_timeout_no_recovery():
    """재시도 후에도 TIMEOUT_05 → 실패와 같게"""
    h = _Health()
    h.update("TIMEOUT_05", retried=False)
    assert h.consecutive_failures == 1

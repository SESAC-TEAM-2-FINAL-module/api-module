"""
adapter_health 갱신 규칙 (4.9절, 7.8절 Q6) — processor가 원문 해석 결과로 기록한다
  성공     OK·OK_EMPTY·NO_DATA            → last_success_utc 갱신, consecutive_failures 초기화
  실패     HTTP_ERROR·NET_ERROR          → last_failure_utc 갱신, consecutive_failures 증가
  별도     TIMEOUT_05                    → 재시도로 복구되면 retry_recovered만 올림. 재시도 후에도 05면 실패와 같게 *(제안)*
           재시도 후 성공(원문 메타 `_retried`)  → 성공으로 갱신하고 retry_recovered도 올림 (v1.5 12절 "복구 건은 실패로 세지 않되 별도 카운터")
  해당 없음 SUSPENDED·PARSE_FAILURE·BAD_REQUEST, 그리고 NO_SERVICE·KEY_ERROR·QUOTA·INCOMPLETE·FILTER_IGNORED *(제안)*
           → 아무것도 갱신하지 않는다 (성공 시각을 갱신하지 않아 신선도 임계로 드러난다)
"""
from __future__ import annotations

from datetime import datetime

_SUCCESS = frozenset({"OK", "OK_EMPTY", "NO_DATA"})
_FAILURE = frozenset({"HTTP_ERROR", "NET_ERROR"})


def next_adapter_health(
    prev: dict | None,
    adapter: str,
    status: str,
    now_utc: datetime,
    retried: bool = False,
) -> dict:
    """직전 adapter_health 행과 이번 응답 상태로 다음 행을 만든다. prev는 바꾸지 않는다"""
    h = {
        "adapter": adapter,
        "last_success_utc": None,
        "last_failure_utc": None,
        "consecutive_failures": 0,
        "retry_recovered": 0,
    }
    if prev:
        h.update({k: prev[k] for k in h if k in prev and k != "adapter"})
    h["consecutive_failures"] = int(h["consecutive_failures"] or 0)
    h["retry_recovered"] = int(h["retry_recovered"] or 0)

    if status in _SUCCESS:
        h["last_success_utc"] = now_utc
        h["consecutive_failures"] = 0
        if retried:
            h["retry_recovered"] += 1
    elif status in _FAILURE or status == "TIMEOUT_05":
        # 최종 응답이 05면 재시도(호출층 1회)로도 복구되지 않은 것 — 실패와 같게 센다 (4.9절 *(제안)*).
        # 재시도로 복구된 경우는 최종 응답이 정상이라 위 성공 분기에서 retry_recovered가 오른다
        h["last_failure_utc"] = now_utc
        h["consecutive_failures"] += 1
    return h

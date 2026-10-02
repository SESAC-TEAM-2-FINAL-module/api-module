"""단계 간 알림의 계약 버전 검사 (2.2절) — 버전이 다르면 처리하지 않고 운영 이벤트로 남긴다."""
from __future__ import annotations

from datetime import datetime, timezone

QUEUE_CONTRACT = "queue-v1"


def accept_message(payload: dict, topic: str, repo) -> bool:
    """payload.schema가 이 모듈이 따르는 큐 계약이면 True. 아니면 CONTRACT_VERSION_MISMATCH를 쓰고 False."""
    if payload.get("schema") == QUEUE_CONTRACT:
        return True
    repo.insert_ops_events([{
        "event_type": "CONTRACT_VERSION_MISMATCH",
        "api": payload.get("api"),
        "occurred_at_utc": datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0),
        "detail": {"topic": topic, "schema": payload.get("schema"), "expected": QUEUE_CONTRACT},
    }])
    return False

"""
실행 ID — 입력 메시지 키에서 결정적으로 만드는 UUID v5 (2.2절, 개정 22 *(제안)*)

재전달 때 같은 실행 ID가 나와야 커밋 뒤 발행 실패에서 다시 처리해도 고유 키에 걸리지 않는다(검수 H2).
네임스페이스는 이 모듈 전용 고정값 — 바꾸면 같은 입력의 실행 ID가 달라진다.
"""
from __future__ import annotations

import uuid

# uuid5(NAMESPACE_URL, "urn:aquasentinel:api-module:run-id") — 값으로 고정해 둔다
RUN_ID_NAMESPACE = uuid.UUID("b0847faf-19cc-527a-a9a6-91c3b1250a10")


def run_id_from(name: str) -> str:
    """이름(입력 키) → 36자 UUID 문자열"""
    return str(uuid.uuid5(RUN_ID_NAMESPACE, name))

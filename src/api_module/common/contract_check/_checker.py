"""기동 시 계약 버전 검사 (2.1절). 테이블 검사(B4)는 I-6(repository)이 구현."""
from __future__ import annotations


def check_contract_version(label: str, expected: str, actual: str) -> None:
    """
    기대 버전과 실제 버전이 다르면 기동 멈춤.
    옛 형식을 새 형식으로 조용히 읽지 않는다.
    """
    if expected != actual:
        raise SystemExit(
            f"계약 버전 불일치 [{label}]: 기대={expected!r} 실제={actual!r}. "
            "조용히 읽지 않는다."
        )

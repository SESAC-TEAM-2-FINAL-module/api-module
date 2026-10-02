"""빈 해역 시드 기동 검사 (개정 19 — I-15, common-core skill ③-9)."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from common.repository.base import AbstractRepository


def check_seed_tables(repo: AbstractRepository, tables: list[str]) -> None:
    """주어진 표 중 0행인 것이 있으면 SystemExit으로 기동을 멈추고 표 이름을 보고한다."""
    empty = [tbl for tbl in tables if repo.count_table_rows(tbl) == 0]
    if empty:
        raise SystemExit(f"해역 시드 표가 비었다 — 기동 멈춤: {', '.join(empty)}")

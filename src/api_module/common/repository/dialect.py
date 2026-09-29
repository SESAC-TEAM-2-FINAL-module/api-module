"""
DB 방언 분기 — upsert, 대량 적재.
이 파일 밖에서 'postgresql'·'mysql' 문자열을 쓰지 않는다 (repository skill ⑤).
"""
from __future__ import annotations

from sqlalchemy import Table
from sqlalchemy.engine import Connection


def upsert(
    conn: Connection,
    table: Table,
    rows: list[dict],
    conflict_keys: list[str],
    update_cols: list[str] | None = None,
) -> None:
    """
    행 목록을 충돌 키 기준으로 upsert한다.
    update_cols 미지정 시 conflict_keys 외 모든 컬럼을 갱신한다.
    update_cols=[] 이면 DO NOTHING / INSERT IGNORE.
    rows가 비어있으면 아무것도 하지 않는다.
    """
    if not rows:
        return

    # 테이블 컬럼에 없는 키(_type 등 메타 필드) 자동 제거
    col_names = {c.name for c in table.columns}
    rows = [{k: v for k, v in r.items() if k in col_names} for r in rows]

    if update_cols is None:
        key_set = set(conflict_keys)
        update_cols = [c.name for c in table.columns if c.name not in key_set]

    # 같은 배치에 중복 충돌 키가 있으면 PostgreSQL이 오류를 낸다 — 마지막 값을 유지
    seen: dict = {}
    for row in rows:
        k = tuple(row.get(ck) for ck in conflict_keys)
        seen[k] = row
    rows = list(seen.values())

    dialect_name = conn.dialect.name
    if dialect_name == "postgresql":
        _upsert_pg(conn, table, rows, conflict_keys, update_cols)
    elif dialect_name == "mysql":
        _upsert_my(conn, table, rows, update_cols)
    else:
        raise SystemExit(f"지원하지 않는 DB 방언: {dialect_name!r}")


def insert_only(conn: Connection, table: Table, rows: list[dict]) -> None:
    """중복 무시 없이 단순 INSERT. ops_events처럼 고유 키 없는 로그 테이블용."""
    if not rows:
        return
    conn.execute(table.insert(), rows)


def _upsert_pg(
    conn: Connection,
    table: Table,
    rows: list[dict],
    conflict_keys: list[str],
    update_cols: list[str],
) -> None:
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    stmt = pg_insert(table).values(rows)
    if update_cols:
        update_dict = {col: stmt.excluded[col] for col in update_cols}
        stmt = stmt.on_conflict_do_update(
            index_elements=conflict_keys,
            set_=update_dict,
        )
    else:
        stmt = stmt.on_conflict_do_nothing(index_elements=conflict_keys)
    conn.execute(stmt)


def _upsert_my(
    conn: Connection,
    table: Table,
    rows: list[dict],
    update_cols: list[str],
) -> None:
    from sqlalchemy.dialects.mysql import insert as my_insert

    stmt = my_insert(table).values(rows)
    if update_cols:
        update_dict = {col: stmt.inserted[col] for col in update_cols}
        stmt = stmt.on_duplicate_key_update(**update_dict)
    conn.execute(stmt)

"""
DB 방언 분기 — upsert, 대량 적재, DDL 생성본.
이 파일 밖에서 'postgresql'·'mysql' 문자열을 쓰지 않는다 (repository skill ⑤).
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import Table
from sqlalchemy.engine import Connection

_MAX_BIND_PARAMS = 60_000   # 한도 65,535보다 여유를 둔다


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
    if dialect_name not in ("postgresql", "mysql"):
        raise SystemExit(f"지원하지 않는 DB 방언: {dialect_name!r}")

    # 한 문장의 바인드 매개변수 한도 — PostgreSQL·MySQL 모두 65,535. 행을 나눠 보낸다 (정선 1년 원문 ≈ 2.8만 행)
    per_row = max(1, len(rows[0]))
    chunk = max(1, _MAX_BIND_PARAMS // per_row)
    for i in range(0, len(rows), chunk):
        part = rows[i:i + chunk]
        if dialect_name == "postgresql":
            _upsert_pg(conn, table, part, conflict_keys, update_cols)
        else:
            _upsert_my(conn, table, part, conflict_keys, update_cols)


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
    conflict_keys: list[str],
    update_cols: list[str],
) -> None:
    from sqlalchemy.dialects.mysql import insert as my_insert

    stmt = my_insert(table).values(rows)
    if update_cols:
        update_dict = {col: stmt.inserted[col] for col in update_cols}
    else:
        # "있으면 그대로" — 키 열을 자기 값으로 두는 무변경 갱신. INSERT IGNORE는 CHECK 위반까지 경고로 삼키므로 쓰지 않는다
        update_dict = {conflict_keys[0]: table.c[conflict_keys[0]]}
    stmt = stmt.on_duplicate_key_update(**update_dict)
    conn.execute(stmt)


# ── DDL 생성본 (contracts/tables/) — 적용은 DB 소유 측, 마이그레이션 없음 (5.4절) ──────────

_CONTRACTS_DIR = Path(__file__).parents[4] / "contracts" / "tables"


def _ddl(sa_dialect, header: list[str], table_suffix: str, out_path: Path) -> str:
    from sqlalchemy.schema import CreateIndex, CreateTable
    from . import tables as t
    parts = [*header, ""]
    for tbl in t.metadata.sorted_tables:
        ddl = str(CreateTable(tbl).compile(dialect=sa_dialect)).strip().rstrip(";")
        parts.append(ddl + table_suffix + ";")
        for idx in tbl.indexes:
            if not idx.unique:  # unique 인덱스는 CREATE TABLE에 포함됨
                parts.append(str(CreateIndex(idx).compile(dialect=sa_dialect)).strip() + ";")
        parts.append("")
    sql = "\n".join(parts)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(sql, encoding="utf-8")
    return sql


def generate_ddl_pg(out_path: Path | None = None) -> str:
    """PostgreSQL DDL 생성본을 반환하고 out_path(기본 contracts/tables/schema_pg.sql)에 저장한다."""
    from sqlalchemy.dialects.postgresql import dialect as PGDialect
    return _ddl(PGDialect(), [
        "-- PostgreSQL DDL — 생성본 (tables.py에서 자동 생성, 직접 수정 금지)",
        "-- DB 소유 측이 적용한다. 마이그레이션 코드 없음 (5.4절)",
    ], "", out_path or (_CONTRACTS_DIR / "schema_pg.sql"))


def generate_ddl_my(out_path: Path | None = None) -> str:
    """MySQL 8.0 DDL 생성본을 반환하고 out_path(기본 contracts/tables/schema_my.sql)에 저장한다."""
    from sqlalchemy.dialects.mysql import dialect as MyDialect
    return _ddl(MyDialect(), [
        "-- MySQL 8.0 DDL — 생성본 (tables.py에서 자동 생성, 직접 수정 금지)",
        "-- DB 소유 측이 적용한다. 마이그레이션 코드 없음 (5.4절)",
        "-- charset=utf8mb4 collate=utf8mb4_0900_ai_ci (NO PAD, 뒤 공백 구분)",
    ], "\nCHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci", out_path or (_CONTRACTS_DIR / "schema_my.sql"))


# ── 시드 적용 SQL 생성본 (개정 19, 4.3절) — 결정적 출력 ─────────────────────────

def _sq(s: str, backslash: bool = False) -> str:
    """SQL 문자열 리터럴. 작은따옴표는 두 번 쓴다. MySQL(기본 모드)은 백슬래시도 이스케이프 문자라 두 번 쓴다"""
    if backslash:
        s = s.replace("\\", "\\\\")
    return "'" + s.replace("'", "''") + "'"


def _gen_seed_sql(
    header: list[str],
    begin_stmt: str,
    bool_true: str,
    bool_false: str,
    out_path: Path,
    backslash_escape: bool = False,
) -> str:
    import hashlib
    import json as _json
    from common.seeds import _SEEDS_DIR, read_areas, read_area_aliases, read_axis_coverage

    def _sha(fname: str) -> str:
        # 줄바꿈을 LF로 맞춘 내용의 해시 — core.autocrlf 체크아웃(CRLF)에서도 같은 값
        return hashlib.sha256((_SEEDS_DIR / fname).read_bytes().replace(b"\r\n", b"\n")).hexdigest()

    def _q(v: str) -> str:
        return _sq(v, backslash_escape)

    lines = header + [
        f"-- areas.yaml sha256: {_sha('areas.yaml')}",
        f"-- area_aliases.yaml sha256: {_sha('area_aliases.yaml')}",
        f"-- axis_coverage.yaml sha256: {_sha('axis_coverage.yaml')}",
        "",
        begin_stmt,
        "",
        "DELETE FROM axis_coverage;",
        "DELETE FROM area_aliases;",
        "DELETE FROM areas;",
        "",
    ]

    # areas — PK 순 (area_id)
    areas = sorted(read_areas(), key=lambda r: r["area_id"])
    lines.append("INSERT INTO areas (area_id, name, center_lat, center_lng, radius_km) VALUES")
    for i, row in enumerate(areas):
        suffix = ";" if i == len(areas) - 1 else ","
        lines.append(
            f"  ({_q(row['area_id'])}, {_q(row['name'])}, "
            f"{repr(float(row['center_lat']))}, {repr(float(row['center_lng']))}, "
            f"{repr(float(row['radius_km']))}){suffix}"
        )
    lines.append("")

    # area_aliases — PK 순 (alias_key)
    aliases = sorted(read_area_aliases(), key=lambda r: r["alias_key"])
    lines.append("INSERT INTO area_aliases (alias_key, area_id, source) VALUES")
    for i, row in enumerate(aliases):
        suffix = ";" if i == len(aliases) - 1 else ","
        src = _q(row["source"]) if row.get("source") is not None else "NULL"
        lines.append(
            f"  ({_q(row['alias_key'])}, {_q(row['area_id'])}, {src}){suffix}"
        )
    lines.append("")

    # axis_coverage — PK 순 (area_id, axis)
    coverage = sorted(read_axis_coverage(), key=lambda r: (r["area_id"], r["axis"]))
    lines.append("INSERT INTO axis_coverage (area_id, axis, covered, season_months, reason) VALUES")
    for i, row in enumerate(coverage):
        suffix = ";" if i == len(coverage) - 1 else ","
        covered = bool_true if row.get("covered") else bool_false
        months_val = row.get("season_months")
        months = _q(_json.dumps(months_val)) if months_val is not None else "NULL"
        reason = _q(row["reason"]) if row.get("reason") is not None else "NULL"
        lines.append(
            f"  ({_q(row['area_id'])}, {_q(row['axis'])}, {covered}, {months}, {reason}){suffix}"
        )
    lines.append("")
    lines.append("COMMIT;")
    lines.append("")

    sql = "\n".join(lines)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # LF로 쓴다 — 어느 OS에서 만들어도 DB 소유 측이 받는 바이트가 같다
    out_path.write_bytes(sql.encode("utf-8"))
    return sql


def generate_seed_sql_pg(out_path: Path | None = None) -> str:
    """PostgreSQL 시드 적용 SQL 생성본을 반환하고 contracts/tables/seeds_pg.sql에 저장한다."""
    return _gen_seed_sql(
        header=[
            "-- PostgreSQL 시드 SQL — 생성본 (common/seeds.py에서 자동 생성, 직접 수정 금지)",
            "-- DB 소유 측이 적용한다. 마이그레이션 코드 없음 (4.3절, 개정 19)",
            "-- 시드 변경 시 generate_seed_sql_pg()를 다시 실행해 이 파일을 갱신한다",
        ],
        begin_stmt="BEGIN;",
        bool_true="TRUE",
        bool_false="FALSE",
        out_path=out_path or (_CONTRACTS_DIR / "seeds_pg.sql"),
    )


def generate_seed_sql_my(out_path: Path | None = None) -> str:
    """MySQL 8.0 시드 적용 SQL 생성본을 반환하고 contracts/tables/seeds_my.sql에 저장한다."""
    return _gen_seed_sql(
        header=[
            "-- MySQL 8.0 시드 SQL — 생성본 (common/seeds.py에서 자동 생성, 직접 수정 금지)",
            "-- DB 소유 측이 적용한다. 마이그레이션 코드 없음 (4.3절, 개정 19)",
            "-- 시드 변경 시 generate_seed_sql_my()를 다시 실행해 이 파일을 갱신한다",
        ],
        begin_stmt="START TRANSACTION;",
        bool_true="1",
        bool_false="0",
        out_path=out_path or (_CONTRACTS_DIR / "seeds_my.sql"),
        backslash_escape=True,
    )

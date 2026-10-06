"""
7.4절 DB 검사 — 필수 항목
- DDL 생성본이 오류 없이 적용되고 모델과 일치
- 기동 시 검사: 테이블·컬럼·고유 키 누락 → SystemExit
- 생성본 DDL에 고유 키(PK·고유 제약·고유 인덱스)가 모두 있고, upsert 충돌 키가 모델의 고유 키와 같다
- PG·MY DDL 파일 생성 확인 (내용 있음)
"""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text


CONTRACTS = Path(__file__).parents[2] / "contracts" / "tables"


# ─────────────────────────────────────────────────────────────────────────────
# DDL 적용 + 스키마 일치 검사
# ─────────────────────────────────────────────────────────────────────────────

class TestDdlAndSchema:
    def test_all_tables_exist(self, schema_engine):
        """생성본 DDL 적용 후 metadata의 모든 테이블이 DB에 있다."""
        from common.repository.tables import metadata
        insp = inspect(schema_engine)
        existing = set(insp.get_table_names())
        for table_name in metadata.tables:
            assert table_name in existing, f"테이블 없음: {table_name}"

    def test_all_columns_exist(self, schema_engine):
        """각 테이블의 모든 컬럼이 DB에 있다."""
        from common.repository.tables import metadata
        insp = inspect(schema_engine)
        for table_name, table_obj in metadata.tables.items():
            db_cols = {c["name"] for c in insp.get_columns(table_name)}
            for col in table_obj.columns:
                assert col.name in db_cols, f"컬럼 없음: {table_name}.{col.name}"

    def test_all_unique_keys_exist(self, schema_engine):
        """모델의 고유 키가 생성본 DDL을 적용한 DB에 모두 있다 — upsert ON CONFLICT의 전제 (5.3절)"""
        from common.repository.sql import _db_unique_keys
        from common.repository.tables import metadata, unique_keys
        insp = inspect(schema_engine)
        missing = []
        for name, tbl in metadata.tables.items():
            db_keys = _db_unique_keys(insp, name)
            missing += [f"{name}{key}" for key in unique_keys(tbl) if frozenset(key) not in db_keys]
        assert not missing, f"생성본 DDL에 없는 고유 키: {missing}"

    def test_upsert_twice_keeps_one_row(self, schema_engine, clean_db):
        """같은 키로 두 번 upsert하면 한 행 — 고유 키가 DB에 있어야 성립한다"""
        from datetime import datetime
        from common.repository.sql import SqlRepository
        repo = SqlRepository(schema_engine)
        row = {"farm_id": "f1", "axis": "water_temp", "state": "NORMAL", "reason": None,
               "basis_utc": None, "last_checked_utc": datetime(2026, 10, 6, 0, 0, 0)}
        repo.upsert_axis_status([row])
        repo.upsert_axis_status([{**row, "state": "STALE"}])
        with schema_engine.connect() as conn:
            got = conn.execute(text("SELECT state FROM axis_status WHERE farm_id = 'f1'")).scalars().all()
        assert got == ["STALE"]

    def test_check_schema_passes(self, schema_engine):
        """스키마 일치 시 check_schema()가 예외 없이 통과한다."""
        from common.repository.sql import SqlRepository
        repo = SqlRepository(schema_engine)
        repo.check_schema()  # raises SystemExit on mismatch


# ─────────────────────────────────────────────────────────────────────────────
# 기동 시 검사 — 누락 시 SystemExit (B4)
# ─────────────────────────────────────────────────────────────────────────────

class TestStartupCheck:
    def test_missing_table_raises(self, pg_engine):
        """테이블을 하나 삭제하면 check_schema()가 SystemExit을 발생시킨다."""
        from common.repository.tables import metadata
        from common.repository.sql import SqlRepository

        # 별도 스키마를 만든 임시 엔진으로 테스트
        with pg_engine.connect() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS chk_test"))
            conn.commit()

        tmp_engine = create_engine(
            pg_engine.url, connect_args={"options": "-csearch_path=chk_test"}
        )
        try:
            metadata.create_all(tmp_engine)
            # 테이블 하나 삭제
            with tmp_engine.begin() as conn:
                conn.execute(text("DROP TABLE chk_test.ops_events CASCADE"))

            repo = SqlRepository(tmp_engine)
            with pytest.raises(SystemExit) as exc:
                repo.check_schema()
            assert "ops_events" in str(exc.value)
        finally:
            with pg_engine.begin() as conn:
                conn.execute(text("DROP SCHEMA chk_test CASCADE"))
            tmp_engine.dispose()

    def test_missing_column_raises(self, pg_engine):
        """컬럼을 하나 삭제하면 check_schema()가 SystemExit을 발생시킨다."""
        from common.repository.tables import metadata
        from common.repository.sql import SqlRepository

        with pg_engine.connect() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS chk_col"))
            conn.commit()

        tmp_engine = create_engine(
            pg_engine.url, connect_args={"options": "-csearch_path=chk_col"}
        )
        try:
            metadata.create_all(tmp_engine)
            with tmp_engine.begin() as conn:
                conn.execute(text("ALTER TABLE chk_col.stations DROP COLUMN sea_area"))

            repo = SqlRepository(tmp_engine)
            with pytest.raises(SystemExit) as exc:
                repo.check_schema()
            assert "sea_area" in str(exc.value)
        finally:
            with pg_engine.begin() as conn:
                conn.execute(text("DROP SCHEMA chk_col CASCADE"))
            tmp_engine.dispose()


    def test_missing_unique_key_raises(self, pg_engine, apply_ddl):
        """생성본 DDL에서 고유 인덱스 하나를 지우면 check_schema()가 없는 키를 보고하고 멈춘다"""
        from common.repository.sql import SqlRepository

        with pg_engine.connect() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS chk_key"))
            conn.commit()
        tmp_engine = create_engine(
            pg_engine.url, connect_args={"options": "-csearch_path=chk_key"}
        )
        try:
            apply_ddl(tmp_engine)
            repo = SqlRepository(tmp_engine)
            repo.check_schema()      # 지우기 전에는 통과
            with tmp_engine.begin() as conn:
                conn.execute(text("DROP INDEX chk_key.pk_axis_status"))
            with pytest.raises(SystemExit) as exc:
                repo.check_schema()
            assert "axis_status(farm_id, axis)" in str(exc.value)
        finally:
            with pg_engine.begin() as conn:
                conn.execute(text("DROP SCHEMA chk_key CASCADE"))
            tmp_engine.dispose()

    def test_key_by_other_name_passes(self, pg_engine, apply_ddl):
        """키가 이름이 다른 고유 제약으로 있어도 통과한다 — 키는 컬럼 조합으로 본다"""
        from common.repository.sql import SqlRepository

        with pg_engine.connect() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS chk_key2"))
            conn.commit()
        tmp_engine = create_engine(
            pg_engine.url, connect_args={"options": "-csearch_path=chk_key2"}
        )
        try:
            apply_ddl(tmp_engine)
            with tmp_engine.begin() as conn:
                conn.execute(text("DROP INDEX chk_key2.pk_axis_status"))
                conn.execute(text(
                    "ALTER TABLE chk_key2.axis_status ADD CONSTRAINT uq_other UNIQUE (axis, farm_id)"))
            SqlRepository(tmp_engine).check_schema()
        finally:
            with pg_engine.begin() as conn:
                conn.execute(text("DROP SCHEMA chk_key2 CASCADE"))
            tmp_engine.dispose()


# ─────────────────────────────────────────────────────────────────────────────
# DDL 파일 생성 확인 (7.4절)
# ─────────────────────────────────────────────────────────────────────────────

class TestDdlFiles:
    """DDL 파일 생성 검사 — DB 연결 불필요, dialect 컴파일만 사용."""

    def test_pg_ddl_generated(self):
        """PostgreSQL DDL 파일이 생성되고 내용이 있다."""
        from common.repository import generate_ddl_pg
        sql = generate_ddl_pg()
        assert len(sql) > 500
        path = CONTRACTS / "schema_pg.sql"
        assert path.exists()
        assert path.stat().st_size > 0
        assert "CREATE TABLE" in path.read_text("utf-8")

    def test_my_ddl_generated(self):
        """MySQL DDL 파일이 생성되고 내용이 있다."""
        from common.repository import generate_ddl_my
        sql = generate_ddl_my()
        assert len(sql) > 500
        path = CONTRACTS / "schema_my.sql"
        assert path.exists()
        assert path.stat().st_size > 0
        content = path.read_text("utf-8")
        assert "CREATE TABLE" in content
        assert "utf8mb4" in content

    def test_unique_indexes_in_both_ddl(self):
        """모델의 고유 인덱스가 두 생성본 모두에 CREATE UNIQUE INDEX로 있다 (DB 없이)"""
        from common.repository import generate_ddl_my, generate_ddl_pg
        from common.repository.tables import metadata
        pg, my = generate_ddl_pg(), generate_ddl_my()
        names = [i.name for tb in metadata.sorted_tables for i in tb.indexes if i.unique]
        assert names
        for n in names:
            assert f"CREATE UNIQUE INDEX {n} " in pg, f"schema_pg.sql에 {n} 없음"
            assert f"CREATE UNIQUE INDEX {n} " in my, f"schema_my.sql에 {n} 없음"


class TestUpsertKeys:
    """upsert 충돌 키 = 모델의 고유 키 — 코드 정적 검사 (5.3절, DB 불필요)"""

    def test_every_upsert_key_is_a_model_key(self):
        import ast
        from common.repository import tables as t
        src = Path(__file__).parents[2] / "src" / "api_module" / "common" / "repository" / "sql.py"
        tree = ast.parse(src.read_text("utf-8"))
        calls = [n for n in ast.walk(tree)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                 and n.func.attr == "upsert" and isinstance(n.func.value, ast.Name)
                 and n.func.value.id == "d"]
        assert len(calls) >= 20
        bad = []
        for c in calls:
            tbl_node, key_node = c.args[1], c.args[3]
            assert isinstance(tbl_node, ast.Attribute), f"{c.lineno}행: 표를 t.<이름>으로 쓰지 않음"
            key = tuple(ast.literal_eval(key_node))
            tbl = getattr(t, tbl_node.attr)
            if frozenset(key) not in {frozenset(k) for k in t.unique_keys(tbl)}:
                bad.append(f"{c.lineno}행 {tbl.name}{key}")
        assert not bad, f"모델 고유 키가 아닌 upsert 충돌 키: {bad}"

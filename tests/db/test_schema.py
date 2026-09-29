"""
7.4절 DB 검사 — 필수 항목
- DDL 생성본이 오류 없이 적용되고 모델과 일치
- 기동 시 검사: 테이블·컬럼 누락 → SystemExit
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
        """create_all 후 metadata의 모든 테이블이 DB에 있다."""
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


# ─────────────────────────────────────────────────────────────────────────────
# DDL 파일 생성 확인 (7.4절)
# ─────────────────────────────────────────────────────────────────────────────

class TestDdlFiles:
    """DDL 파일 생성 검사 — DB 연결 불필요, dialect 컴파일만 사용."""

    def test_pg_ddl_generated(self):
        """PostgreSQL DDL 파일이 생성되고 내용이 있다."""
        from common.repository.sql import generate_ddl_pg
        sql = generate_ddl_pg()
        assert len(sql) > 500
        path = CONTRACTS / "schema_pg.sql"
        assert path.exists()
        assert path.stat().st_size > 0
        assert "CREATE TABLE" in path.read_text("utf-8")

    def test_my_ddl_generated(self):
        """MySQL DDL 파일이 생성되고 내용이 있다."""
        from common.repository.sql import generate_ddl_my
        sql = generate_ddl_my()
        assert len(sql) > 500
        path = CONTRACTS / "schema_my.sql"
        assert path.exists()
        assert path.stat().st_size > 0
        content = path.read_text("utf-8")
        assert "CREATE TABLE" in content
        assert "utf8mb4" in content

"""
DB 테스트 픽스처 — PostgreSQL testcontainer (7.4절)
고른 DB: postgresql+psycopg (확정, memory 참조)
"""
from __future__ import annotations

import os
from pathlib import Path
import pytest
from sqlalchemy import create_engine, text, Engine

# .env 로드 (TEST_DATABASE_URL 등)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parents[2] / ".env", override=False)
except ImportError:
    pass

# testcontainers 임포트 — test 의존성 (community 패키지 우선)
try:
    from testcontainers.community.postgres import PostgresContainer
    _HAS_CONTAINER = True
except ImportError:
    try:
        from testcontainers.postgres import PostgresContainer
        _HAS_CONTAINER = True
    except ImportError:
        _HAS_CONTAINER = False


def _url_from_env() -> str | None:
    """TEST_DATABASE_URL 환경변수에서 연결 문자열 로드 (값 출력 금지)."""
    return os.environ.get("TEST_DATABASE_URL")


@pytest.fixture(scope="session")
def pg_engine() -> Engine:
    """
    세션 범위 PostgreSQL 엔진.
    TEST_DATABASE_URL 설정 시 해당 DB 사용, 없으면 testcontainer 기동.
    """
    url = _url_from_env()
    if url:
        engine = create_engine(url)
        yield engine
        engine.dispose()
        return

    if not _HAS_CONTAINER:
        pytest.skip("testcontainers 미설치 & TEST_DATABASE_URL 미설정")

    with PostgresContainer("postgres:16-alpine") as pg:
        # testcontainer 기본 URL은 psycopg2 — 이 환경은 psycopg(v3)만 설치됨
        url = pg.get_connection_url().replace(
            "postgresql+psycopg2://", "postgresql+psycopg://", 1
        )
        engine = create_engine(url)
        yield engine
        engine.dispose()


@pytest.fixture(scope="session")
def schema_engine(pg_engine: Engine) -> Engine:
    """
    tables.py 메타데이터를 적용한 엔진.
    DDL 적용은 모델 기반 create_all — 생성본 DDL 파일 검증은 별도 테스트.
    """
    from common.repository.tables import metadata
    metadata.create_all(pg_engine)
    yield pg_engine
    # 정리: 모든 테이블 삭제 (세션 종료 시)
    metadata.drop_all(pg_engine)


@pytest.fixture()
def repo(schema_engine: Engine):
    """SqlRepository 인스턴스 — 각 테스트마다 독립 트랜잭션."""
    from common.repository.sql import SqlRepository
    return SqlRepository(schema_engine)


@pytest.fixture()
def clean_db(schema_engine: Engine):
    """각 테스트 전후로 테이블 데이터를 비운다 (스키마 유지)."""
    from common.repository.tables import metadata
    with schema_engine.begin() as conn:
        for tbl in reversed(metadata.sorted_tables):
            conn.execute(tbl.delete())
    yield
    with schema_engine.begin() as conn:
        for tbl in reversed(metadata.sorted_tables):
            conn.execute(tbl.delete())


@pytest.fixture(scope="class")
def clean_db_class(schema_engine: Engine):
    """class 스코프 클린업 — class 내 첫 테스트 전·마지막 테스트 후 한 번씩."""
    from common.repository.tables import metadata
    with schema_engine.begin() as conn:
        for tbl in reversed(metadata.sorted_tables):
            conn.execute(tbl.delete())
    yield
    with schema_engine.begin() as conn:
        for tbl in reversed(metadata.sorted_tables):
            conn.execute(tbl.delete())


def _fake_raw_id(engine: Engine, storage_key: str = "test_key") -> int:
    """raw_index에 더미 행 삽입 후 생성된 id를 반환한다."""
    from common.repository import SqlRepository
    repo = SqlRepository(engine)
    from datetime import datetime, timezone
    return repo.insert_raw_index({
        "api": "test",
        "tag": "test",
        "storage_key": storage_key,
        "fetched_at_utc": datetime.now(timezone.utc).replace(tzinfo=None),
        "http_status": 200,
        "body_sha256": None,
        "body_bytes": None,
        "precheck_code": None,
    })


@pytest.fixture()
def fake_raw_id(schema_engine: Engine):
    """_fake_raw_id 헬퍼를 fixture로 노출 — test_upsert.py에서 사용."""
    def _make(storage_key: str = "test_key") -> int:
        return _fake_raw_id(schema_engine, storage_key)
    return _make

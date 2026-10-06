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


_SCHEMA_PG = Path(__file__).parents[2] / "contracts" / "tables" / "schema_pg.sql"


def apply_generated_ddl(engine: Engine) -> None:
    """
    커밋된 생성본 DDL(contracts/tables/schema_pg.sql)을 그대로 적용한다.
    모델 create_all이 아니라 DB 소유 측이 받는 파일로 스키마를 만든다 — DDL 검증을 겸한다 (repository skill, 7.4절)
    """
    sql = _SCHEMA_PG.read_text("utf-8")
    with engine.begin() as conn:
        for part in sql.split(";"):
            stmt = "\n".join(
                ln for ln in part.splitlines() if not ln.lstrip().startswith("--")
            ).strip()
            if stmt:
                conn.exec_driver_sql(stmt)


@pytest.fixture()
def apply_ddl():
    """생성본 DDL 적용 함수 — 별도 스키마(search_path)에 같은 파일로 스키마를 만들 때"""
    return apply_generated_ddl


@pytest.fixture(scope="session")
def schema_engine(pg_engine: Engine) -> Engine:
    """생성본 DDL을 적용한 엔진 (apply_generated_ddl)."""
    from common.repository.tables import metadata
    apply_generated_ddl(pg_engine)
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


# ─────────────────────────────────────────────────────────────────────────────
# I-12 — processor 경로 적재용 (원문 저장소 + processor 기동)
# ─────────────────────────────────────────────────────────────────────────────

FIXTURES_RAW = Path(__file__).parents[2] / "fixtures" / "raw"


@pytest.fixture()
def raw_store(tmp_path, monkeypatch):
    """임시 디스크 원문 저장소. put(api, tag, content) → 객체 키(raw.fetched.raw_id)"""
    import itertools
    import common.raw_store._store as store_mod
    store = store_mod.LocalDiskStore(str(tmp_path / "raw"))
    monkeypatch.setattr(store_mod, "_store", store)
    seq = itertools.count(1_790_000_000_000)

    class _Put:
        def put(self, api: str, tag: str, content: dict, day: str = "2026/09/20") -> str:
            key = f"raw/{api}/{day}/{next(seq)}_{tag}.json"
            store.put(key, content)
            return key

        def put_fixture(self, api: str, tag: str, glob: str) -> str:
            import json
            path = next(FIXTURES_RAW.glob(glob))
            content = json.loads(path.read_text("utf-8"))
            content.setdefault("http_status", content.get("http"))
            content.setdefault("fetched_at", "2026-09-20T00:00:00Z")
            return self.put(api, tag, content)

    return _Put()


@pytest.fixture()
def processor_up(schema_engine, clean_db):
    """processor 기동 — 실제 판정 정의 + 운영 조정 초기값 + 테스트 DB. (pm, repo) 반환"""
    import yaml
    import processor.main as pm
    from common.config import load_definitions
    from common.repository import SqlRepository
    pm._load_adapters()
    repo = SqlRepository(schema_engine)
    op = yaml.safe_load((Path(__file__).parents[2] / "config" / "operational.initial.yaml").read_text("utf-8"))
    pm.startup(definitions=load_definitions(), operational=op, repo=repo)
    return pm, repo


def count_rows(engine: Engine, table_name: str) -> int:
    from sqlalchemy import func, select
    from common.repository.tables import metadata
    with engine.connect() as conn:
        return conn.execute(select(func.count()).select_from(metadata.tables[table_name])).scalar_one()


# 합성 dtRecent 원문 — 저장소에 dtRecent 원문 픽스처가 없다 (I-12 보고서 기록)
TIDE_STATIONS = {   # fixtures/derived/stations.csv의 시연권역 관측소 좌표
    "DT_0014": (34.82777, 128.43472), "DT_0016": (34.74722, 127.76555), "DT_0029": (34.80138, 128.69916),
    "DT_0061": (34.92416, 128.06972), "DT_0026": (34.48111, 127.34277), "DT_0062": (35.1975, 128.57638),
    "DT_0063": (35.02417, 128.81093),
}


def tide_body(obs: list[tuple[str, str, float]], result_code: str = "00") -> str:
    """obs = [(관측소, KST 시각 'YYYY-MM-DD HH:MM:SS', 수온)] → data.go.kr 형식 JSON 본문"""
    import json
    items = []
    for code, kst, wt in obs:
        lat, lng = TIDE_STATIONS[code]
        items.append({"obsCode": code, "obsrvnDt": kst, "wtem": f"{wt:.3f}", "slntQty": "32.100",
                      "bscTdlvHgt": "120", "wspd": "3.2", "wdir": "180", "artmp": "26.0",
                      "lat": str(lat), "lot": str(lng)})
    body = {"items": {"item": items}, "totalCount": len(items), "numOfRows": len(items), "pageNo": 1} if items \
        else {"items": "", "totalCount": 0, "numOfRows": 0, "pageNo": 1}
    return json.dumps({"response": {"header": {"resultCode": result_code, "resultMsg": "NORMAL SERVICE."},
                                    "body": body}}, ensure_ascii=False)


def tide_raw(body: str | None, fetched_at: str = "2026-08-01T00:10:00Z", error: dict | None = None,
             retried: bool = False) -> dict:
    content = {"url": "https://example.invalid/dtRecent", "params": {"serviceKey": "***"},
               "http_status": None if error else 200, "final_url": None, "fetched_at": fetched_at,
               "body": body, "error": error}
    if retried:
        content["_retried"] = True
    return content


@pytest.fixture()
def tide():
    """합성 dtRecent 원문 도우미 — tide.body(...), tide.raw(...), tide.STATIONS"""
    import types
    return types.SimpleNamespace(body=tide_body, raw=tide_raw, STATIONS=TIDE_STATIONS)


@pytest.fixture()
def farm_sites_table(schema_engine):
    """웹 소유 farm_sites — 테스트 컨테이너에만 합성으로 만들고 지운다 (1.6·2.0.3절)"""
    from sqlalchemy import text
    with schema_engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE farm_sites (farm_id VARCHAR(64) PRIMARY KEY, lat DOUBLE PRECISION, "
            "lng DOUBLE PRECISION, active BOOLEAN, updated_at_utc TIMESTAMP)"))
        conn.execute(text("INSERT INTO farm_sites VALUES ('syn_gam_001', 34.68, 127.69, TRUE, '2026-07-01 00:00:00')"))
    yield ["syn_gam_001"]
    with schema_engine.begin() as conn:
        conn.execute(text("DROP TABLE farm_sites"))

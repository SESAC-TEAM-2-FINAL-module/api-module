"""
A3 시드 적재 DB 테스트 (확정 2026-10-01)
seeds/areas.yaml · area_aliases.yaml · axis_coverage.yaml → DB 적재 검증
"""
from __future__ import annotations

from sqlalchemy import func, select


_EXPECTED_AREAS = 8          # seeds/areas.yaml 해역 수
_EXPECTED_ALIASES = 15       # seeds/area_aliases.yaml 별칭 수
_EXPECTED_COVERAGE = 8       # seeds/axis_coverage.yaml 커버리지 선언 수


class TestSeedLoad:
    def test_load_seeds_no_error(self, repo, clean_db):
        """load_seeds() 가 예외 없이 완료된다."""
        from processor.adapters.bulletin._seed import load_seeds
        load_seeds(repo)  # raises on failure

    def test_areas_count(self, schema_engine, clean_db):
        """areas: 8개 해역이 적재된다."""
        from common.repository.sql import SqlRepository
        from common.repository.tables import areas as t
        from processor.adapters.bulletin._seed import load_seeds

        repo = SqlRepository(schema_engine)
        load_seeds(repo)

        with schema_engine.connect() as conn:
            cnt = conn.execute(select(func.count()).select_from(t)).scalar_one()
        assert cnt == _EXPECTED_AREAS, f"areas 행 수 {cnt} ≠ {_EXPECTED_AREAS}"

    def test_area_aliases_count(self, schema_engine, clean_db):
        """area_aliases: 15개 별칭이 적재된다."""
        from common.repository.sql import SqlRepository
        from common.repository.tables import area_aliases as t
        from processor.adapters.bulletin._seed import load_seeds

        repo = SqlRepository(schema_engine)
        load_seeds(repo)

        with schema_engine.connect() as conn:
            cnt = conn.execute(select(func.count()).select_from(t)).scalar_one()
        assert cnt == _EXPECTED_ALIASES, f"area_aliases 행 수 {cnt} ≠ {_EXPECTED_ALIASES}"

    def test_axis_coverage_count(self, schema_engine, clean_db):
        """axis_coverage: 8개 커버리지 선언이 적재된다."""
        from common.repository.sql import SqlRepository
        from common.repository.tables import axis_coverage as t
        from processor.adapters.bulletin._seed import load_seeds

        repo = SqlRepository(schema_engine)
        load_seeds(repo)

        with schema_engine.connect() as conn:
            cnt = conn.execute(select(func.count()).select_from(t)).scalar_one()
        assert cnt == _EXPECTED_COVERAGE, f"axis_coverage 행 수 {cnt} ≠ {_EXPECTED_COVERAGE}"

    def test_axis_coverage_all_red_tide(self, schema_engine, clean_db):
        """axis_coverage: 모든 행이 red_tide 축이다."""
        from common.repository.sql import SqlRepository
        from common.repository.tables import axis_coverage as t
        from processor.adapters.bulletin._seed import load_seeds

        repo = SqlRepository(schema_engine)
        load_seeds(repo)

        with schema_engine.connect() as conn:
            cnt = conn.execute(
                select(func.count()).select_from(t).where(t.c.axis == "red_tide")
            ).scalar_one()
        assert cnt == _EXPECTED_COVERAGE

    def test_load_seeds_idempotent(self, schema_engine, clean_db):
        """load_seeds()를 두 번 호출해도 행 수가 늘지 않는다 (upsert)."""
        from common.repository.sql import SqlRepository
        from common.repository.tables import areas as t
        from processor.adapters.bulletin._seed import load_seeds

        repo = SqlRepository(schema_engine)
        load_seeds(repo)
        load_seeds(repo)

        with schema_engine.connect() as conn:
            cnt = conn.execute(select(func.count()).select_from(t)).scalar_one()
        assert cnt == _EXPECTED_AREAS

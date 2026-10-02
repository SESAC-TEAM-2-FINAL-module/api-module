"""
I-15 SD4 — 시드 파일·생성본 검사 (DB 없음)
- area_aliases·axis_coverage의 area_id ⊂ areas.yaml
- 커밋 대상 contracts/tables/seeds_*.sql = 지금 시드로 만든 생성기 출력(바이트 단위)
"""
from __future__ import annotations

from pathlib import Path

CONTRACTS = Path(__file__).parents[2] / "contracts" / "tables"


class TestSD4SeedIntegrity:
    def test_area_aliases_area_ids_subset_of_areas(self):
        """area_aliases.yaml의 area_id가 모두 areas.yaml에 있다."""
        from common.seeds import read_areas, read_area_aliases
        area_ids = {r["area_id"] for r in read_areas()}
        for alias in read_area_aliases():
            assert alias["area_id"] in area_ids, (
                f"area_aliases {alias['alias_key']!r}.area_id={alias['area_id']!r} → areas.yaml에 없음"
            )

    def test_axis_coverage_area_ids_subset_of_areas(self):
        """axis_coverage.yaml의 area_id가 모두 areas.yaml에 있다."""
        from common.seeds import read_areas, read_axis_coverage
        area_ids = {r["area_id"] for r in read_areas()}
        for cov in read_axis_coverage():
            assert cov["area_id"] in area_ids, (
                f"axis_coverage ({cov['area_id']}, {cov['axis']}).area_id → areas.yaml에 없음"
            )

    def test_pg_seed_sql_byte_equal_to_committed(self, tmp_path):
        """커밋된 seeds_pg.sql 이 현재 시드로 만든 생성기 출력과 바이트 단위로 같다."""
        from common.repository import generate_seed_sql_pg
        committed_path = CONTRACTS / "seeds_pg.sql"
        assert committed_path.exists(), "contracts/tables/seeds_pg.sql 없음 — generate_seed_sql_pg()를 먼저 실행하라"
        # 바이트 비교 — 줄바꿈만 LF로 맞춘다(core.autocrlf 체크아웃은 CRLF로 풀린다)
        committed = committed_path.read_bytes().replace(b"\r\n", b"\n")
        fresh = generate_seed_sql_pg(out_path=tmp_path / "seeds_pg.sql").encode("utf-8")
        assert (tmp_path / "seeds_pg.sql").read_bytes() == fresh, "생성본을 LF로 쓰지 않았다"
        assert fresh == committed, (
            "seeds_pg.sql 이 현재 시드와 다르다 — 시드 변경 후 generate_seed_sql_pg()를 재실행하지 않았거나 "
            "SQL 파일을 직접 수정했다"
        )

    def test_my_seed_sql_byte_equal_to_committed(self, tmp_path):
        """커밋된 seeds_my.sql 이 현재 시드로 만든 생성기 출력과 바이트 단위로 같다."""
        from common.repository import generate_seed_sql_my
        committed_path = CONTRACTS / "seeds_my.sql"
        assert committed_path.exists(), "contracts/tables/seeds_my.sql 없음 — generate_seed_sql_my()를 먼저 실행하라"
        # 바이트 비교 — 줄바꿈만 LF로 맞춘다(core.autocrlf 체크아웃은 CRLF로 풀린다)
        committed = committed_path.read_bytes().replace(b"\r\n", b"\n")
        fresh = generate_seed_sql_my(out_path=tmp_path / "seeds_my.sql").encode("utf-8")
        assert (tmp_path / "seeds_my.sql").read_bytes() == fresh, "생성본을 LF로 쓰지 않았다"
        assert fresh == committed, (
            "seeds_my.sql 이 현재 시드와 다르다 — 시드 변경 후 generate_seed_sql_my()를 재실행하지 않았거나 "
            "SQL 파일을 직접 수정했다"
        )

    def test_pg_seed_sql_has_content(self):
        """seeds_pg.sql 이 비어 있지 않고 세 표 INSERT가 있다."""
        committed_path = CONTRACTS / "seeds_pg.sql"
        if not committed_path.exists():
            import pytest
            pytest.skip("seeds_pg.sql 없음 — generate_seed_sql_pg() 먼저 실행")
        content = committed_path.read_text("utf-8")
        assert "INSERT INTO areas" in content
        assert "INSERT INTO area_aliases" in content
        assert "INSERT INTO axis_coverage" in content
        assert "gyeongnam_tongyeong" in content
        assert "BEGIN;" in content
        assert "COMMIT;" in content

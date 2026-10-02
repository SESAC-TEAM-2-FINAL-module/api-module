"""
I-15 SD1·SD2·SD3 — 해역 시드 기동 검사·생성본 적용·seed-check (DB)
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import text


# ─────────────────────────────────────────────────────────────────────────────
# SD1 — 빈 시드 기동 검사
# ─────────────────────────────────────────────────────────────────────────────

class TestSD1EmptySeedStartup:
    def test_areas_empty_raises(self, repo, clean_db):
        """areas 0행이면 check_seed_tables가 SystemExit."""
        from common.contract_check import check_seed_tables
        with pytest.raises(SystemExit) as exc:
            check_seed_tables(repo, ["areas"])
        assert "areas" in str(exc.value)

    def test_axis_coverage_empty_raises(self, repo, clean_db):
        """areas는 있고 axis_coverage 0행이면 SystemExit."""
        from common.contract_check import check_seed_tables
        from common.seeds import read_areas
        repo.upsert_areas(read_areas())
        with pytest.raises(SystemExit) as exc:
            check_seed_tables(repo, ["areas", "axis_coverage"])
        assert "axis_coverage" in str(exc.value)

    def test_seeds_loaded_passes(self, repo, clean_db):
        """시드 적재 후 check_seed_tables 통과."""
        from common.contract_check import check_seed_tables
        from common.seeds import load_seeds
        load_seeds(repo)
        check_seed_tables(repo, ["areas", "axis_coverage"])  # no SystemExit

    def test_grading_check_tables(self, repo, clean_db):
        """grading 검사 대상은 ['areas']만."""
        from common.contract_check import check_seed_tables
        from common.seeds import read_areas
        repo.upsert_areas(read_areas())
        # areas만 있으면 grading 검사 통과
        check_seed_tables(repo, ["areas"])

    def test_both_checks_fail_if_areas_empty(self, repo, clean_db):
        """both grading·evaluation 검사 모두 areas=0이면 실패."""
        from common.contract_check import check_seed_tables
        # grading check
        with pytest.raises(SystemExit):
            check_seed_tables(repo, ["areas"])
        # evaluation check
        with pytest.raises(SystemExit):
            check_seed_tables(repo, ["areas", "axis_coverage"])


# ─────────────────────────────────────────────────────────────────────────────
# SD2 — 생성본 적용
# ─────────────────────────────────────────────────────────────────────────────

def _apply_seed_sql(engine, sql: str) -> None:
    """PG 시드 SQL을 테스트 컨테이너에 적용한다. BEGIN/COMMIT은 SQLAlchemy 트랜잭션으로 대체."""
    stmts = []
    for raw in sql.split(";"):
        s = raw.strip()
        # 빈 줄·주석 줄·트랜잭션 제어문 건너뜀
        if not s or s.startswith("--"):
            continue
        if s.upper() in ("BEGIN", "COMMIT", "START TRANSACTION"):
            continue
        stmts.append(s)
    with engine.begin() as conn:
        for stmt in stmts:
            conn.execute(text(stmt))


class TestSD2SeedSqlApplication:
    def test_pg_sql_result_equals_load_seeds(self, schema_engine, clean_db):
        """PG 생성본 적용 결과가 load_seeds 결과와 행 단위로 같다."""
        from common.repository import generate_seed_sql_pg
        from common.repository.sql import SqlRepository
        from common.seeds import load_seeds

        repo = SqlRepository(schema_engine)

        # 생성본 적용
        sql = generate_seed_sql_pg()
        _apply_seed_sql(schema_engine, sql)

        areas_sql = sorted(repo.get_areas(), key=lambda r: r["area_id"])
        aliases_sql = sorted(repo.get_area_aliases(), key=lambda r: r["alias_key"])

        # load_seeds 로 다시 적재 (덮어쓰기)
        load_seeds(repo)

        areas_load = sorted(repo.get_areas(), key=lambda r: r["area_id"])
        aliases_load = sorted(repo.get_area_aliases(), key=lambda r: r["alias_key"])

        assert len(areas_sql) == len(areas_load)
        for a, b in zip(areas_sql, areas_load):
            assert a["area_id"] == b["area_id"]
            assert a["name"] == b["name"]
            assert abs(float(a["center_lat"]) - float(b["center_lat"])) < 1e-9
            assert abs(float(a["center_lng"]) - float(b["center_lng"])) < 1e-9
            assert abs(float(a["radius_km"]) - float(b["radius_km"])) < 1e-9

        assert len(aliases_sql) == len(aliases_load)
        for a, b in zip(aliases_sql, aliases_load):
            assert a["alias_key"] == b["alias_key"]
            assert a["area_id"] == b["area_id"]

    def test_pg_sql_row_removed_disappears(self, schema_engine, clean_db):
        """시드에서 행 하나를 지운 생성본 적용 시 그 행이 DB에서 사라진다."""
        from common.repository import generate_seed_sql_my
        from common.repository.sql import SqlRepository
        from common.seeds import load_seeds
        import tempfile, pathlib

        repo = SqlRepository(schema_engine)
        load_seeds(repo)

        # areas에 행 하나 추가 (seed에는 없음 → DELETE로 제거됨)
        repo.upsert_areas([{
            "area_id": "test_extra_area",
            "name": "임시 테스트",
            "center_lat": 35.0,
            "center_lng": 128.0,
            "radius_km": 10.0,
        }])
        assert repo.count_table_rows("areas") == 9  # 8 + 1

        # PG 생성본 재적용 — DELETE로 임시 행 제거
        from common.repository import generate_seed_sql_pg
        tmp = pathlib.Path(tempfile.mktemp(suffix=".sql"))
        sql = generate_seed_sql_pg(out_path=tmp)
        _apply_seed_sql(schema_engine, sql)
        tmp.unlink(missing_ok=True)

        assert repo.count_table_rows("areas") == 8  # 임시 행 사라짐
        ids = {r["area_id"] for r in repo.get_areas()}
        assert "test_extra_area" not in ids

    def test_pg_sql_referenced_row_deleted_no_error(self, schema_engine, clean_db):
        """지운 행이 bulletin_detail_areas에서 참조돼도 DELETE 오류 없음 (FK 제약 없음)."""
        from common.repository.sql import SqlRepository
        from common.seeds import load_seeds
        from datetime import datetime, timezone
        import pathlib, tempfile

        repo = SqlRepository(schema_engine)
        load_seeds(repo)

        # bulletin_detail_areas에 area_id 참조 행 삽입
        raw_id = repo.insert_raw_index({
            "api": "redtideList", "tag": "test", "storage_key": "test/bda_ref",
            "fetched_at_utc": datetime.now(timezone.utc).replace(tzinfo=None),
            "http_status": 200, "body_sha256": None, "body_bytes": None, "precheck_code": None,
        })
        repo.upsert_bulletins([{
            "cod_news": "TEST_NEWS_001", "day_report": date.today(), "detail_count": 1,
            "grade": "NONE", "raw_id": raw_id,
        }])
        repo.upsert_bulletin_detail_areas([{
            "cod_news": "TEST_NEWS_001", "seq": 1, "part_no": 1,
            "area_key": "경남 통영", "area_id": "gyeongnam_tongyeong",
        }])

        # PG 생성본 재적용 — areas DELETE 포함 (FK 제약 없으므로 오류 없음)
        from common.repository import generate_seed_sql_pg
        tmp = pathlib.Path(tempfile.mktemp(suffix=".sql"))
        sql = generate_seed_sql_pg(out_path=tmp)
        _apply_seed_sql(schema_engine, sql)
        tmp.unlink(missing_ok=True)

        assert repo.count_table_rows("areas") == 8  # 정상 복원

    def test_mysql_seed_sql_generated(self, tmp_path):
        """MySQL 생성본이 생성되고 내용이 있다."""
        from common.repository import generate_seed_sql_my
        sql = generate_seed_sql_my(out_path=tmp_path / "seeds_my.sql")
        assert len(sql) > 200
        assert "gyeongnam_tongyeong" in sql
        assert "START TRANSACTION" in sql


# ─────────────────────────────────────────────────────────────────────────────
# SD3 — seed-check 대조 함수
# ─────────────────────────────────────────────────────────────────────────────

class TestSD3SeedCheck:
    def _defs(self, window_days: int = 30) -> dict:
        return {"bulletin": {"current_window_days": window_days}}

    def test_matching_seeds_no_diff(self, repo, clean_db):
        """시드와 같은 DB → 빈 목록."""
        from common.seeds import load_seeds, compare_seed_tables
        load_seeds(repo)
        diffs = compare_seed_tables(repo, self._defs(), ref_date=date.today())
        assert not diffs

    def test_changed_area_value(self, repo, clean_db):
        """areas 행 값 변경 → ① 보고."""
        from common.seeds import load_seeds, compare_seed_tables
        load_seeds(repo)
        repo.upsert_areas([{
            "area_id": "gyeongnam_tongyeong", "name": "변경된이름",
            "center_lat": 34.845, "center_lng": 128.435, "radius_km": 25.0,
        }])
        diffs = compare_seed_tables(repo, self._defs(), ref_date=date.today())
        assert any("[①]" in d and "gyeongnam_tongyeong" in d for d in diffs)

    def test_deleted_area_row(self, repo, clean_db):
        """areas 행 하나 삭제 (DB에서) → ① 보고."""
        from common.seeds import load_seeds, compare_seed_tables
        from sqlalchemy import text
        from common.repository.tables import metadata
        load_seeds(repo)
        with repo._engine.begin() as conn:
            conn.execute(text("DELETE FROM axis_coverage WHERE area_id = 'gyeongnam_geoje'"))
            conn.execute(text("DELETE FROM area_aliases WHERE area_id = 'gyeongnam_geoje'"))
            conn.execute(text("DELETE FROM areas WHERE area_id = 'gyeongnam_geoje'"))
        diffs = compare_seed_tables(repo, self._defs(), ref_date=date.today())
        assert any("gyeongnam_geoje" in d for d in diffs)

    def test_extra_area_row(self, repo, clean_db):
        """시드에 없는 행이 DB에 추가 → ① 보고."""
        from common.seeds import load_seeds, compare_seed_tables
        load_seeds(repo)
        repo.upsert_areas([{
            "area_id": "extra_test_area", "name": "추가",
            "center_lat": 35.0, "center_lng": 128.0, "radius_km": 5.0,
        }])
        diffs = compare_seed_tables(repo, self._defs(), ref_date=date.today())
        assert any("extra_test_area" in d and "[①]" in d for d in diffs)

    def test_alias_area_id_unknown(self, repo, clean_db):
        """area_aliases.area_id가 없는 해역 → ② 보고."""
        from common.seeds import load_seeds, compare_seed_tables
        load_seeds(repo)
        repo.upsert_area_aliases([{
            "alias_key": "미존재해역별칭", "area_id": "nonexistent_area", "source": "test",
        }])
        diffs = compare_seed_tables(repo, self._defs(), ref_date=date.today())
        assert any("[②]" in d and "nonexistent_area" in d for d in diffs)

    def test_axis_coverage_area_id_unknown(self, repo, clean_db):
        """axis_coverage.area_id가 없는 해역 → ② 보고."""
        from common.seeds import load_seeds, compare_seed_tables
        load_seeds(repo)
        repo.upsert_axis_coverage([{
            "area_id": "nonexistent_area", "axis": "red_tide",
            "covered": True, "season_months": [5, 6, 7, 8, 9, 10], "reason": None,
        }])
        diffs = compare_seed_tables(repo, self._defs(), ref_date=date.today())
        assert any("[②]" in d and "nonexistent_area" in d for d in diffs)

    def test_bulletin_area_id_in_window_unknown(self, schema_engine, clean_db):
        """유효 기간 안 bulletin_detail_areas.area_id가 없는 해역 → ③ 보고."""
        from common.seeds import load_seeds, compare_seed_tables
        from common.repository.sql import SqlRepository
        from datetime import datetime, timezone

        repo = SqlRepository(schema_engine)
        load_seeds(repo)

        ref_date = date(2026, 8, 15)
        window_days = 30

        raw_id = repo.insert_raw_index({
            "api": "redtideList", "tag": "sd3_t",
            "storage_key": f"test/sd3_{ref_date}",
            "fetched_at_utc": datetime(2026, 8, 15, 0, 0, 0),
            "http_status": 200, "body_sha256": None, "body_bytes": None, "precheck_code": None,
        })
        # bulletin 날짜: ref_date 이내 (ref_date - window_days 이후)
        bday = ref_date - timedelta(days=5)
        repo.upsert_bulletins([{
            "cod_news": "SD3_NEWS_001", "day_report": bday,
            "detail_count": 1, "grade": "NONE", "raw_id": raw_id,
        }])
        repo.upsert_bulletin_detail_areas([{
            "cod_news": "SD3_NEWS_001", "seq": 1, "part_no": 1,
            "area_key": "없는해역", "area_id": "nonexistent_sd3",
        }])

        diffs = compare_seed_tables(repo, self._defs(window_days), ref_date=ref_date)
        assert any("[③]" in d and "nonexistent_sd3" in d for d in diffs)

    def test_bulletin_area_id_outside_window_passes(self, schema_engine, clean_db):
        """유효 기간 밖 bulletin_detail_areas.area_id → ③ 통과 (경계 직전)."""
        from common.seeds import load_seeds, compare_seed_tables
        from common.repository.sql import SqlRepository
        from datetime import datetime, timezone

        repo = SqlRepository(schema_engine)
        load_seeds(repo)

        ref_date = date(2026, 8, 15)
        window_days = 30

        raw_id = repo.insert_raw_index({
            "api": "redtideList", "tag": "sd3_out",
            "storage_key": "test/sd3_out",
            "fetched_at_utc": datetime(2026, 8, 15, 0, 0, 0),
            "http_status": 200, "body_sha256": None, "body_bytes": None, "precheck_code": None,
        })
        # bulletin 날짜: ref_date - window_days - 1 (창 밖)
        bday_out = ref_date - timedelta(days=window_days + 1)
        repo.upsert_bulletins([{
            "cod_news": "SD3_NEWS_OUT", "day_report": bday_out,
            "detail_count": 1, "grade": "NONE", "raw_id": raw_id,
        }])
        repo.upsert_bulletin_detail_areas([{
            "cod_news": "SD3_NEWS_OUT", "seq": 1, "part_no": 1,
            "area_key": "없는해역밖", "area_id": "nonexistent_out",
        }])

        diffs = compare_seed_tables(repo, self._defs(window_days), ref_date=ref_date)
        # ③ 보고 없음 (창 밖이므로)
        assert not any("[③]" in d for d in diffs)

    def test_window_boundary_exactly_at_cutoff(self, schema_engine, clean_db):
        """경계 정확히 유효 기간 첫날(cutoff) → ③ 검출 (창 안)."""
        from common.seeds import load_seeds, compare_seed_tables
        from common.repository.sql import SqlRepository
        from datetime import datetime

        repo = SqlRepository(schema_engine)
        load_seeds(repo)

        ref_date = date(2026, 8, 15)
        window_days = 30
        cutoff = ref_date - timedelta(days=window_days)

        raw_id = repo.insert_raw_index({
            "api": "redtideList", "tag": "sd3_boundary",
            "storage_key": "test/sd3_boundary",
            "fetched_at_utc": datetime(2026, 8, 15, 0, 0, 0),
            "http_status": 200, "body_sha256": None, "body_bytes": None, "precheck_code": None,
        })
        repo.upsert_bulletins([{
            "cod_news": "SD3_NEWS_BND", "day_report": cutoff,
            "detail_count": 1, "grade": "NONE", "raw_id": raw_id,
        }])
        repo.upsert_bulletin_detail_areas([{
            "cod_news": "SD3_NEWS_BND", "seq": 1, "part_no": 1,
            "area_key": "경계해역", "area_id": "nonexistent_boundary",
        }])

        diffs = compare_seed_tables(repo, self._defs(window_days), ref_date=ref_date)
        assert any("[③]" in d and "nonexistent_boundary" in d for d in diffs)

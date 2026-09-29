"""
7.4절 — upsert 멱등성 + 콜레이션 검사
- upsert 중복: 행이 늘지 않는다
- ops_events: 고유 키 없음 → 중복 삽입 시 행이 늘어난다
- 콜레이션: txt_seas_raw 뒤 공백 구분, txt_seas_key 정규화 키 일치
"""
from __future__ import annotations

from datetime import datetime, date

import pytest
from sqlalchemy import func, select

_NOW = datetime(2026, 9, 29, 1, 0, 0)


# ─────────────────────────────────────────────────────────────────────────────
# raw_index upsert 멱등성
# ─────────────────────────────────────────────────────────────────────────────

class TestRawIndexUpsert:
    def test_insert_returns_id(self, repo, clean_db, fake_raw_id):
        row_id = fake_raw_id("key_a")
        assert isinstance(row_id, int) and row_id > 0

    def test_duplicate_storage_key_no_new_row(self, schema_engine, clean_db, fake_raw_id):
        from common.repository.tables import raw_index as t_ri
        fake_raw_id("key_dup")
        fake_raw_id("key_dup")  # 중복 삽입
        with schema_engine.connect() as conn:
            cnt = conn.execute(
                select(func.count()).select_from(t_ri)
                .where(t_ri.c.storage_key == "key_dup")
            ).scalar_one()
        assert cnt == 1


# ─────────────────────────────────────────────────────────────────────────────
# bulletins upsert 멱등성
# ─────────────────────────────────────────────────────────────────────────────

class TestBulletinUpsert:
    def test_same_cod_news_no_new_row(self, repo, clean_db):
        row = {"cod_news": "20260929-001", "day_report": date(2026, 9, 29),
               "detail_count": 1, "grade": None, "raw_id": None}
        repo.upsert_bulletins([row])
        repo.upsert_bulletins([row])  # 중복

        from common.repository.tables import bulletins as t_b
        with repo._engine.connect() as conn:
            cnt = conn.execute(select(func.count()).select_from(t_b)).scalar_one()
        assert cnt == 1

    def test_update_on_conflict(self, repo, clean_db):
        row = {"cod_news": "20260929-002", "day_report": date(2026, 9, 29),
               "detail_count": 1, "grade": None, "raw_id": None}
        repo.upsert_bulletins([row])

        row2 = dict(row, detail_count=5)
        repo.upsert_bulletins([row2])

        from common.repository.tables import bulletins as t_b
        with repo._engine.connect() as conn:
            dc = conn.execute(
                select(t_b.c.detail_count)
                .where(t_b.c.cod_news == "20260929-002")
            ).scalar_one()
        assert dc == 5


# ─────────────────────────────────────────────────────────────────────────────
# ops_events — 고유 키 없음, 중복 삽입 허용
# ─────────────────────────────────────────────────────────────────────────────

class TestOpsEventsNoDedup:
    def test_same_event_twice_creates_two_rows(self, repo, clean_db):
        row = {"event_type": "TEST_EVENT", "api": "test",
               "detail": {"msg": "hi"}, "occurred_at_utc": _NOW}
        repo.insert_ops_events([row, row])  # 같은 이벤트 두 번

        from common.repository.tables import ops_events as t_oe
        with repo._engine.connect() as conn:
            cnt = conn.execute(select(func.count()).select_from(t_oe)).scalar_one()
        assert cnt == 2


# ─────────────────────────────────────────────────────────────────────────────
# 콜레이션 검사 (7.4절)
# txt_seas_raw: 뒤 공백 있는 값과 없는 값은 다른 행
# txt_seas_key: 정규화 키는 같아야 한다
# ─────────────────────────────────────────────────────────────────────────────

class TestCollation:
    def _insert_details(self, repo, raw, key, seq):
        row = {
            "cod_news": "20260929-COL",
            "seq": seq,
            "nam_biology": "Cochlodinium polykrikoides",
            "species_class": "TARGET",
            "txt_seas_raw": raw,
            "txt_seas_key": key,
            "min_density": None,
            "max_density": 100.0,
            "grade": "ADVISORY",
        }
        repo.upsert_bulletin_details([row])

    def test_trailing_space_raw_distinct(self, repo, clean_db):
        """txt_seas_raw 뒤 공백 버전과 없는 버전은 다른 행으로 저장된다."""
        # cod_news 공통 행
        repo.upsert_bulletins([{
            "cod_news": "20260929-COL", "day_report": date(2026, 9, 29),
            "detail_count": 2, "grade": None, "raw_id": None,
        }])
        self._insert_details(repo, "전남 여수", "전남 여수", seq=1)
        self._insert_details(repo, "전남 여수 ", "전남 여수", seq=2)

        from common.repository.tables import bulletin_details as t_bd
        from sqlalchemy import literal
        with repo._engine.connect() as conn:
            # 원문 문자열로 조회 — 공백 없는 버전 1건만
            cnt = conn.execute(
                select(func.count()).select_from(t_bd)
                .where(t_bd.c.txt_seas_raw == "전남 여수")
            ).scalar_one()
        assert cnt == 1, "뒤 공백 있는 값과 없는 값이 같게 취급됨 (PAD SPACE 문제)"

    def test_normalized_key_matches_both(self, repo, clean_db):
        """정규화 키(txt_seas_key)로 조회하면 두 행이 모두 나온다."""
        repo.upsert_bulletins([{
            "cod_news": "20260929-COL", "day_report": date(2026, 9, 29),
            "detail_count": 2, "grade": None, "raw_id": None,
        }])
        self._insert_details(repo, "전남 여수", "전남 여수", seq=1)
        self._insert_details(repo, "전남 여수 ", "전남 여수", seq=2)

        from common.repository.tables import bulletin_details as t_bd
        with repo._engine.connect() as conn:
            cnt = conn.execute(
                select(func.count()).select_from(t_bd)
                .where(t_bd.c.txt_seas_key == "전남 여수")
            ).scalar_one()
        assert cnt == 2, "정규화 키로 두 행이 모두 검색되어야 한다"


# ─────────────────────────────────────────────────────────────────────────────
# observations + stations 기본 흐름
# ─────────────────────────────────────────────────────────────────────────────

class TestObservationsFlow:
    def test_upsert_station_and_observation(self, repo, clean_db):
        repo.upsert_stations([{
            "id": "tide:DT_0016", "source_api": "tide",
            "name": "여수", "lat": 34.74, "lng": 127.76,
            "sea_area": "남해", "active": True,
        }])
        repo.upsert_observations([{
            "station_id": "tide:DT_0016",
            "observed_at_utc": datetime(2026, 9, 29, 0, 0, 0),
            "metric": "water_temp",
            "value": 26.5,
            "missing_reason": None,
            "flags": [],
            "raw_id": None,
        }])

        from common.repository.tables import stations, observations
        with repo._engine.connect() as conn:
            sc = conn.execute(select(func.count()).select_from(stations)).scalar_one()
            oc = conn.execute(select(func.count()).select_from(observations)).scalar_one()
        assert sc == 1
        assert oc == 1

    def test_observation_upsert_idempotent(self, repo, clean_db):
        obs = {
            "station_id": "tide:DT_0014",
            "observed_at_utc": datetime(2026, 9, 29, 0, 0, 0),
            "metric": "salinity",
            "value": 32.0,
            "missing_reason": None,
            "flags": None,
            "raw_id": None,
        }
        repo.upsert_stations([{
            "id": "tide:DT_0014", "source_api": "tide",
            "name": "진도", "lat": 34.38, "lng": 126.26,
            "sea_area": None, "active": True,
        }])
        repo.upsert_observations([obs])
        repo.upsert_observations([obs])

        from common.repository.tables import observations as t_o
        with repo._engine.connect() as conn:
            cnt = conn.execute(select(func.count()).select_from(t_o)).scalar_one()
        assert cnt == 1

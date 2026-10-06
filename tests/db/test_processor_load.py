"""
I-12 — processor 경로 적재 (계획서 7.4절 필수 + 지시서 L1~L5)

원문 저장소(임시 디스크) → processor.process() → 고른 DB(PostgreSQL testcontainer).
기존 tests/db/test_counts.py는 어댑터 → repository를 직접 불렀다. 여기서는 진입점을 통과한다.
기대값은 ci/gate/expected.yaml counts.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
import yaml
from sqlalchemy import create_engine, func, select

from common.queue import MemoryQueue

from .conftest import FIXTURES_RAW, count_rows

_COUNTS = yaml.safe_load(
    (Path(__file__).parents[2] / "ci" / "gate" / "expected.yaml").read_text("utf-8")
)["counts"]

_FISHERY_ROWS_PER_OBS = 6   # 수온·염분·클로로필 × 표층·저층
_LINE_ROWS_PER_REC = 3      # 수온·염분·DO


def _select(engine, table, *where):
    from common.repository.tables import metadata
    tbl = metadata.tables[table]
    stmt = select(tbl)
    for w in where:
        stmt = stmt.where(w(tbl))
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(stmt).mappings().all()]


# ── 7.4 필수 — F1~F10을 processor 경로로 ──────────────────────────────────────

class TestCountsThroughProcessor:

    @pytest.mark.parametrize("year,key", [("2023", "femo_2023"), ("2024", "femo_2024"), ("2025", "femo_2025")])
    def test_femo_years(self, processor_up, raw_store, schema_engine, year, key):
        pm, _ = processor_up
        k = raw_store.put_fixture("femoSeaList", year, f"femoSeaList_f3_{year}_*.json")
        pm.process(k, "femoSeaList", MemoryQueue())
        # loaded = DB 적재(PK) — 원문 완전 중복 8건(임원)이 합쳐진 수 (7.7절, 개정 14)
        assert count_rows(schema_engine, "survey_observations") // _FISHERY_ROWS_PER_OBS == _COUNTS[key]["loaded"]
        assert count_rows(schema_engine, "survey_observations") % _FISHERY_ROWS_PER_OBS == 0
        assert _COUNTS[key]["raw"] - _COUNTS[key]["loaded"] == 8   # 완전 중복 수 (1.5절)
        assert count_rows(schema_engine, "stations") > 0          # 결정 D5 — 원문 좌표로 관측소 마스터

    @pytest.mark.parametrize("year", ["2023", "2024", "2025"])
    def test_femo_years_all_distinct_records_loaded(self, processor_up, raw_store, schema_engine, year):
        """중복을 뺀 원문 레코드가 전부 적재된다 — 적재 단계에서 빠지는 행이 없다 (위 xfail과 별개로 확인)"""
        import json
        pm, _ = processor_up
        path = next(Path(__file__).parents[2].glob(f"fixtures/raw/femoSeaList_f3_{year}_*.json"))
        from common.classifier import parse
        pr = parse(json.loads(path.read_text("utf-8"))["body"])
        distinct = {(i["FISHERY"], i["LOCATION_POINT"], int(i["DATE_Y"]), int(i["DATE_M"]), int(i["DATE_D"]),
                     int(i["TIME_H"]), int(i["TIME_I"])) for i in pr.items}
        k = raw_store.put_fixture("femoSeaList", year, f"femoSeaList_f3_{year}_*.json")
        pm.process(k, "femoSeaList", MemoryQueue())
        assert count_rows(schema_engine, "survey_observations") == len(distinct) * _FISHERY_ROWS_PER_OBS

    def test_femo_backfill_alias(self, processor_up, raw_store, schema_engine):
        """백필 원문(femoSeaList-backfill)도 같은 해석으로 적재된다 — 등록된 어댑터 없음으로 버려지지 않는다"""
        pm, _ = processor_up
        k = raw_store.put_fixture("femoSeaList-backfill", "2023", "femoSeaList_f3_2023_*.json")
        pm.process(k, "femoSeaList-backfill", MemoryQueue())
        assert count_rows(schema_engine, "survey_observations") // _FISHERY_ROWS_PER_OBS == _COUNTS["femo_2023"]["loaded"]

    def test_femo_2026_watch(self, processor_up, raw_store, schema_engine):
        """F2 — 감시 원문 0건 → publication_checks 1행, OK_EMPTY, target_year는 tag에서"""
        pm, _ = processor_up
        k = raw_store.put_fixture("femoSeaList-watch", "watch_2026", "femoSeaList_f1_*.json")
        pm.process(k, "femoSeaList-watch", MemoryQueue())
        rows = _select(schema_engine, "publication_checks")
        assert len(rows) == _COUNTS["femo_2026"]["publication_check_rows"]
        assert rows[0]["parse_status"] == _COUNTS["femo_2026"]["status"]
        assert rows[0]["target_year"] == 2026

    def test_redtide_r1(self, processor_up, raw_store, schema_engine):
        pm, _ = processor_up
        k = raw_store.put_fixture("redtideList", "r1", "redtideList_r1_*.json")
        pm.process(k, "redtideList", MemoryQueue())
        exp = _COUNTS["redtide_r1"]
        assert count_rows(schema_engine, "bulletins") == exp["stored_bulletins"]
        assert count_rows(schema_engine, "bulletin_details") == exp["details"]
        unknown = _select(schema_engine, "bulletins", lambda t: t.c.grade == "UNKNOWN")
        assert len(unknown) == exp["item2_missing_unknown"]

    def test_redtide_r3(self, processor_up, raw_store, schema_engine):
        pm, _ = processor_up
        k = raw_store.put_fixture("redtideList", "r3", "redtideList_r3_*.json")
        pm.process(k, "redtideList", MemoryQueue())
        exp = _COUNTS["redtide_r3"]
        assert count_rows(schema_engine, "bulletins") == exp["outer"]
        assert len(_select(schema_engine, "bulletin_details", lambda t: t.c.grade == "NOT_GRADED")) == exp["not_graded"]
        assert count_rows(schema_engine, "bulletin_detail_areas") == exp["detail_area_parts"]

    def test_redtide_unmapped_queue(self, processor_up, raw_store, schema_engine):
        """해역 대응이 안 된 지점은 검토 큐로 — bulletin_detail_areas.area_id가 빈 키와 같은 집합 (4.3절)"""
        pm, _ = processor_up
        for tag, g in (("r1", "redtideList_r1_*.json"), ("r3", "redtideList_r3_*.json")):
            pm.process(raw_store.put_fixture("redtideList", tag, g), "redtideList", MemoryQueue())
        unmapped_keys = {r["area_key"] for r in _select(schema_engine, "bulletin_detail_areas", lambda t: t.c.area_id.is_(None))}
        queue_keys = {r["area_key"] for r in _select(schema_engine, "unmapped_locations")}
        assert unmapped_keys, "픽스처에는 미매핑 지점이 있다(R1 4·R3 15) — 비면 적재가 안 된 것"
        assert queue_keys == unmapped_keys
        assert all(r["occurrence_count"] >= 1 for r in _select(schema_engine, "unmapped_locations"))

    def test_soo_v2(self, processor_up, raw_store, schema_engine):
        """F4·F5 — 좌표 검증 통과 레코드 전량 적재: 행 수 ÷ 3 = raw − coord_excluded"""
        pm, _ = processor_up
        k = raw_store.put_fixture("sooList", "depth", "sooList_depth_*.json")
        pm.process(k, "sooList", MemoryQueue())
        exp = _COUNTS["soo_v2"]
        n = count_rows(schema_engine, "line_observations")
        assert n % _LINE_ROWS_PER_REC == 0
        assert n // _LINE_ROWS_PER_REC == exp["raw"] - exp["coord_excluded"]
        skipped = _select(schema_engine, "ops_events", lambda t: t.c.event_type == "LOAD_ROWS_SKIPPED")
        assert skipped == []


# ── L1 멱등 · L2 재처리 ─────────────────────────────────────────────────────────

def test_L1_duplicate_notification_is_idempotent(processor_up, raw_store, schema_engine):
    pm, _ = processor_up
    k = raw_store.put_fixture("redtideList", "r1", "redtideList_r1_*.json")
    q = MemoryQueue()
    pm.process(k, "redtideList", q)
    before = {t: count_rows(schema_engine, t) for t in ("bulletins", "bulletin_details", "unmapped_locations",
                                                        "ingest_runs", "raw_index")}
    occ_before = {r["area_key"]: r["occurrence_count"] for r in _select(schema_engine, "unmapped_locations")}
    health_before = _select(schema_engine, "adapter_health")
    pm.process(k, "redtideList", q)
    after = {t: count_rows(schema_engine, t) for t in before}
    assert after == before
    assert after["ingest_runs"] == 1 and after["raw_index"] == 1
    assert {r["area_key"]: r["occurrence_count"] for r in _select(schema_engine, "unmapped_locations")} == occ_before
    assert _select(schema_engine, "adapter_health") == health_before


def test_L2_reprocess_with_new_parser_version(processor_up, raw_store, schema_engine, monkeypatch):
    pm, _ = processor_up
    k = raw_store.put_fixture("femoSeaList", "2025", "femoSeaList_f3_2025_*.json")
    pm.process(k, "femoSeaList", MemoryQueue())
    obs_before = count_rows(schema_engine, "survey_observations")
    health_before = _select(schema_engine, "adapter_health")
    monkeypatch.setattr(pm, "PARSER_VERSION", "v0.2")
    pm.reprocess([k], "femoSeaList", MemoryQueue())
    assert count_rows(schema_engine, "ingest_runs") == 2
    assert count_rows(schema_engine, "survey_observations") == obs_before
    assert _select(schema_engine, "adapter_health") == health_before   # 같은 호출을 다시 세지 않는다


# ── L3 Q6 DB판 ────────────────────────────────────────────────────────────────

def test_L3_adapter_health_sequence(processor_up, raw_store, schema_engine, tide, monkeypatch):
    """7.8 Q6 — OK → NET_ERROR → NET_ERROR → PARSE_FAILURE → OK_EMPTY, 별도로 재시도 후 성공"""
    pm, _ = processor_up
    t0 = datetime(2026, 8, 1, 0, 0, 0)
    clock = iter(t0 + timedelta(minutes=i) for i in range(100))
    monkeypatch.setattr(pm, "_now_utc", lambda: next(clock))

    ok = tide.body([("DT_0014", "2026-08-01 09:00:00", 25.0)])
    seq = [
        tide.raw(ok),
        tide.raw(None, error={"type": "NET_ERROR", "message": "x"}),
        tide.raw(None, error={"type": "NET_ERROR", "message": "x"}),
        tide.raw("<<not a response>>"),
        tide.raw(tide.body([])),
    ]
    fails, success = [], []
    for i, content in enumerate(seq):
        pm.process(raw_store.put("dtRecent", f"DT_0014_{i}", content), "dtRecent", MemoryQueue())
        h = _select(schema_engine, "adapter_health")[0]
        fails.append(h["consecutive_failures"])
        success.append(h["last_success_utc"])
    assert fails == [0, 1, 2, 2, 0]
    assert h["adapter"] == "tide"                                      # 결정 D2 — 수집 원천
    assert success[0] is not None and success[1] == success[2] == success[3] == success[0]
    assert success[4] > success[0]

    pm.process(raw_store.put("dtRecent", "DT_0014_r", tide.raw(ok, retried=True)), "dtRecent", MemoryQueue())
    h = _select(schema_engine, "adapter_health")[0]
    assert h["retry_recovered"] == 1                                   # 결정 D4 — 횟수
    statuses = [r["status"] for r in _select(schema_engine, "ingest_runs")]
    assert {"OK", "NET_ERROR", "PARSE_FAILURE", "OK_EMPTY"} <= set(statuses)   # 결정 D6 — 응답 상태


# ── L4 적재 실패 시 알림 없음 ────────────────────────────────────────────────────

def test_L4_load_failure_publishes_nothing(processor_up, raw_store, schema_engine, monkeypatch):
    pm, repo = processor_up

    def _boom(rows):
        raise RuntimeError("적재 실패 주입")
    monkeypatch.setattr(type(repo), "upsert_bulletin_details", lambda self, rows: _boom(rows))
    k = raw_store.put_fixture("redtideList", "r1", "redtideList_r1_*.json")
    q = MemoryQueue()
    with pytest.raises(RuntimeError):
        pm.process(k, "redtideList", q)
    assert q.drain("obs.loaded") == []
    for tbl in ("raw_index", "ingest_runs", "bulletins", "bulletin_details", "adapter_health"):
        assert count_rows(schema_engine, tbl) == 0, tbl


# ── L5 기동 시 테이블 검사 ──────────────────────────────────────────────────────

def test_L5_startup_stops_on_missing_table(tmp_path):
    """테이블 하나(adapter_health)를 뺀 DB로 기동 → 멈추고 빠진 테이블 이름을 보고"""
    import processor.main as pm
    from common.config import load_definitions
    from common.repository import SqlRepository
    from common.repository.tables import metadata
    engine = create_engine(f"sqlite:///{tmp_path / 'partial.db'}")
    metadata.create_all(engine, tables=[tb for tb in metadata.sorted_tables if tb.name != "adapter_health"])
    op = yaml.safe_load((Path(__file__).parents[2] / "config" / "operational.initial.yaml").read_text("utf-8"))
    with pytest.raises(SystemExit, match="adapter_health"):
        pm.startup(definitions=load_definitions(), operational=op, repo=SqlRepository(engine))


def test_survey_time_axis_in_db(processor_up, raw_store, schema_engine):
    """조사 시각이 키 — DB 행의 observed_at_utc가 원문 KST 시각 −9h (개정 14)"""
    pm, _ = processor_up
    pm.process(raw_store.put_fixture("femoSeaList", "2025", "femoSeaList_f3_2025_*.json"), "femoSeaList", MemoryQueue())
    rows = _select(schema_engine, "survey_observations",
                   lambda t: t.c.station_id == "fishery:구룡포-3", lambda t: t.c.metric == "water_temp",
                   lambda t: t.c.layer == "S")
    # 원문 첫 레코드: 구룡포 3, 2025-11-05 08:33 KST
    assert any(r["observed_at_utc"] == datetime(2025, 11, 4, 23, 33) for r in rows)


# ── 개정 15 — reprocess는 원문 ID(raw_index.id) 범위 ─────────────────────────

def test_reprocess_range_by_raw_index_id(processor_up, raw_store, schema_engine, monkeypatch):
    pm, _ = processor_up
    for tag, g in (("r1", "redtideList_r1_*.json"), ("r3", "redtideList_r3_*.json")):
        pm.process(raw_store.put_fixture("redtideList", tag, g), "redtideList", MemoryQueue())
    ids = sorted(r["id"] for r in _select(schema_engine, "raw_index"))
    assert len(ids) == 2
    monkeypatch.setattr(pm, "PARSER_VERSION", "v0.2")
    assert pm.reprocess_range(ids[0], ids[0]) == 1                  # 양끝 포함, 범위 안만
    versions = [r["parser_version"] for r in _select(schema_engine, "ingest_runs") if r["raw_id"] == ids[0]]
    assert sorted(versions) == ["v0.1", "v0.2"]
    assert pm.reprocess_range(ids[0], ids[1]) == 2
    with pytest.raises(SystemExit):
        pm.reprocess_range(ids[1], ids[0])


# ── 2026-10-02 점검 C1 — grading이 조회하는 층 값 = processor가 저장한 층 값 ──────

def test_grading_chlorophyll_layer_matches_stored_layer(processor_up, raw_store, schema_engine):
    """어장환경 원문을 processor로 적재한 뒤, grading의 표층 상수로 클로로필이 조회된다 (4.8절)"""
    from grading._chlorophyll import SURFACE_LAYER
    pm, repo = processor_up
    k = raw_store.put_fixture("femoSeaList", "2025", "femoSeaList_f3_2025_*.json")
    pm.process(k, "femoSeaList", MemoryQueue())
    stored = {r["layer"] for r in _select(schema_engine, "survey_observations", lambda t: t.c.metric == "chlorophyll")}
    assert SURFACE_LAYER in stored
    assert repo.get_latest_survey_obs("chlorophyll", SURFACE_LAYER)


def test_regular_path_filter_ignored_recorded(processor_up, raw_store, schema_engine):
    """C9 — 정기 경로: 원문 항목 날짜(day_report)가 요청 창 밖이면 ingest_runs.status = FILTER_IGNORED (3.3절)"""
    import json
    pm, _ = processor_up
    path = next(FIXTURES_RAW.glob("redtideList_r1_*.json"))
    content = json.loads(path.read_text("utf-8"))
    content["url"] = content["url"].replace("edate=20260921", "edate=20260815")   # 0816 이후 속보가 창 밖
    content.setdefault("http_status", content.get("http"))
    content.setdefault("fetched_at", "2026-09-20T00:00:00Z")
    pm.process(raw_store.put("redtideList", "narrow", content), "redtideList", MemoryQueue())
    assert [r["status"] for r in _select(schema_engine, "ingest_runs")] == ["FILTER_IGNORED"]


def test_unreadable_observation_time_rows_skipped_not_shifted(processor_up, raw_store, schema_engine, tide):
    """C10 — 시각을 못 읽은 관측은 KST 문자열로 적재하지 않고 건너뛰어 LOAD_ROWS_SKIPPED로 남긴다. 나머지는 UTC로"""
    pm, _ = processor_up
    codes = list(tide.STATIONS)
    obs = [(codes[0], "2026/08/01 09:00", 24.0)] + [(c, "2026-08-01 09:00:00", 24.5) for c in codes[1:]]
    pm.process(raw_store.put("dtRecent", "badtime", tide.raw(tide.body(obs))), "dtRecent", MemoryQueue())

    rows = _select(schema_engine, "observations")
    assert {r["station_id"] for r in rows} == {f"tide:{c}" for c in codes[1:]}
    assert {r["observed_at_utc"] for r in rows} == {datetime(2026, 8, 1, 0, 0, 0)}
    ev = [e for e in _select(schema_engine, "ops_events") if e["event_type"] == "LOAD_ROWS_SKIPPED"]
    assert len(ev) == 1 and ev[0]["detail"]["rows"] > 0
    assert [r["status"] for r in _select(schema_engine, "ingest_runs")] == ["OK"]


def test_live_dtrecent_raw_loads_station_and_observations(processor_up, raw_store, schema_engine):
    """I-17 실수집 dtRecent 원문(항목에 관측소 코드 없음) — 관측소 마스터·관측이 적재되고 obs.loaded에 시각이 실린다.
    수정 전: body.items.item을 못 읽어 PARSE_FAILURE, 고친 뒤에도 관측소 코드가 없어 0행·관측소 없음"""
    from sqlalchemy import text
    from common.queue import MemoryQueue
    pm, _repo = processor_up
    key = raw_store.put_fixture("dtRecent", "DT_0014", "dtRecent_i17_DT_0014_*.json")
    q = MemoryQueue()
    pm.process(key, "dtRecent", q)
    with schema_engine.connect() as c:
        st = c.execute(text("SELECT id FROM stations WHERE source_api = 'tide'")).scalars().all()
        n = c.execute(text("SELECT COUNT(*) FROM observations WHERE station_id = 'tide:DT_0014'")).scalar()
    assert st == ["tide:DT_0014"]
    assert n == 300 * 6
    (msg,) = q.drain("obs.loaded")
    assert msg.payload["observed_to_utc"] and msg.payload["station_ids"] == ["tide:DT_0014"]

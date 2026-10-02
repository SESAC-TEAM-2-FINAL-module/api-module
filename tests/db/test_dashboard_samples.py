"""
대시보드 인계 묶음의 예시 행 생성 — 실제 단계 코드를 통과한 결과 테이블 행을 덤프한다.
DASHBOARD_SAMPLE_OUT(출력 JSON 경로)이 있을 때만 돈다. 결과 테이블 계약이 바뀌면 다시 생성한다.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path

import pytest
import yaml
from sqlalchemy import text

from common.queue import MemoryQueue

OUT = os.environ.get("DASHBOARD_SAMPLE_OUT")
pytestmark = pytest.mark.skipif(not OUT, reason="DASHBOARD_SAMPLE_OUT 미설정 — 예시 행 생성 전용")

NOW_UTC = datetime(2026, 8, 14, 3, 10, 0)          # KST 2026-08-14 12:10 — R1 여수 해역 속보 기간
FARMS = [
    ("syn_gam_001", 34.68, 127.69),                 # 가막만 — 해역 전남 여수
    ("syn_out_001", 34.30, 126.30),                 # 반경 안 해역 없음 — 커버리지 밖 예시
]
RESULT_TABLES = ["farm_readings", "axis_status", "farm_areas", "farm_reading_history"]


@pytest.fixture()
def farms(schema_engine):
    with schema_engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE farm_sites (farm_id VARCHAR(64) PRIMARY KEY, lat DOUBLE PRECISION, "
            "lng DOUBLE PRECISION, active BOOLEAN, updated_at_utc TIMESTAMP)"))
        for fid, lat, lng in FARMS:
            conn.execute(text("INSERT INTO farm_sites VALUES (:f, :a, :o, TRUE, '2026-07-01 00:00:00')"),
                         {"f": fid, "a": lat, "o": lng})
    yield [f[0] for f in FARMS]
    with schema_engine.begin() as conn:
        conn.execute(text("DROP TABLE farm_sites"))


def _rows(engine, sql: str, **params) -> list[dict]:
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def _jsonable(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


def test_dump_dashboard_samples(processor_up, raw_store, schema_engine, tide, farms, monkeypatch):
    import evaluation.main as ev
    import grading.main as gr
    import interpolation.main as ip
    from common.config import load_definitions
    from processor.adapters.bulletin._seed import load_seeds

    pm, repo = processor_up
    defs = load_definitions()
    op = yaml.safe_load((Path(__file__).parents[2] / "config" / "operational.initial.yaml").read_text("utf-8"))
    load_seeds(repo)
    import common.repository.sql as sql_mod

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW_UTC.replace(tzinfo=tz) if tz else NOW_UTC

    monkeypatch.setattr(gr, "_utcnow", lambda: NOW_UTC)
    monkeypatch.setattr(ev, "_now_utc", lambda: NOW_UTC)
    monkeypatch.setattr(ip, "_utcnow", lambda: NOW_UTC)
    monkeypatch.setattr(sql_mod, "datetime", _FrozenDatetime)     # LOOCV 창 조회의 기준 시각

    # 오늘의 오차(LOOCV)가 계산되도록 앞선 관측 시점을 먼저 적재만 한다 — 알림은 버린다
    for h in range(6, 12):
        prior = [(code, f"2026-08-14 {h:02d}:00:00", 24.0 + h * 0.1 + ((i * 7) % 5) * 0.4)
                 for i, code in enumerate(tide.STATIONS)]
        pm.process(raw_store.put("dtRecent", f"h{h}", tide.raw(tide.body(prior))), "dtRecent", MemoryQueue())

    q = MemoryQueue()
    obs = [(code, "2026-08-14 12:00:00", 25.2 + ((i * 7) % 5) * 0.4) for i, code in enumerate(tide.STATIONS)]
    keys = [
        (raw_store.put("dtRecent", "all", tide.raw(tide.body(obs), fetched_at="2026-08-14T03:05:00Z")), "dtRecent"),
        (raw_store.put_fixture("redtideList", "r1", "redtideList_r1_*.json"), "redtideList"),
        (raw_store.put_fixture("sooList", "depth", "sooList_depth_*.json"), "sooList"),
        (raw_store.put_fixture("femoSeaList", "2025", "femoSeaList_f3_2025_*.json"), "femoSeaList"),
    ]
    for key, api in keys:
        pm.process(key, api, q)
    for msg in q.drain("obs.loaded"):
        if msg.payload.get("source") == "tide":
            ip.handle_obs_loaded(msg.payload, repo, q, defs)
            for done in q.drain("interp.done"):
                gr.handle_interp_done(done.payload, repo, q, defs)
        gr.handle_obs_loaded(msg.payload, repo, q, defs)
    for msg in q.drain("grade.done"):
        ev.handle_grade_done(msg.payload, repo, q, op)
    updated = q.drain("result.updated")

    readings = _rows(schema_engine, "SELECT * FROM farm_readings ORDER BY farm_id, axis")
    assert readings
    for r in readings:                                                     # N11
        assert not (r["derivation"] == "COMPUTED" and r["alertable"])

    red_refs = {r["source_ref"].split("#")[0] for r in readings if r["axis"] == "red_tide" and r["source_ref"]}
    bulletins = [b for b in _rows(schema_engine, "SELECT * FROM bulletins ORDER BY cod_news")
                 if b["cod_news"] in red_refs]
    sample = {
        "_notes": {
            "origin": "API 모듈 단계 코드(processor → interpolation → grading → evaluation)를 실제로 통과한 결과 "
                      "테이블 행. 입력: 합성 조위 원문 1건 + 검증 원문 픽스처(적조 R1·정선·어장환경 2025). 실 DB 덤프 아님",
            "basis_time": "판정 시각 2026-08-14T03:10:00 UTC (KST 12:10)",
            "farms": "합성 양식장 2곳 — syn_gam_001(가막만, 해역 있음), syn_out_001(반경 안 해역 없음). "
                     "형식은 farm_sites_format.csv",
            "utc": "모든 *_utc 시각은 UTC naive. 화면 표시 시 KST(+9h) 변환",
            "contract": "결과 테이블 계약 tables-v2 — 의미는 dashboard_contract.md, DDL은 schema_pg.sql / schema_my.sql",
            "dashboard_reads": "farm_readings, axis_status, farm_areas, farm_reading_history, bulletins, "
                               "bulletin_details, bulletin_detail_areas, areas, axis_coverage(시드 — seeds/)",
            "generator": "tests/db/test_dashboard_samples.py (DASHBOARD_SAMPLE_OUT 지정 시 재생성)",
        },
        **{t: [{k: _jsonable(v) for k, v in r.items()}
               for r in _rows(schema_engine, f"SELECT * FROM {t} ORDER BY 1, 2")] for t in RESULT_TABLES},
        "bulletins": [{k: _jsonable(v) for k, v in b.items()} for b in bulletins],
        "bulletin_details": [{k: _jsonable(v) for k, v in r.items()} for r in _rows(
            schema_engine, "SELECT * FROM bulletin_details WHERE cod_news = ANY(:c) ORDER BY cod_news, seq",
            c=list(red_refs))],
        "bulletin_detail_areas": [{k: _jsonable(v) for k, v in r.items()} for r in _rows(
            schema_engine, "SELECT * FROM bulletin_detail_areas WHERE cod_news = ANY(:c) ORDER BY 1, 2, 3",
            c=list(red_refs))],
        "result_updated_messages": [m.payload for m in updated],
    }
    Path(OUT).write_text(json.dumps(sample, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")

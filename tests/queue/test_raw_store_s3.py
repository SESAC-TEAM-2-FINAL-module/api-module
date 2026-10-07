"""
7.11 O1~O5 — S3 원문 저장소 구현 검사 (개정 22). S3 호환 테스트 컨테이너(MinIO)만 쓴다.
O1의 E3 재실행(tide·bulletin → 같은 DB 행)은 tests/db/test_collector_e2e.py
"""
from __future__ import annotations

import json
import logging
import runpy
import sys
import time
from pathlib import Path

import pytest

_ROOT = Path(__file__).parents[2]
_FIX = _ROOT / "fixtures" / "raw"


def _envelope(body: str = '{"a": "가나다"}', fetched_at: str = "2026-10-07T01:02:03", ms: int | None = None) -> dict:
    return {"url": "https://example.invalid/", "params": {"key": "***"}, "http_status": 200,
            "final_url": None, "fetched_at": fetched_at,
            "_fetched_ms": ms if ms is not None else time.time_ns() // 1_000_000,
            "body": body, "error": None}


def _s3(env, prefix: str = ""):
    from common.raw_store._store import S3Store
    return S3Store(env["bucket"], prefix=prefix, endpoint_url=env["endpoint"])


# ── O1 왕복 ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("prefix", ["", "env/a"])
def test_o1_round_trip_same_as_local_disk(s3_env, tmp_path, prefix):
    from common.raw_store._store import LocalDiskStore
    s3, local = _s3(s3_env, prefix), LocalDiskStore(str(tmp_path))
    body = json.loads(next(_FIX.glob("redtideList_r1_*.json")).read_text("utf-8"))["body"]
    keys = [f"raw/redtideList/2026/10/07/{1_791_000_000_000 + i}_20260907_20261007.json" for i in range(3)]
    for k in keys:
        env = _envelope(body)
        assert s3.put(k, env) == k
        local.put(k, env)
    for k in keys:
        assert s3.get_body(k) == local.get_body(k) == body
        assert s3.get_meta(k) == local.get_meta(k)
        assert "body" not in s3.get_meta(k)
    assert sorted(s3.list_keys("raw/redtideList/2026/10/07/")) == sorted(local.list_keys("raw/redtideList/2026/10/07/")) == keys
    assert s3.list_keys("raw/redtideList/2026/10/06/") == []
    assert s3.get_meta("raw/redtideList/2026/10/07/0_none.json") is None
    assert s3.get_body("raw/redtideList/2026/10/07/0_none.json") is None


def test_o1_envelope_bytes_equal_local_disk(s3_env, tmp_path):
    """원문 봉투를 JSON으로 한 번 직렬화한 바이트 — 로컬 디스크 구현과 같다 (2.3절)"""
    from common.raw_store._store import LocalDiskStore
    s3, local = _s3(s3_env, "p"), LocalDiskStore(str(tmp_path))
    key = "raw/dtRecent/2026/10/07/1791000000123_DT_0001.json"
    env = _envelope('{"x": "한글 \\" 따옴표"}', ms=1791000000123)
    s3.put(key, env)
    local.put(key, env)
    stored = s3_env["client"].get_object(Bucket=s3_env["bucket"], Key=f"p/{key}")["Body"].read()
    assert stored == (tmp_path / key).read_bytes()


def test_o1_list_keys_paginates(s3_env):
    s3 = _s3(s3_env)
    keys = [f"raw/sooList/2026/10/07/{1_791_000_000_000 + i}_t.json" for i in range(1005)]
    for k in keys:
        s3_env["client"].put_object(Bucket=s3_env["bucket"], Key=k, Body=b"{}")
    assert sorted(s3.list_keys("raw/sooList/2026/10/07/")) == sorted(keys)


# ── O2 덮어쓰기 금지 ────────────────────────────────────────────────────────

def test_o2_second_put_same_key_fails_and_first_kept(s3_env, tmp_path):
    from common.raw_store._store import LocalDiskStore
    for store in (_s3(s3_env), LocalDiskStore(str(tmp_path))):
        key = "raw/dtRecent/2026/10/07/1791000000000_DT_0001.json"
        store.put(key, _envelope("first"))
        with pytest.raises(FileExistsError):
            store.put(key, _envelope("second"))
        assert store.get_body(key) == "first"


def test_o2_versioned_bucket_also_refuses_overwrite(s3_env):
    """버전 관리 버킷에서는 덮어써도 옛 버전이 남지만, 조건부 쓰기가 새 버전 자체를 막아야 한다 (2.3절)"""
    c, bucket = s3_env["client"], s3_env["bucket"]
    c.put_bucket_versioning(Bucket=bucket, VersioningConfiguration={"Status": "Enabled"})
    s3 = _s3(s3_env)
    key = "raw/dtRecent/2026/10/07/1791000000000_DT_0001.json"
    s3.put(key, _envelope("first"))
    with pytest.raises(FileExistsError):
        s3.put(key, _envelope("second"))
    assert s3.get_body(key) == "first"
    assert len(c.list_object_versions(Bucket=bucket, Prefix=key).get("Versions", [])) == 1


def test_o2_save_raw_conflict_counts_error_and_raises(s3_env, monkeypatch):
    import common.raw_store as rs
    from common.metrics import raw_store_errors_total
    monkeypatch.setenv("RAW_STORE_DSN", f"s3://{s3_env['bucket']}")
    rs.open_raw_store("collector")
    label = (("image", "collector"), ("op", "put"))
    before = raw_store_errors_total._values[label]
    env = _envelope("first", ms=1791000000000)
    key = rs.save_raw("dtRecent", "DT_0001", env)
    with pytest.raises(FileExistsError):
        rs.save_raw("dtRecent", "DT_0001", _envelope("second", ms=1791000000000))
    assert raw_store_errors_total._values[label] == before + 1
    assert rs.get_raw_body(key) == "first"


# ── O3 연결 실패 → 멈춤 ─────────────────────────────────────────────────────

def _no_local_writes(tmp_path):
    return not any(tmp_path.rglob("*.json"))


def test_o3_no_dsn_stops_and_ignores_raw_store_path(s3_env, monkeypatch, tmp_path):
    import common.raw_store as rs
    monkeypatch.delenv("RAW_STORE_DSN", raising=False)
    monkeypatch.setenv("RAW_STORE_PATH", str(tmp_path))        # 남아 있어도 대체하지 않는다 (검수 N13)
    with pytest.raises(SystemExit, match="RAW_STORE_DSN"):
        rs.open_raw_store("collector")
    with pytest.raises(SystemExit):
        rs.save_raw("dtRecent", "DT_0001", _envelope())
    assert _no_local_writes(tmp_path)


@pytest.mark.parametrize("dsn", ["file:///tmp/raw", "/data/raw", "s3:/bucket"])
def test_o3_malformed_dsn_stops(s3_env, monkeypatch, dsn):
    import common.raw_store as rs
    monkeypatch.setenv("RAW_STORE_DSN", dsn)
    with pytest.raises(SystemExit, match="형식"):
        rs.open_raw_store("collector")


def test_o3_missing_bucket_stops(s3_env, monkeypatch):
    import common.raw_store as rs
    monkeypatch.setenv("RAW_STORE_DSN", "s3://no-such-bucket-o3")
    with pytest.raises(SystemExit, match="S3"):
        rs.open_raw_store("processor")


def test_o3_unreachable_endpoint_stops(s3_env, monkeypatch):
    import common.raw_store as rs
    monkeypatch.setenv("RAW_STORE_DSN", f"s3://{s3_env['bucket']}")
    monkeypatch.setenv("RAW_STORE_ENDPOINT", "http://127.0.0.1:1")
    with pytest.raises(SystemExit, match="S3"):
        rs.open_raw_store("processor")


def test_o3_explicit_local_store_is_used(s3_env, monkeypatch, tmp_path):
    """테스트·실행기가 로컬 디스크를 코드로 넘기면 그것을 쓴다"""
    import common.raw_store as rs
    from common.raw_store._store import LocalDiskStore
    monkeypatch.delenv("RAW_STORE_DSN", raising=False)
    rs.init_store(LocalDiskStore(str(tmp_path)))
    key = rs.save_raw("dtRecent", "DT_0001", _envelope("local"))
    assert (tmp_path / key).is_file()
    rs.init_store(None)


# ── O4 키 밀리초 ────────────────────────────────────────────────────────────

def test_o4_same_second_keys_differ_and_sort_in_save_order(s3_env, monkeypatch):
    import common.raw_store as rs
    from common.http._client import _now_ms
    monkeypatch.setenv("RAW_STORE_DSN", f"s3://{s3_env['bucket']}")
    rs.open_raw_store("collector")
    keys = []
    for _ in range(3):
        keys.append(rs.save_raw("redtideList", "20260907_20261007",
                                _envelope("b", fetched_at="2026-10-07T01:02:03", ms=_now_ms())))
        time.sleep(0.002)
    assert len(set(keys)) == 3
    ms = [int(Path(k).name.split("_", 1)[0]) for k in keys]
    assert ms == sorted(ms)
    listed = rs.list_raw_keys("raw/redtideList/2026/10/07/")
    order = sorted(listed, key=lambda k: (int(Path(k).name.split("_", 1)[0]), k))
    assert order == keys


def test_o4_fetch_records_millisecond(monkeypatch):
    """호출층이 원문 메타에 밀리초를 남긴다 — 초 단위 fetched_at과 같은 순간 (2.3절)"""
    from common.http import _client
    ms = _client._now_ms()
    assert abs(ms - time.time() * 1000) < 5_000
    assert isinstance(ms, int)


# ── O5 비밀 미출력 ──────────────────────────────────────────────────────────

_NATS_USER, _NATS_PASS = "o5natsuser41c7", "o5natspass8d2e"


@pytest.fixture()
def nats_auth_url():
    try:
        from testcontainers.core.container import DockerContainer
        from testcontainers.core.waiting_utils import wait_for_logs
    except ImportError:
        pytest.skip("testcontainers 미설치")
    c = (DockerContainer("nats:2.10-alpine")
         .with_command(f"-js --user {_NATS_USER} --pass {_NATS_PASS}").with_exposed_ports(4222))
    with c:
        wait_for_logs(c, "Server is ready", timeout=60)
        yield c.get_container_host_ip(), c.get_exposed_port(4222)


def _run_collector_main(monkeypatch, workload: str) -> None:
    monkeypatch.setattr(sys, "argv", ["collector.main", workload])
    runpy.run_module("collector.main", run_name="__main__")


def test_o5_markers_absent_from_logs_raw_and_exit(s3_env, nats_auth_url, monkeypatch, capsys, caplog):
    import collector.adapters.bulletin._adapter as cb
    import collector.main as cm
    host, port = nats_auth_url
    body = json.loads(next(_FIX.glob("redtideList_r1_*.json")).read_text("utf-8"))["body"]
    monkeypatch.setattr(cb, "fetch", lambda *a, **k: _envelope(body))
    for var in ("DTRECENT_URL", "NIFS_URL"):
        monkeypatch.setenv(var, "https://example.invalid/")
    for var in ("DTRECENT_KEY", "NIFS_KEY_BULLETIN", "NIFS_KEY_LINE", "NIFS_KEY_FISHERY_SEA"):
        monkeypatch.setenv(var, "test-placeholder")
    monkeypatch.setenv("RAW_STORE_DSN", f"s3://{s3_env['bucket']}")
    monkeypatch.setenv("QUEUE_DSN", f"nats://{_NATS_USER}:{_NATS_PASS}@{host}:{port}")
    monkeypatch.setenv("QUEUE_STREAM_REPLICAS", "1")
    cm._load_adapters()
    caplog.set_level(logging.DEBUG)
    exits = []

    _run_collector_main(monkeypatch, "bulletin")                        # 정상 실행
    monkeypatch.setenv("QUEUE_DSN", f"nats://{_NATS_USER}:wrong-{_NATS_PASS[::-1]}@{host}:{port}")
    with pytest.raises(SystemExit) as e:                               # 큐 인증 실패
        _run_collector_main(monkeypatch, "bulletin")
    exits.append(str(e.value))
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", s3_env["marks"][1] + "x")
    import common.raw_store._store as store_mod
    monkeypatch.setattr(store_mod, "_store", None)
    with pytest.raises(SystemExit) as e:                               # 원문 저장소 인증 실패
        _run_collector_main(monkeypatch, "bulletin")
    exits.append(str(e.value))

    client = s3_env["client"]
    objs = client.list_objects_v2(Bucket=s3_env["bucket"]).get("Contents", [])
    assert objs, "정상 실행이 원문을 저장하지 않았다"
    raw = b"".join(client.get_object(Bucket=s3_env["bucket"], Key=o["Key"])["Body"].read() for o in objs)
    out = capsys.readouterr()
    sources = {"stdout": out.out, "stderr": out.err, "log": caplog.text,
               "exit": "\n".join(exits), "raw": raw.decode("utf-8")}
    marks = (*s3_env["marks"], _NATS_USER, _NATS_PASS)
    hits = sorted((name, i) for name, text in sources.items() for i, m in enumerate(marks) if m in text)
    loggers = sorted({r.name for r in caplog.records if any(m in r.getMessage() for m in marks)})
    assert hits == [], f"표식 출력(출처, 표식 번호): {hits} 로거 {loggers}"
    assert all("멈춤" in x or "실패" in x for x in exits)

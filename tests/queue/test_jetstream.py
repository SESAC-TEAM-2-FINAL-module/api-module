"""
7.11 J1~J8 — NATS JetStream 큐 구현 검사 (개정 22). 테스트 컨테이너 NATS만 쓴다.
"""
from __future__ import annotations

import asyncio
import threading
import time

import pytest

from common.queue import Message, NatsQueue, msg_id_of
from tests_queue_helpers import run_in_thread, wait_until


def _q(nats_url, spec, workload, **kw) -> NatsQueue:
    q = NatsQueue(nats_url, 1, workload, spec=spec, **kw)
    q.connect()
    return q


def _payload(topic, **kw):
    base = {"schema": "queue-v2", "topic": topic}
    base.update(kw)
    return base


def _stream_msgs(q: NatsQueue) -> int:
    info = q._call(q._js.stream_info(q._spec["stream"]["name"]))
    return info.state.messages


# ── J1 ──────────────────────────────────────────────────────────────────────

def test_j1_creates_stream_and_all_consumers_idempotently(nats_url, spec):
    q = _q(nats_url, spec, "collector")
    names = {c["name"] for c in spec["consumers"]}
    got = set()
    for n in names:
        info = q._call(q._js.consumer_info(spec["stream"]["name"], n))
        got.add(info.name)
    assert got == names
    q2 = _q(nats_url, spec, "processor")          # 다시 기동 — 그대로
    info = q2._call(q2._js.stream_info(spec["stream"]["name"]))
    assert info.config.max_age == pytest.approx(float(spec["stream"]["max_age_seconds"]))
    assert getattr(info.config.retention, "value", info.config.retention) == "interest"
    q.close(); q2.close()


def test_j1_mismatch_stops(nats_url, spec):
    q = _q(nats_url, spec, "collector")
    from nats.js import api
    stream = spec["stream"]["name"]
    q._call(q._js.delete_consumer(stream, "processor-raw-fetched"))
    q._call(q._js.add_consumer(stream, config=api.ConsumerConfig(
        durable_name="processor-raw-fetched", filter_subject=f"{spec['subject_prefix']}.raw.fetched",
        ack_policy=api.AckPolicy.EXPLICIT, ack_wait=5.0, max_deliver=3)))
    with pytest.raises(SystemExit) as e:
        _q(nats_url, spec, "processor")
    assert "max_deliver" in str(e.value)
    q.close()


def test_j1_server_defaults_and_foreign_consumer_pass(nats_url, spec):
    q = _q(nats_url, spec, "collector")
    from nats.js import api
    stream = spec["stream"]["name"]
    cfg = q._call(q._js.stream_info(stream)).config
    cfg.max_msgs = 123456                           # 비교 필드 밖 — 서버 쪽 값만 다름
    q._call(q._js.update_stream(config=cfg))
    q._call(q._js.add_consumer(stream, config=api.ConsumerConfig(   # 계약에 없는 컨슈머(웹 등)
        durable_name="web-result-updated", filter_subject=f"{spec['subject_prefix']}.result.updated",
        ack_policy=api.AckPolicy.EXPLICIT)))
    _q(nats_url, spec, "processor").close()
    q.close()


def test_j1_open_queue_requires_env(monkeypatch):
    from common.queue import open_queue
    monkeypatch.delenv("QUEUE_DSN", raising=False)
    monkeypatch.setenv("QUEUE_STREAM_REPLICAS", "1")
    with pytest.raises(SystemExit, match="QUEUE_DSN"):
        open_queue("processor")
    monkeypatch.setenv("QUEUE_DSN", "nats://127.0.0.1:1")
    monkeypatch.delenv("QUEUE_STREAM_REPLICAS", raising=False)
    with pytest.raises(SystemExit, match="QUEUE_STREAM_REPLICAS"):
        open_queue("processor")


# ── J2 · J3 ─────────────────────────────────────────────────────────────────

def test_j2_ack_after_success_and_redeliver_on_error(nats_url, spec):
    pub = _q(nats_url, spec, "collector")
    con = _q(nats_url, spec, "processor")
    calls = []

    def handler(msg: Message):
        calls.append(msg.payload["raw_id"])
        if len(calls) == 1:
            raise RuntimeError("커밋 실패 흉내")

    con.subscribe("raw.fetched", handler)
    t = run_in_thread(con)
    pub.publish(Message("raw.fetched", _payload("raw.fetched", raw_id="k1", api="dtRecent")))
    assert _wait(lambda: len(calls) == 2)
    time.sleep(1.5)                                  # ack된 뒤 다시 오지 않는다
    assert calls == ["k1", "k1"]
    con.stop(); t.join(10)
    assert _wait(lambda: _stream_msgs(pub) == 0)
    pub.close(); con.close()


def test_j3_exhausted_records_once(nats_url, spec):
    pub = _q(nats_url, spec, "collector")
    events = []
    con = _q(nats_url, spec, "processor", on_exhausted=events.append)
    calls = []

    def handler(msg):
        calls.append(1)
        raise ValueError("늘 실패")

    con.subscribe("raw.fetched", handler)
    t = run_in_thread(con)
    pub.publish(Message("raw.fetched", _payload("raw.fetched", raw_id="k2", api="dtRecent")))
    max_deliver = spec["consumer_defaults"]["max_deliver"]
    assert _wait(lambda: len(events) == 1, timeout=20)
    time.sleep(1.5)
    assert len(calls) == max_deliver
    assert len(events) == 1
    ev = events[0]
    assert ev["topic"] == "raw.fetched" and ev["consumer"] == "processor-raw-fetched"
    assert ev["num_delivered"] == max_deliver and ev["msg_id"] == "raw.fetched:k2"
    assert ev["error_type"] == "ValueError"
    con.stop(); t.join(10)
    pub.close(); con.close()


def test_j3_recorder_writes_ops_event():
    from common.queue import exhausted_recorder

    class _Repo:
        rows = []
        def insert_ops_events(self, rows):
            self.rows.extend(rows)
    r = _Repo()
    exhausted_recorder(r)({"topic": "raw.fetched", "payload": {"api": "dtRecent"}, "num_delivered": 5})
    assert r.rows[0]["event_type"] == "QUEUE_DELIVERY_EXHAUSTED" and r.rows[0]["api"] == "dtRecent"


# ── J4 ──────────────────────────────────────────────────────────────────────

def test_j4_two_consumers_each_receive_and_interest_retention(nats_url, spec):
    pub = _q(nats_url, spec, "collector")
    interp = _q(nats_url, spec, "interpolation")
    grad = _q(nats_url, spec, "grading")
    got_i, got_g = [], []
    interp.subscribe("obs.loaded", lambda m: got_i.append(m.payload["load_id"]))
    pub.publish(Message("obs.loaded", _payload("obs.loaded", load_id="L1", api="dtRecent")))
    ti = run_in_thread(interp)
    assert _wait(lambda: got_i == ["L1"])
    assert _wait(lambda: _stream_msgs(pub) == 1)     # grading이 아직 ack하지 않았다 — 남는다
    grad.subscribe("obs.loaded", lambda m: got_g.append(m.payload["load_id"]))
    tg = run_in_thread(grad)
    assert _wait(lambda: got_g == ["L1"])
    assert _wait(lambda: _stream_msgs(pub) == 0)     # 둘 다 ack — 지워진다
    for q, t in ((interp, ti), (grad, tg)):
        q.stop(); t.join(10); q.close()
    pub.close()


def test_grading_runs_two_subscriptions_in_one_process(nats_url, spec):
    pub = _q(nats_url, spec, "collector")
    grad = _q(nats_url, spec, "grading")
    seen = []
    grad.subscribe("obs.loaded", lambda m: seen.append("obs"))
    grad.subscribe("interp.done", lambda m: seen.append("interp"))
    t = run_in_thread(grad)
    pub.publish(Message("obs.loaded", _payload("obs.loaded", load_id="L2", api="dtRecent")))
    pub.publish(Message("interp.done", _payload("interp.done", run_id="R2", load_id="L2")))
    assert _wait(lambda: sorted(seen) == ["interp", "obs"])
    grad.stop(); t.join(10); grad.close(); pub.close()


def test_handler_can_publish_inside_consumer(nats_url, spec):
    """핸들러 안에서 다음 알림을 발행한다 — 루프가 겹치지 않아야 한다"""
    pub = _q(nats_url, spec, "collector")
    proc = _q(nats_url, spec, "processor")
    interp = _q(nats_url, spec, "interpolation")
    out = []
    proc.subscribe("raw.fetched", lambda m: proc.publish(
        Message("obs.loaded", _payload("obs.loaded", load_id=m.payload["raw_id"] + "::v", api="dtRecent"))))
    interp.subscribe("obs.loaded", lambda m: out.append(m.payload["load_id"]))
    tp, ti = run_in_thread(proc), run_in_thread(interp)
    pub.publish(Message("raw.fetched", _payload("raw.fetched", raw_id="k3", api="dtRecent")))
    assert _wait(lambda: out == ["k3::v"])
    for q, t in ((proc, tp), (interp, ti)):
        q.stop(); t.join(10); q.close()
    pub.close()


# ── J6 ──────────────────────────────────────────────────────────────────────

def test_j6_waits_without_messages_and_finishes_in_flight_on_stop(nats_url, spec):
    pub = _q(nats_url, spec, "collector")
    con = _q(nats_url, spec, "processor")
    started, finished = threading.Event(), threading.Event()

    def slow(msg):
        started.set()
        time.sleep(2.5)                              # in_progress 간격(1초)보다 길게
        finished.set()

    con.subscribe("raw.fetched", slow)
    t = run_in_thread(con)
    time.sleep(2.0)
    assert t.is_alive()                              # 메시지가 없어도 끝나지 않는다
    pub.publish(Message("raw.fetched", _payload("raw.fetched", raw_id="k4", api="dtRecent")))
    assert started.wait(10)
    con.stop()                                       # 처리 중 종료 신호
    t.join(15)
    assert not t.is_alive() and finished.is_set()
    assert _wait(lambda: _stream_msgs(pub) == 0)     # 마친 메시지는 ack — 다시 오지 않는다
    con.close(); pub.close()


# ── J7 ──────────────────────────────────────────────────────────────────────

def test_j7_msg_id_dedup_and_distinct_keys(nats_url, spec):
    pub = _q(nats_url, spec, "collector")
    _q(nats_url, spec, "evaluation").close()         # 소비자 자리(Interest)
    g = _payload("grade.done", grade_run_id="G1", axis="water_temp", farm_ids=["f1"])
    pub.publish(Message("grade.done", g))
    pub.publish(Message("grade.done", dict(g)))                      # 같은 Msg-Id → 1건
    pub.publish(Message("grade.done", dict(g, axis="salinity")))     # 같은 실행, 다른 축 → 남는다
    pub.publish(Message("obs.loaded", _payload("obs.loaded", load_id="G1", api="x")))  # 다른 주제, 같은 키
    pub.publish(Message("interp.done", _payload("interp.done", run_id="G1", load_id="G1")))
    c1 = _payload("completeness.collected", run_key="RK", api="sooList")
    pub.publish(Message("completeness.collected", c1))
    pub.publish(Message("completeness.collected", dict(c1, api="femoSeaList")))
    assert _wait(lambda: _stream_msgs(pub) == 6)
    pub.close()


def test_j7_msg_id_table():
    from common.queue import load_spec
    s = load_spec()
    assert msg_id_of("raw.fetched", {"raw_id": "a"}, s) == "raw.fetched:a"
    assert msg_id_of("completeness.collected", {"run_key": "r", "api": "x"}, s) == "completeness.collected:r+x"
    assert msg_id_of("obs.loaded", {"load_id": "l", "raw_id": "zz"}, s) == "obs.loaded:l"
    assert msg_id_of("interp.done", {"run_id": "r", "load_id": "l"}, s) == "interp.done:r"
    assert msg_id_of("grade.done", {"grade_run_id": "g", "axis": "a"}, s) == "grade.done:g+a"
    assert msg_id_of("result.updated", {"farm_ids": []}, s) is None
    with pytest.raises(ValueError):
        msg_id_of("grade.done", {"grade_run_id": "g"}, s)


def test_j1_connect_failure_stops_startup(spec):
    """서버에 닿지 않으면 기동이 멈춘다 — 접속 정보는 메시지에 남기지 않는다 (2.2절, 7.11 O5)"""
    q = NatsQueue("nats://o5user:o5secret@127.0.0.1:1", 1, "collector", spec=spec)
    with pytest.raises(SystemExit) as e:
        q.connect()
    assert "o5user" not in str(e.value) and "o5secret" not in str(e.value)


def test_j7_publish_fails_without_server_ack(spec):
    """서버 확인을 못 받는 발행(서버 중지)은 예외 — 부른 쪽 처리가 실패로 남는다 (2.2절)"""
    from testcontainers.core.container import DockerContainer
    from testcontainers.core.waiting_utils import wait_for_logs
    c = DockerContainer("nats:2.10-alpine").with_command("-js").with_exposed_ports(4222)
    c.start()
    try:
        wait_for_logs(c, "Server is ready", timeout=60)
        q = _q(f"nats://{c.get_container_host_ip()}:{c.get_exposed_port(4222)}", spec, "collector")
        q.publish(Message("raw.fetched", _payload("raw.fetched", raw_id="before", api="dtRecent")))
        c.get_wrapped_container().stop(timeout=1)
        with pytest.raises(Exception):
            q.publish(Message("raw.fetched", _payload("raw.fetched", raw_id="after", api="dtRecent")))
        q.close()
    finally:
        c.stop()


# ── J8 ──────────────────────────────────────────────────────────────────────

def test_j8_publisher_first_then_consumer_receives(nats_url, spec):
    pub = _q(nats_url, spec, "collector")            # 소비자 파드 없음 — 그래도 컨슈머 자리가 생긴다
    pub.publish(Message("raw.fetched", _payload("raw.fetched", raw_id="early", api="dtRecent")))
    time.sleep(0.5)
    con = _q(nats_url, spec, "processor")
    got = []
    con.subscribe("raw.fetched", lambda m: got.append(m.payload["raw_id"]))
    t = run_in_thread(con)
    assert _wait(lambda: got == ["early"])
    con.stop(); t.join(10); con.close(); pub.close()


def test_j8_record_interest_stream_without_consumers(nats_url, spec):
    """기록용 — 컨슈머가 0개인 Interest 스트림에 발행한 메시지가 남는가(보고서에 결과를 적는다)"""
    from nats.js import api
    import nats as _nats

    async def go():
        nc = await _nats.connect(nats_url)
        js = nc.jetstream()
        name = spec["stream"]["name"] + "X"
        await js.add_stream(config=api.StreamConfig(name=name, subjects=[f"{name.lower()}.>"],
                                                    retention=api.RetentionPolicy.INTEREST))
        await js.publish(f"{name.lower()}.a", b"x")
        n = (await js.stream_info(name)).state.messages
        await nc.close()
        return n
    n = asyncio.run(go())
    print(f"[J8 기록] 컨슈머 0개 Interest 스트림 발행 뒤 남은 메시지 = {n}")
    assert n in (0, 1)


def _wait(cond, timeout=15.0):
    return wait_until(cond, timeout)


# ── J5 ──────────────────────────────────────────────────────────────────────

def test_j5_other_contract_version_records_event_without_processing_or_redelivery(nats_url, spec):
    """schema가 다른 메시지 → 처리하지 않고 운영 이벤트, 재전달 없음 (2.2절). 판정은 단계 핸들러의 accept_message"""
    from common.contract_check import accept_message

    class _Repo:
        events: list = []

        def insert_ops_events(self, rows):
            self.events.extend(rows)

    repo, processed, deliveries = _Repo(), [], []
    pub = _q(nats_url, spec, "collector")
    con = _q(nats_url, spec, "processor")

    def handler(msg: Message):
        deliveries.append(msg.payload["raw_id"])
        if not accept_message(msg.payload, "raw.fetched", repo):
            return
        processed.append(msg.payload["raw_id"])

    con.subscribe("raw.fetched", handler)
    t = run_in_thread(con)
    old = {**_payload("raw.fetched", raw_id="old1", api="dtRecent"), "schema": "queue-v1"}
    pub.publish(Message("raw.fetched", old, schema="queue-v1"))
    assert _wait(lambda: deliveries == ["old1"])
    time.sleep(1.5)                                   # 재전달 없음
    assert deliveries == ["old1"] and processed == []
    assert [e["event_type"] for e in repo.events] == ["CONTRACT_VERSION_MISMATCH"]
    assert repo.events[0]["detail"]["schema"] == "queue-v1"
    con.stop(); t.join(10)
    assert _wait(lambda: _stream_msgs(pub) == 0)
    pub.close(); con.close()

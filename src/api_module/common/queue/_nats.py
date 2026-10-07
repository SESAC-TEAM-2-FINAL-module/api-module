"""
NATS JetStream 큐 구현 (2.2절 "JetStream 구성", 개정 22)

- 정의는 `contracts/queue/jetstream.json` 한 곳 — 스트림·컨슈머·`Nats-Msg-Id` 키·재전달 간격·비교 필드
- 기동 시 스트림과 **계약의 컨슈머 전부**를 멱등 생성한다. 있으면 비교 필드만 보고, 다르면 멈춘다
- 발행은 서버 확인을 받아야 성공. `Nats-Msg-Id` = `{주제}:{키}`
- 처리(DB 커밋·다음 알림 발행)가 끝난 뒤 ack. 예외면 전달 횟수에 따른 지연 nak, 마지막 전달이면 소진 기록 후 term
- nats-py는 asyncio다. 단계 코드는 동기라 **이벤트 루프를 전용 스레드 하나에 두고** 동기 호출은 그 루프에 넘겨
  결과를 기다린다 — 핸들러 안에서 발행해도 루프가 겹치지 않고, 한 프로세스가 여러 주제를 구독할 수 있다
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import threading
from pathlib import Path
from typing import Callable

from ._interface import Queue, Message

log = logging.getLogger(__name__)

_SPEC_PATH = Path(__file__).parents[4] / "contracts" / "queue" / "jetstream.json"
_FETCH_TIMEOUT_SEC = 1.0      # 구독 하나를 기다리는 시간 — 종료 신호에 빨리 반응하게 짧게
_CALL_TIMEOUT_SEC = 30.0      # 서버 왕복 상한(연결·발행·ack)


class SpecMismatch(Exception):
    """서버의 스트림·컨슈머가 계약과 다르다 — 루프 스레드 안에서는 SystemExit를 던지지 않는다(루프가 죽는다)"""


def load_spec(path: Path | None = None) -> dict:
    return json.loads((path or _SPEC_PATH).read_text(encoding="utf-8"))


def subject_of(topic: str, spec: dict) -> str:
    return f"{spec['subject_prefix']}.{topic}"


def msg_id_of(topic: str, payload: dict, spec: dict) -> str | None:
    """주제별 키 필드로 `{주제}:{키}`를 만든다. 키가 정의되지 않은 주제(`result.updated`)는 None"""
    fields = spec["msg_id_keys"].get(topic)
    if fields is None:
        raise ValueError(f"계약에 없는 주제: {topic}")
    if not fields:
        return None
    missing = [f for f in fields if payload.get(f) in (None, "")]
    if missing:
        raise ValueError(f"{topic} 메시지에 Nats-Msg-Id 키 필드가 없다: {missing}")
    return f"{topic}:" + "+".join(str(payload[f]) for f in fields)


class NatsQueue(Queue):
    """
    운영 진입점은 `open_queue()`로 만든다(`QUEUE_DSN`·`QUEUE_STREAM_REPLICAS` 필수).
    `workload`는 구독할 때 컨슈머 이름을 고르는 데만 쓴다 — 발행만 하는 진입점(collector 등)도 같은 클래스
    """

    def __init__(self, dsn: str, replicas: int, workload: str, *, spec: dict | None = None,
                 on_exhausted: Callable[[dict], None] | None = None,
                 nak_delays: list[float] | None = None) -> None:
        self._dsn = dsn
        self._replicas = replicas
        self._workload = workload
        self._spec = spec or load_spec()
        self._on_exhausted = on_exhausted
        self._nak_delays = nak_delays if nak_delays is not None else self._spec["nak_delays_seconds"]
        self._subs: list[tuple[dict, Callable[[Message], None]]] = []
        self._stop = threading.Event()
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, name="nats-loop", daemon=True)
        self._thread.start()
        self._nc = None
        self._js = None

    # ── 루프 위임 ─────────────────────────────────────────────────────────────

    def _call(self, coro, timeout: float | None = _CALL_TIMEOUT_SEC):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout)

    # ── 연결 · 정의 확인 ──────────────────────────────────────────────────────

    def connect(self) -> None:
        """연결하고 스트림·계약의 컨슈머 전부를 확인·생성한다. 정의가 다르면 기동을 멈춘다(SystemExit)"""
        try:
            self._call(self._aconnect())
        except SpecMismatch as e:
            self.close()
            raise SystemExit(str(e))
        except Exception as e:
            # 접속 정보(사용자·비밀번호가 DSN에 있을 수 있다)를 내보내지 않는다 — 오류 종류만 (7.11 O5)
            self.close()
            raise SystemExit(f"[nats] 큐 연결 실패 — 기동 멈춤: {type(e).__name__}") from None

    async def _aconnect(self) -> None:
        import nats
        self._nc = await nats.connect(self._dsn, connect_timeout=10, max_reconnect_attempts=-1)
        self._js = self._nc.jetstream()
        await self._ensure_stream()
        for c in self._spec["consumers"]:
            await self._ensure_consumer(c)

    def _stream_config(self):
        from nats.js import api
        st = self._spec["stream"]
        return api.StreamConfig(
            name=st["name"], subjects=list(st["subjects"]),
            retention=api.RetentionPolicy(st["retention"]), storage=api.StorageType(st["storage"]),
            max_age=float(st["max_age_seconds"]), duplicate_window=float(st["duplicate_window_seconds"]),
            num_replicas=self._replicas,
        )

    def _consumer_config(self, c: dict):
        from nats.js import api
        d = self._spec["consumer_defaults"]
        return api.ConsumerConfig(
            durable_name=c["name"], filter_subject=subject_of(c["topic"], self._spec),
            ack_policy=api.AckPolicy(d["ack_policy"]), deliver_policy=api.DeliverPolicy(d["deliver_policy"]),
            ack_wait=float(d["ack_wait_seconds"]), max_deliver=int(d["max_deliver"]),
        )

    @staticmethod
    def _diff(have, want, fields: list[str]) -> list[str]:
        out = []
        for f in fields:
            a, b = getattr(have, f, None), getattr(want, f, None)
            if isinstance(a, float) or isinstance(b, float):
                same = a is not None and b is not None and abs(float(a) - float(b)) < 1e-3
            elif isinstance(a, list) or isinstance(b, list):
                same = sorted(a or []) == sorted(b or [])
            else:
                same = a == b
            if not same:
                out.append(f"{f}: 서버={a!r} 계약={b!r}")
        return out

    async def _ensure_stream(self) -> None:
        from nats.js.errors import NotFoundError
        want = self._stream_config()
        try:
            info = await self._js.stream_info(want.name)
        except NotFoundError:
            await self._js.add_stream(config=want)
            log.info("[nats] 스트림 생성: %s", want.name)
            return
        diffs = self._diff(info.config, want, self._spec["compare_fields"]["stream"])
        if diffs:
            raise SpecMismatch(f"[nats] 스트림 {want.name} 정의가 계약과 다르다 — 기동 멈춤: " + "; ".join(diffs))

    async def _ensure_consumer(self, c: dict) -> None:
        from nats.js.errors import NotFoundError
        stream = self._spec["stream"]["name"]
        want = self._consumer_config(c)
        try:
            info = await self._js.consumer_info(stream, c["name"])
        except NotFoundError:
            await self._js.add_consumer(stream, config=want)
            log.info("[nats] 컨슈머 생성: %s", c["name"])
            return
        diffs = self._diff(info.config, want, self._spec["compare_fields"]["consumer"])
        if diffs:
            raise SpecMismatch(f"[nats] 컨슈머 {c['name']} 정의가 계약과 다르다 — 기동 멈춤: " + "; ".join(diffs))

    # ── 발행 ─────────────────────────────────────────────────────────────────

    def publish(self, msg: Message) -> None:
        """서버 확인을 받아야 돌아온다. 실패하면 예외 — 부른 쪽 처리가 실패로 남아 재전달된다"""
        if self._js is None:
            raise RuntimeError("NatsQueue.connect() 전에 발행")
        msg_id = msg_id_of(msg.topic, msg.payload, self._spec)
        headers = {"Nats-Msg-Id": msg_id} if msg_id else None
        data = json.dumps(msg.payload, ensure_ascii=False).encode("utf-8")
        self._call(self._js.publish(subject_of(msg.topic, self._spec), data, headers=headers,
                                    timeout=_CALL_TIMEOUT_SEC))

    # ── 구독 · 수신 루프 ──────────────────────────────────────────────────────

    def subscribe(self, topic: str, handler: Callable[[Message], None]) -> None:
        """이 워크로드의 그 주제 컨슈머에 핸들러를 건다 — 받기 시작은 `run()`"""
        cands = [c for c in self._spec["consumers"] if c["workload"] == self._workload and c["topic"] == topic]
        if len(cands) != 1:
            raise SystemExit(f"[nats] 계약에 워크로드 {self._workload}의 {topic} 컨슈머가 없다")
        self._subs.append((cands[0], handler))

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        """구독한 컨슈머들을 돌아가며 한 건씩 받는다. 메시지가 없어도 끝나지 않는다(점검 C17).
        종료 신호를 받으면 새 메시지를 받지 않고, 처리 중인 메시지는 마친 뒤(ack/nak) 돌아온다"""
        if not self._subs:
            raise RuntimeError("NatsQueue.run(): 구독이 없다")
        stream = self._spec["stream"]["name"]
        pulls = [(c, h, self._call(self._js.pull_subscribe_bind(c["name"], stream=stream)))
                 for c, h in self._subs]
        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGTERM, lambda *_: self._stop.set())
        from nats.errors import TimeoutError as NatsTimeout
        while not self._stop.is_set():
            for c, handler, psub in pulls:
                if self._stop.is_set():
                    break
                try:
                    msgs = self._call(psub.fetch(1, timeout=_FETCH_TIMEOUT_SEC), timeout=_FETCH_TIMEOUT_SEC + 10)
                except (NatsTimeout, asyncio.TimeoutError):
                    continue
                for m in msgs:
                    self._handle(c, handler, m)

    def _handle(self, consumer: dict, handler: Callable[[Message], None], m) -> None:
        from common.metrics import queue_delivery_exhausted_total, queue_redelivered_total
        topic = consumer["topic"]
        try:
            payload = json.loads(m.data.decode("utf-8"))
        except Exception as exc:  # 읽을 수 없는 메시지 — 다시 보내도 같다
            log.error("[nats] %s 메시지 해석 실패 — term: %s", consumer["name"], type(exc).__name__)
            self._call(m.term())
            return
        num = m.metadata.num_delivered if m.metadata else 1
        max_deliver = int(self._spec["consumer_defaults"]["max_deliver"])
        if num > 1:
            queue_redelivered_total.labels(topic=topic, consumer=consumer["name"]).inc()

        # 처리 중 연장 — 핸들러가 ack_wait보다 오래 걸려도 재전달되지 않게 (2.2절 *(제안)*)
        done = threading.Event()
        interval = float(self._spec["in_progress_interval_seconds"])

        def _beat():
            while not done.wait(interval):
                try:
                    self._call(m.in_progress())
                except Exception:
                    pass
        beat = threading.Thread(target=_beat, daemon=True)
        beat.start()
        try:
            handler(Message(topic=topic, payload=payload, schema=payload.get("schema", "")))
        except Exception as exc:
            done.set()
            if num >= max_deliver:
                queue_delivery_exhausted_total.labels(topic=topic, consumer=consumer["name"]).inc()
                info = {"topic": topic, "consumer": consumer["name"], "num_delivered": num,
                        "msg_id": self._safe_msg_id(topic, payload), "error_type": type(exc).__name__,
                        "payload": payload}
                log.error("[nats] 전달 소진 %s (%d회) — %s", consumer["name"], num, type(exc).__name__)
                if self._on_exhausted is not None:
                    try:
                        self._on_exhausted(info)
                    except Exception as e2:
                        log.error("[nats] 소진 기록 실패: %s", type(e2).__name__)
                self._call(m.term())
            else:
                delay = self._nak_delays[min(num - 1, len(self._nak_delays) - 1)]
                log.warning("[nats] %s 처리 실패(%d/%d) — %s초 뒤 재전달: %s",
                            consumer["name"], num, max_deliver, delay, type(exc).__name__)
                self._call(m.nak(delay=delay))
            return
        done.set()
        self._call(m.ack_sync())

    def _safe_msg_id(self, topic: str, payload: dict) -> str | None:
        try:
            return msg_id_of(topic, payload, self._spec)
        except ValueError:
            return None

    def close(self) -> None:
        """연결을 닫고 루프 스레드를 끝낸다. 처리 중 메시지는 run()이 이미 마쳤다(ack/nak)"""
        if self._nc is not None and not self._nc.is_closed:
            try:
                self._call(self._nc.close(), timeout=10)
            except Exception:
                pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(5)


def exhausted_recorder(repo) -> Callable[[dict], None]:
    """전달 소진을 `ops_events` `QUEUE_DELIVERY_EXHAUSTED`로 남기는 콜백 (2.2절). 비밀은 메시지에 없다"""
    def _record(info: dict) -> None:
        from datetime import datetime, timezone
        repo.insert_ops_events([{
            "event_type": "QUEUE_DELIVERY_EXHAUSTED",
            "api": (info.get("payload") or {}).get("api"),
            "occurred_at_utc": datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0),
            "detail": info,
        }])
    return _record


def open_queue(workload: str, repo=None) -> NatsQueue:
    """
    운영 진입점의 큐 — `QUEUE_DSN`·`QUEUE_STREAM_REPLICAS`가 없으면 멈춘다(인메모리로 대체하지 않는다, 12절).
    연결하고 스트림·컨슈머를 확인·생성한 뒤 돌려준다. `repo`가 있으면 전달 소진을 `ops_events`에 남긴다
    """
    dsn = os.environ.get("QUEUE_DSN")
    if not dsn:
        raise SystemExit("QUEUE_DSN이 없다 — 운영 진입점은 큐 없이 기동하지 않는다 (계획서 2.2절)")
    raw = os.environ.get("QUEUE_STREAM_REPLICAS")
    if not raw:
        raise SystemExit("QUEUE_STREAM_REPLICAS가 없다 — 스트림 복제 수를 추정하지 않는다 (계획서 2.2절)")
    try:
        replicas = int(raw)
    except ValueError:
        raise SystemExit("QUEUE_STREAM_REPLICAS는 정수여야 한다")
    q = NatsQueue(dsn, replicas, workload, on_exhausted=exhausted_recorder(repo) if repo is not None else None)
    q.connect()
    return q

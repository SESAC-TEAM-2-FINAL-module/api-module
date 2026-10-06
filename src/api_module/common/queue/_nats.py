"""
NATS JetStream 큐 구현 (2.2절, 개정 22)
- 스트림 AQUASENTINEL, 주제 aquasentinel.> — 기동 시 멱등 생성
- Interest 보존 + max_age 7일, ack_wait 30초, max_deliver 5
- Nats-Msg-Id = {주제}:{키} (중복 창 10분)
- 소진 시 ops_events QUEUE_DELIVERY_EXHAUSTED 후 term
- SIGTERM: 처리 중 메시지 마친 뒤 종료
라이브러리: nats-py (asyncio)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
from typing import Callable

from ._interface import Queue, Message

logger = logging.getLogger(__name__)

_STREAM_NAME = "AQUASENTINEL"
_SUBJECT_PREFIX = "aquasentinel"
_SUBJECT_WILDCARD = f"{_SUBJECT_PREFIX}.>"
_MAX_AGE_SECONDS = 7 * 24 * 3600          # 7일
_ACK_WAIT_SECONDS = 30
_MAX_DELIVER = 5
_NAK_DELAYS = [10, 30, 60, 120]           # 전달 횟수별 지연(초) — 소진 직전까지
_IDLE_HEARTBEAT_SECONDS = 5


def _subject(topic: str) -> str:
    return f"{_SUBJECT_PREFIX}.{topic.replace('.', '_')}"


def _msg_id(topic: str, key: str) -> str:
    return f"{topic}:{key}"


class NatsQueue(Queue):
    """
    NATS JetStream 기반 단계 간 알림 큐 (2.2절, 개정 22).
    운영 진입점은 QUEUE_DSN과 QUEUE_STREAM_REPLICAS 필수 — 없으면 멈춘다.
    테스트·flowtest는 MemoryQueue를 쓴다.
    """

    def __init__(
        self,
        dsn: str,
        replicas: int,
        *,
        consumer_name: str | None = None,
        subscribed_topic: str | None = None,
        repo=None,
    ) -> None:
        self._dsn = dsn
        self._replicas = replicas
        self._consumer_name = consumer_name
        self._subscribed_topic = subscribed_topic
        self._repo = repo
        self._nc = None
        self._js = None
        self._running = False

    # ── 비동기 진입 ──────────────────────────────────────────────────────────

    async def _connect(self) -> None:
        import nats
        self._nc = await nats.connect(self._dsn)
        self._js = self._nc.jetstream()
        await self._ensure_stream()
        await self._ensure_consumers()

    async def _ensure_stream(self) -> None:
        """스트림이 없으면 만들고, 있으면 비교 필드만 확인한다 (개정 22)"""
        import nats.js.api as jsapi
        config = jsapi.StreamConfig(
            name=_STREAM_NAME,
            subjects=[_SUBJECT_WILDCARD],
            retention=jsapi.RetentionPolicy.INTEREST,
            max_age=_MAX_AGE_SECONDS * 1_000_000_000,  # nats-py는 나노초
            num_replicas=self._replicas,
        )
        try:
            info = await self._js.find_stream(_SUBJECT_WILDCARD)
            sc = info.config
            if sc.retention != config.retention or sc.max_age != config.max_age:
                raise SystemExit(
                    f"[nats] 스트림 {_STREAM_NAME} 정의 불일치 — 인프라에 재생성 요청 필요 "
                    f"(retention={sc.retention}, max_age={sc.max_age})"
                )
        except Exception as exc:
            if "not found" in str(exc).lower() or "no stream" in str(exc).lower():
                await self._js.add_stream(config=config)
                logger.info("[nats] 스트림 생성: %s", _STREAM_NAME)
            else:
                raise

    async def _ensure_consumers(self) -> None:
        """계약의 컨슈머를 모두 확인·생성 (Interest 보존 — 컨슈머 없이 발행된 메시지는 유실)"""
        import nats.js.api as jsapi
        _CONSUMER_DEFS = [
            ("processor-raw-fetched",                 "raw.fetched"),
            ("completeness-check-completeness-collected", "completeness.collected"),
            ("interpolation-obs-loaded",              "obs.loaded"),
            ("grading-obs-loaded",                    "obs.loaded"),
            ("grading-interp-done",                   "interp.done"),
            ("evaluation-grade-done",                 "grade.done"),
        ]
        for name, topic in _CONSUMER_DEFS:
            subj = _subject(topic)
            config = jsapi.ConsumerConfig(
                durable_name=name,
                filter_subject=subj,
                ack_policy=jsapi.AckPolicy.EXPLICIT,
                ack_wait=_ACK_WAIT_SECONDS * 1_000_000_000,
                max_deliver=_MAX_DELIVER,
                deliver_policy=jsapi.DeliverPolicy.ALL,
            )
            try:
                info = await self._js.consumer_info(_STREAM_NAME, name)
                cc = info.config
                if cc.ack_wait != config.ack_wait or cc.max_deliver != config.max_deliver:
                    raise SystemExit(
                        f"[nats] 컨슈머 {name} 정의 불일치 — 인프라에 재생성 요청 필요"
                    )
            except Exception as exc:
                if "not found" in str(exc).lower() or "consumer not found" in str(exc).lower():
                    await self._js.add_consumer(_STREAM_NAME, config)
                    logger.info("[nats] 컨슈머 생성: %s", name)
                else:
                    raise

    # ── 발행 ─────────────────────────────────────────────────────────────────

    def publish(self, msg: Message) -> None:
        """동기 래퍼 — 운영 진입점의 asyncio 이벤트 루프 안에서 호출하는 경우에는 run_in_loop를 쓴다"""
        key = msg.payload.get("raw_id") or msg.payload.get("load_id") or \
              msg.payload.get("run_id") or \
              (f"{msg.payload.get('grade_run_id')}+{msg.payload.get('axis')}" if "grade_run_id" in msg.payload else None)
        asyncio.get_event_loop().run_until_complete(self._publish_async(msg, key or ""))

    async def _publish_async(self, msg: Message, key: str) -> None:
        subj = _subject(msg.topic)
        data = json.dumps(msg.payload, ensure_ascii=False).encode("utf-8")
        headers = {"Nats-Msg-Id": _msg_id(msg.topic, key)} if key else {}
        ack = await self._js.publish(subj, data, headers=headers)
        logger.debug("[nats] 발행: %s seq=%s", subj, ack.seq)

    # ── 수신 루프 ────────────────────────────────────────────────────────────

    async def _run_consumer(self, handler: Callable[[Message], None]) -> None:
        """durable pull 컨슈머 수신 루프 — SIGTERM이면 처리 중 메시지 마친 뒤 종료"""
        if not self._consumer_name or not self._subscribed_topic:
            raise RuntimeError("NatsQueue.run(): consumer_name과 subscribed_topic 필요")

        sub = await self._js.pull_subscribe(
            _subject(self._subscribed_topic),
            self._consumer_name,
        )
        self._running = True

        def _handle_sigterm(*_):
            logger.info("[nats] SIGTERM 수신 — 현재 메시지 처리 후 종료")
            self._running = False

        signal.signal(signal.SIGTERM, _handle_sigterm)

        while self._running:
            try:
                msgs = await sub.fetch(1, timeout=_IDLE_HEARTBEAT_SECONDS)
            except asyncio.TimeoutError:
                continue
            except Exception as exc:
                logger.warning("[nats] fetch 오류: %s", exc)
                await asyncio.sleep(1)
                continue

            for nat_msg in msgs:
                await self._handle_one(nat_msg, handler)

    async def _handle_one(self, nat_msg, handler: Callable[[Message], None]) -> None:
        """메시지 하나 처리 — ack/nak 전략 (개정 22)"""
        try:
            raw = json.loads(nat_msg.data.decode("utf-8"))
        except Exception as exc:
            logger.error("[nats] 메시지 JSON 파싱 실패: %s", exc)
            await nat_msg.term()
            return

        num_delivered = nat_msg.metadata.num_delivered if nat_msg.metadata else 1
        topic = raw.get("topic", "")
        msg = Message(topic=topic, payload=raw)

        try:
            handler(msg)
            await nat_msg.ack()
        except Exception as exc:
            logger.error("[nats] 핸들러 오류 (전달 %d/%d): %s", num_delivered, _MAX_DELIVER, exc)
            if num_delivered >= _MAX_DELIVER:
                # 소진 — ops_events 기록 후 term
                await self._record_exhausted(topic, raw, num_delivered)
                await nat_msg.term()
            else:
                delay_idx = min(num_delivered - 1, len(_NAK_DELAYS) - 1)
                delay = _NAK_DELAYS[delay_idx]
                await nat_msg.nak(delay=delay)

    async def _record_exhausted(self, topic: str, raw: dict, num_delivered: int) -> None:
        if self._repo is None:
            logger.warning("[nats] QUEUE_DELIVERY_EXHAUSTED — repo 없어 ops_events 미기록: %s", topic)
            return
        from datetime import datetime, timezone
        try:
            self._repo.insert_ops_events([{
                "event_type": "QUEUE_DELIVERY_EXHAUSTED",
                "api": raw.get("api"),
                "occurred_at_utc": datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0),
                "detail": {"topic": topic, "num_delivered": num_delivered,
                           "raw_id": raw.get("raw_id") or raw.get("load_id")},
            }])
        except Exception as exc:
            logger.error("[nats] ops_events 기록 실패: %s", exc)

    def run(self, handler: Callable[[Message], None]) -> None:
        """수신 루프 진입 — asyncio 이벤트 루프를 만들어 블로킹 실행"""
        asyncio.run(self._run_loop(handler))

    async def _run_loop(self, handler: Callable[[Message], None]) -> None:
        await self._connect()
        try:
            await self._run_consumer(handler)
        finally:
            if self._nc:
                await self._nc.drain()

    # ── 팩토리 ───────────────────────────────────────────────────────────────

    @classmethod
    def from_env(cls, consumer_name: str, subscribed_topic: str, repo=None) -> "NatsQueue":
        """운영 진입점 팩토리 — QUEUE_DSN, QUEUE_STREAM_REPLICAS 필수"""
        dsn = os.environ.get("QUEUE_DSN")
        replicas_raw = os.environ.get("QUEUE_STREAM_REPLICAS")
        if not dsn:
            raise SystemExit("QUEUE_DSN이 설정되지 않았습니다 — 운영 진입점에서 큐가 필요합니다 (2.2절)")
        if not replicas_raw:
            raise SystemExit("QUEUE_STREAM_REPLICAS가 설정되지 않았습니다 (2.2절)")
        try:
            replicas = int(replicas_raw)
        except ValueError:
            raise SystemExit(f"QUEUE_STREAM_REPLICAS 형식 오류(정수 필요): {replicas_raw}")
        return cls(
            dsn=dsn,
            replicas=replicas,
            consumer_name=consumer_name,
            subscribed_topic=subscribed_topic,
            repo=repo,
        )

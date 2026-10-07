"""로컬 개발용 인메모리 큐"""
from __future__ import annotations
from collections import defaultdict
from typing import Callable

from ._interface import Queue, Message


class MemoryQueue(Queue):
    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable]] = defaultdict(list)
        self._published: list[Message] = []

    def publish(self, msg: Message) -> None:
        self._published.append(msg)
        for handler in self._handlers.get(msg.topic, []):
            handler(msg)

    def subscribe(self, topic: str, handler: Callable[[Message], None]) -> None:
        self._handlers[topic].append(handler)

    def run(self) -> None:
        """인메모리는 발행 호출 안에서 바로 전달하므로 기다릴 것이 없다 — 테스트·시험 실행기 전용"""
        return

    def drain(self, topic: str | None = None) -> list[Message]:
        if topic is None:
            return list(self._published)
        return [m for m in self._published if m.topic == topic]

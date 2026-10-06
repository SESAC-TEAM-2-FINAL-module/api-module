"""단계 간 알림 큐 인터페이스 (2.2절)"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Message:
    topic: str
    payload: dict
    schema: str = "queue-v2"


class Queue:
    def publish(self, msg: Message) -> None:
        raise NotImplementedError

    def subscribe(self, topic: str, handler: Callable[[Message], None]) -> None:
        raise NotImplementedError

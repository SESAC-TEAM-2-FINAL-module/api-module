"""단계 간 알림 큐 인터페이스 (2.2절)"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable

from common.contract_check._message import QUEUE_CONTRACT


@dataclass
class Message:
    topic: str
    payload: dict
    schema: str = QUEUE_CONTRACT


class Queue:
    def publish(self, msg: Message) -> None:
        raise NotImplementedError

    def subscribe(self, topic: str, handler: Callable[[Message], None]) -> None:
        raise NotImplementedError

    def run(self) -> None:
        """구독한 주제를 받으며 계속 돈다 — 운영 컨슈머 진입점의 수신 대기 (2.2절, 점검 C17)"""
        raise NotImplementedError

    def close(self) -> None:
        """연결 정리 — 인메모리는 할 일 없음"""

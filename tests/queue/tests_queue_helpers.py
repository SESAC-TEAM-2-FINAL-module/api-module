"""tests/queue 공용 도우미 — 수신 루프를 스레드로 돌리고 조건을 기다린다"""
from __future__ import annotations

import threading
import time


def run_in_thread(q) -> threading.Thread:
    t = threading.Thread(target=q.run, daemon=True)
    t.start()
    return t


def wait_until(cond, timeout: float = 15.0, step: float = 0.05) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(step)
    return cond()

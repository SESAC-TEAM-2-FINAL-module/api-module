"""
7.11 J·O 검사용 테스트 컨테이너 — NATS JetStream 서버, S3 호환 MinIO (개정 22).
운영·공유 자원에 접속하지 않는다. Docker가 없으면 건너뛴다.
"""
from __future__ import annotations

import copy
import uuid

import pytest

try:
    from testcontainers.core.container import DockerContainer
    from testcontainers.core.waiting_utils import wait_for_logs
    _HAS_TC = True
except ImportError:
    _HAS_TC = False


@pytest.fixture(scope="session")
def nats_url():
    if not _HAS_TC:
        pytest.skip("testcontainers 미설치")
    c = DockerContainer("nats:2.10-alpine").with_command("-js").with_exposed_ports(4222)
    with c:
        wait_for_logs(c, "Server is ready", timeout=60)
        yield f"nats://{c.get_container_host_ip()}:{c.get_exposed_port(4222)}"


@pytest.fixture()
def spec():
    """테스트마다 스트림·주제 접두를 따로 둔 계약 사본 — 같은 서버에서 서로 섞이지 않게.
    재전달 간격은 줄여 주입한다(7.11절 — 값은 정의 파일, 간격만 테스트용)"""
    from common.queue import load_spec
    s = copy.deepcopy(load_spec())
    tag = uuid.uuid4().hex[:8]
    s["stream"]["name"] = f"T{tag}"
    s["subject_prefix"] = f"t{tag}"
    s["stream"]["subjects"] = [f"t{tag}.>"]
    s["nak_delays_seconds"] = [0.05]
    s["consumer_defaults"]["ack_wait_seconds"] = 5
    s["in_progress_interval_seconds"] = 1
    return s

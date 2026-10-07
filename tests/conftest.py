import sys
from pathlib import Path

# src/api_module을 sys.path에 추가
sys.path.insert(0, str(Path(__file__).parents[1] / "src" / "api_module"))

import uuid

import pytest

# ── 7.11 O1~O5 — S3 호환 테스트 컨테이너 (개정 22) ────────────────────────────
# 공식 minio/minio 이미지가 Docker Hub에서 내려가 Chainguard 빌드(MinIO 서버 그대로)를 쓴다.
# 계정은 일회용 표식 문자열 — `.env`에 쓰지 않는다. O5가 이 표식이 출력에 없는지 본다
MINIO_IMAGE = "cgr.dev/chainguard/minio:latest"
S3_MARK_USER = "o5markuser7f3a"
S3_MARK_SECRET = "o5marksecret9b1e2c"


@pytest.fixture(scope="session")
def minio_endpoint():
    try:
        from testcontainers.core.container import DockerContainer
        from testcontainers.core.waiting_utils import wait_for_logs
    except ImportError:
        pytest.skip("testcontainers 미설치")
    c = (DockerContainer(MINIO_IMAGE).with_command("server /data")
         .with_env("MINIO_ROOT_USER", S3_MARK_USER).with_env("MINIO_ROOT_PASSWORD", S3_MARK_SECRET)
         .with_exposed_ports(9000))
    with c:
        wait_for_logs(c, "API:", timeout=60)
        yield f"http://{c.get_container_host_ip()}:{c.get_exposed_port(9000)}"


@pytest.fixture()
def s3_env(minio_endpoint, monkeypatch):
    """테스트마다 새 버킷 + 기본 자격 증명 체인이 읽는 환경변수. 원문 저장소 전역 구현체는 비운다.
    반환: {"endpoint", "bucket", "client", "marks"}"""
    import boto3
    import common.raw_store._store as store_mod
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", S3_MARK_USER)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", S3_MARK_SECRET)
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("RAW_STORE_ENDPOINT", minio_endpoint)
    monkeypatch.delenv("RAW_STORE_PATH", raising=False)
    bucket = f"raw-{uuid.uuid4().hex[:12]}"
    client = boto3.client("s3", endpoint_url=minio_endpoint)
    client.create_bucket(Bucket=bucket)
    monkeypatch.setattr(store_mod, "_store", None)
    yield {"endpoint": minio_endpoint, "bucket": bucket, "client": client,
           "marks": (S3_MARK_USER, S3_MARK_SECRET)}

"""
원문 저장 인터페이스 (2.3절, 개정 22)
참고: $SRC_IDW/src/collector.py save_raw_response() (B 수정본)
사용 금지: $SRC_IDW/stage2_collect.py _save_raw() — 200,000자 절단
키: raw/{api}/{yyyy}/{mm}/{dd}/{epoch_ms}_{tag}.json (: 금지 — Windows 불가)
body는 DB에 넣지 않는다 — 객체 저장소에, DB에는 색인 행만
"""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def _raw_key(api: str, tag: str, fetched_at: str, epoch_ms: int | None = None) -> str:
    dt = datetime.strptime(fetched_at, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    ms = epoch_ms if epoch_ms is not None else int(dt.timestamp() * 1000)
    return f"raw/{api}/{dt.strftime('%Y')}/{dt.strftime('%m')}/{dt.strftime('%d')}/{ms}_{tag}.json"


class RawStore:
    def put(self, key: str, content: dict) -> str:
        raise NotImplementedError

    def get_meta(self, key: str) -> dict | None:
        raise NotImplementedError

    def get_body(self, key: str) -> str | None:
        raise NotImplementedError

    def list_keys(self, prefix: str) -> list[str]:
        """접두 아래 객체 키 전부 (순서 보장 없음) — 적조 직전 원문 대조가 날짜 폴더 단위로 쓴다 (3.3절, 개정 18)"""
        raise NotImplementedError


class LocalDiskStore(RawStore):
    def __init__(self, base_dir: str) -> None:
        self._base = Path(base_dir)

    def put(self, key: str, content: dict) -> str:
        path = self._base / key
        # 덮어쓰기 금지 — S3 조건부 쓰기(If-None-Match)와 같은 의미 (2.3절, 개정 22)
        if path.exists():
            raise FileExistsError(f"원문 키 충돌 — 이미 존재함: {key}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
        return key

    def get_meta(self, key: str) -> dict | None:
        path = self._base / key
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        # collector는 메타만 읽을 수 있다 — body 제외
        return {k: v for k, v in data.items() if k != "body"}

    def get_body(self, key: str) -> str | None:
        path = self._base / key
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8")).get("body")

    def list_keys(self, prefix: str) -> list[str]:
        folder = self._base / prefix
        if not folder.is_dir():
            return []
        return [p.relative_to(self._base).as_posix() for p in folder.rglob("*.json") if p.is_file()]


class S3Store(RawStore):
    """S3(또는 MinIO) 원문 저장소 (2.3절, 개정 22).
    RAW_STORE_DSN = s3://<버킷>[/<접두>]
    인증: 기본 자격 증명 체인(IRSA 등) — 키를 이미지에 넣지 않는다.
    로컬 MinIO: RAW_STORE_ENDPOINT 로 엔드포인트 지정.
    """

    def __init__(self, bucket: str, prefix: str = "", endpoint_url: str | None = None) -> None:
        import logging
        import boto3
        from botocore.config import Config
        # botocore는 DEBUG에서 요청 헤더(Credential=<접근 키 ID>/…)를 남긴다 — 로그 수준을 올려도 계정이 새지 않게 (7.11 O5)
        _boto_log = logging.getLogger("botocore")
        if _boto_log.getEffectiveLevel() < logging.INFO:
            _boto_log.setLevel(logging.INFO)
        kwargs: dict = {"config": Config(retries={"max_attempts": 3, "mode": "standard"})}
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url
        self._s3 = boto3.client("s3", **kwargs)
        self._bucket = bucket
        self._prefix = prefix.rstrip("/")

    def check(self) -> None:
        """기동 시 버킷 접근 1회 확인 — 실패하면 멈춘다 (2.3절, 개정 22)"""
        try:
            self._s3.head_bucket(Bucket=self._bucket)
        except Exception as exc:
            raise SystemExit(f"원문 저장소(S3) 접근 실패 — 기동 멈춤: {type(exc).__name__}")

    def _full_key(self, key: str) -> str:
        return f"{self._prefix}/{key}" if self._prefix else key

    def put(self, key: str, content: dict) -> str:
        body = json.dumps(content, ensure_ascii=False).encode("utf-8")
        fkey = self._full_key(key)
        # 조건부 쓰기 — 이미 존재하면 덮어쓰지 않는다 (2.3절, 개정 22)
        try:
            self._s3.put_object(
                Bucket=self._bucket,
                Key=fkey,
                Body=body,
                ContentType="application/json",
                IfNoneMatch="*",
            )
        except self._s3.exceptions.ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("PreconditionFailed", "ConditionalRequestConflict"):
                raise FileExistsError(f"원문 키 충돌 — 이미 존재함: {key}") from exc
            raise
        return key

    def get_meta(self, key: str) -> dict | None:
        import botocore.exceptions
        fkey = self._full_key(key)
        try:
            resp = self._s3.get_object(Bucket=self._bucket, Key=fkey)
        except botocore.exceptions.ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                return None
            raise
        data = json.loads(resp["Body"].read().decode("utf-8"))
        return {k: v for k, v in data.items() if k != "body"}

    def get_body(self, key: str) -> str | None:
        import botocore.exceptions
        fkey = self._full_key(key)
        try:
            resp = self._s3.get_object(Bucket=self._bucket, Key=fkey)
        except botocore.exceptions.ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                return None
            raise
        return json.loads(resp["Body"].read().decode("utf-8")).get("body")

    def list_keys(self, prefix: str) -> list[str]:
        full_prefix = self._full_key(prefix)
        paginator = self._s3.get_paginator("list_objects_v2")
        keys = []
        for page in paginator.paginate(Bucket=self._bucket, Prefix=full_prefix):
            for obj in page.get("Contents", []):
                obj_key = obj["Key"]
                # 내부 접두 제거 → 원문 키 형식으로 반환
                if self._prefix:
                    obj_key = obj_key.removeprefix(self._prefix + "/")
                keys.append(obj_key)
        return keys


_store: RawStore | None = None
_image: str = "unknown"


def _get_store() -> RawStore:
    """운영 진입점은 RAW_STORE_DSN 필수 — 없으면 멈춘다 (2.3절, 개정 22).
    테스트·flowtest는 init_store()로 구현체를 직접 넘긴다.
    """
    global _store
    if _store is None:
        dsn = os.environ.get("RAW_STORE_DSN")
        if not dsn:
            raise SystemExit(
                "RAW_STORE_DSN이 설정되지 않았습니다 — 운영 진입점에서 원문 저장소가 필요합니다 (2.3절)"
            )
        # s3://<버킷>[/<접두>]
        if not dsn.startswith("s3://"):
            raise SystemExit(f"RAW_STORE_DSN 형식 오류 (s3://<버킷>[/<접두>] 필요): {dsn}")
        rest = dsn[5:]
        parts = rest.split("/", 1)
        bucket = parts[0]
        prefix = parts[1] if len(parts) > 1 else ""
        endpoint_url = os.environ.get("RAW_STORE_ENDPOINT")
        _store = S3Store(bucket=bucket, prefix=prefix, endpoint_url=endpoint_url or None)
    return _store


def init_store(store: RawStore | None) -> None:
    """테스트·flowtest용 — 구현체를 직접 주입한다(None이면 비운다). 운영 진입점은 open_raw_store()"""
    global _store
    _store = store


def open_raw_store(image: str) -> RawStore:
    """운영 진입점 `main()` 층에서 부른다 — `RAW_STORE_DSN`(s3://)이 없거나 버킷에 닿지 않으면 멈춘다.
    로컬 디스크로 대체하지 않는다. `RAW_STORE_PATH`는 읽지 않는다 (2.3절, 개정 22)"""
    global _image
    _image = image
    store = _get_store()
    check = getattr(store, "check", None)
    if check is not None:
        check()
    return store


def save_raw(api: str, tag: str, fetch_result: dict) -> str:
    """fetch_result: common/http/fetch()의 반환값. 반환: raw_id (객체 키)"""
    fetched_at = fetch_result.get("fetched_at") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    epoch_ms = fetch_result.get("_fetched_ms")
    key = _raw_key(api, tag, fetched_at, epoch_ms=epoch_ms)
    try:
        _get_store().put(key, fetch_result)
    except Exception:
        # 같은 키 충돌(FileExistsError)도 오류다 — 덮어쓰지 않고, raw.fetched도 내지 않는다 (2.3절, 개정 22)
        _count_error("put")
        raise
    return key


def _count_error(op: str) -> None:
    from common.metrics import raw_store_errors_total
    raw_store_errors_total.labels(op=op, image=_image).inc()


def get_raw_meta(raw_id: str) -> dict | None:
    try:
        return _get_store().get_meta(raw_id)
    except Exception:
        _count_error("get")
        raise


def get_raw_body(raw_id: str) -> str | None:
    try:
        return _get_store().get_body(raw_id)
    except Exception:
        _count_error("get")
        raise


def list_raw_keys(prefix: str) -> list[str]:
    try:
        return _get_store().list_keys(prefix)
    except Exception:
        _count_error("list")
        raise

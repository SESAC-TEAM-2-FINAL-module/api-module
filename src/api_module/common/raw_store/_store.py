"""
원문 저장 인터페이스 (2.3절)
참고: $SRC_IDW/src/collector.py save_raw_response() (B 수정본)
사용 금지: $SRC_IDW/stage2_collect.py _save_raw() — 200,000자 절단
키: raw/{api}/{yyyy}/{mm}/{dd}/{epoch_ms}_{tag}.json (: 금지 — Windows 불가)
body는 DB에 넣지 않는다 — 객체 저장소에, DB에는 색인 행만
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path


def _raw_key(api: str, tag: str, fetched_at: str) -> str:
    dt = datetime.strptime(fetched_at, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    epoch_ms = int(dt.timestamp() * 1000)
    return f"raw/{api}/{dt.strftime('%Y')}/{dt.strftime('%m')}/{dt.strftime('%d')}/{epoch_ms}_{tag}.json"


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


_store: RawStore | None = None


def _get_store() -> RawStore:
    """
    지금 구현은 로컬 디스크(`RAW_STORE_PATH`)뿐이다. 객체 저장소 구현은 인프라 확정 뒤에 붙인다(계획서 11절 미결).
    `RAW_STORE_DSN`이 설정됐는데 지원하는 구현이 없으면 멈춘다 — 인프라가 저장소를 연결했는데 로컬 디스크에
    조용히 쓰는 것을 막는다(단계 간에 원문이 공유되지 않는다)
    """
    global _store
    if _store is None:
        import os
        if os.environ.get("RAW_STORE_DSN"):
            raise SystemExit("RAW_STORE_DSN이 설정됐으나 객체 저장소 구현이 이 이미지에 없다 — 로컬 디스크로 대체하지 않는다 (계획서 11절)")
        base = os.environ.get("RAW_STORE_PATH", "raw_data")
        _store = LocalDiskStore(base)
    return _store


def save_raw(api: str, tag: str, fetch_result: dict) -> str:
    """fetch_result: common/http/fetch()의 반환값. 반환: raw_id (객체 키)"""
    fetched_at = fetch_result.get("fetched_at") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    key = _raw_key(api, tag, fetched_at)
    _get_store().put(key, fetch_result)
    return key


def get_raw_meta(raw_id: str) -> dict | None:
    return _get_store().get_meta(raw_id)


def get_raw_body(raw_id: str) -> str | None:
    return _get_store().get_body(raw_id)


def list_raw_keys(prefix: str) -> list[str]:
    return _get_store().list_keys(prefix)

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


_store: RawStore | None = None


def _get_store() -> RawStore:
    global _store
    if _store is None:
        import os
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

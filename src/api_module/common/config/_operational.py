"""
운영 조정 로딩과 스키마 검사 (2.0.6절)
ConfigMap이 없거나 스키마와 다르면 멈추고 보고한다
operational.initial.yaml이나 코드 기본값으로 조용히 대체하지 않는다
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path

import yaml

_SCHEMA_VERSION = "operational-v1"
_PLACEHOLDER = "<미결>"


def _find_placeholders(d: dict, path: str = "") -> list[str]:
    found = []
    for k, v in d.items():
        p = f"{path}.{k}" if path else k
        if v == _PLACEHOLDER:
            found.append(p)
        elif isinstance(v, dict):
            found.extend(_find_placeholders(v, p))
    return found


def load_operational(path: str | None = None) -> dict:
    env_path = path or os.environ.get("OPERATIONAL_CONFIG_PATH")
    if not env_path:
        raise SystemExit(
            "운영 조정 ConfigMap 없음: OPERATIONAL_CONFIG_PATH 미설정. "
            "기본값으로 대체하지 않는다."
        )
    config_path = Path(env_path)
    if not config_path.exists():
        raise SystemExit(f"운영 조정 파일 없음: {config_path}")

    with config_path.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    errors: list[str] = []

    if cfg.get("schema") != _SCHEMA_VERSION:
        errors.append(f"schema 버전 불일치: {cfg.get('schema')!r} != {_SCHEMA_VERSION!r}")

    placeholders = _find_placeholders(cfg)
    for p in placeholders:
        errors.append(f"{p}: 자리 표시 미결 값")

    if errors:
        raise SystemExit("운영 조정 스키마 검사 실패:\n" + "\n".join(f"  - {e}" for e in errors))

    return cfg


def operational_hash(cfg: dict) -> str:
    canonical = json.dumps(cfg, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]

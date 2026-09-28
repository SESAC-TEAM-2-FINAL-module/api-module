"""판정 정의 로딩 (config/definitions.yaml — 이미지에 포함, CI 게이트 대조)"""
from __future__ import annotations
from pathlib import Path

import yaml

_DEFAULT_PATH = Path(__file__).parents[4] / "config" / "definitions.yaml"


def load_definitions(path: str | None = None) -> dict:
    p = Path(path) if path else _DEFAULT_PATH
    with p.open(encoding="utf-8") as f:
        return yaml.safe_load(f)

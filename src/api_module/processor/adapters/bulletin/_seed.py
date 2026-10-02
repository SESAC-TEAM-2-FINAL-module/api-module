"""적조 시드 적재 — seeds/ YAML → DB (areas, area_aliases, axis_coverage). (개정 19: 읽기는 common.seeds)"""
from __future__ import annotations

from common.seeds import load_seeds, _read_seed  # noqa: F401 — 하위 호환 재내보내기

__all__ = ["load_seeds"]

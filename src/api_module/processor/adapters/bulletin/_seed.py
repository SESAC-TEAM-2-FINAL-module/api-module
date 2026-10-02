"""적조 시드 적재 — seeds/ YAML → DB (areas, area_aliases, axis_coverage)."""
from __future__ import annotations

from pathlib import Path

import yaml

from common.repository.base import AbstractRepository

_SEEDS_DIR = Path(__file__).parents[5] / "seeds"


def load_seeds(repo: AbstractRepository) -> None:
    """seeds/ 세 파일을 순서대로 upsert한다. 파일이 없으면 건너뛴다."""
    _load_areas(repo)
    _load_area_aliases(repo)
    _load_axis_coverage(repo)


def _load_areas(repo: AbstractRepository) -> None:
    path = _SEEDS_DIR / "areas.yaml"
    if not path.exists():
        return
    data = yaml.safe_load(path.read_text("utf-8")) or {}
    rows = data.get("areas") or []
    if rows:
        repo.upsert_areas(rows)


def _load_area_aliases(repo: AbstractRepository) -> None:
    path = _SEEDS_DIR / "area_aliases.yaml"
    if not path.exists():
        return
    data = yaml.safe_load(path.read_text("utf-8")) or {}
    rows = data.get("aliases") or []
    if rows:
        repo.upsert_area_aliases(rows)


def _load_axis_coverage(repo: AbstractRepository) -> None:
    path = _SEEDS_DIR / "axis_coverage.yaml"
    if not path.exists():
        return
    data = yaml.safe_load(path.read_text("utf-8")) or {}
    rows = data.get("coverage") or []
    if rows:
        repo.upsert_axis_coverage(rows)

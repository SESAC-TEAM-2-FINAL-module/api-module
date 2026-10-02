"""
해역 시드 읽기·적재·대조 (개정 19 — I-15).

읽기: read_areas / read_area_aliases / read_axis_coverage → list[dict]
     파일 없음·빔·항목 형식 오류면 RuntimeError (점검 C11)
대조: compare_seed_tables(repo, defs, ref_date) → list[str]  (빈 목록 = 일치)
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from common.repository.base import AbstractRepository

_SEEDS_DIR = Path(__file__).parents[3] / "seeds"

_PENDING_MARK = "<미결>"


def _is_pending(val: object) -> bool:
    return val is None or str(val).strip() in (_PENDING_MARK, "")


# ─────────────────────────────────────────────────────────────────────────────
# 파일 읽기
# ─────────────────────────────────────────────────────────────────────────────

def _read_seed(filename: str, key: str) -> list[dict]:
    """YAML 시드 파일을 읽어 목록을 반환한다. 파일 없음·빔이면 RuntimeError."""
    path = _SEEDS_DIR / filename
    if not path.exists():
        raise RuntimeError(f"적조 해역 시드 없음: {filename}")
    data = yaml.safe_load(path.read_text("utf-8"))
    rows = data.get(key) if isinstance(data, dict) else None
    if not rows:
        raise RuntimeError(f"적조 해역 시드가 비었다: {filename} ({key})")
    return rows


def read_areas() -> list[dict]:
    """areas.yaml → 전체 목록."""
    return _read_seed("areas.yaml", "areas")


def read_area_aliases() -> list[dict]:
    """area_aliases.yaml → 전체 목록."""
    return _read_seed("area_aliases.yaml", "aliases")


def read_axis_coverage() -> list[dict]:
    """axis_coverage.yaml → 전체 목록."""
    return _read_seed("axis_coverage.yaml", "coverage")


def load_area_aliases_dict() -> dict[str, str]:
    """{alias_key: area_id} — 형식 오류 행이 있으면 RuntimeError."""
    entries = read_area_aliases()
    bad = [e for e in entries if not isinstance(e, dict) or not e.get("alias_key") or not e.get("area_id")]
    if bad:
        raise RuntimeError(f"적조 별칭 시드 항목 형식 오류 {len(bad)}건: area_aliases.yaml")
    return {e["alias_key"]: e["area_id"] for e in entries}


def load_seeds(repo: AbstractRepository) -> None:
    """seeds/ 세 파일을 순서대로 upsert한다. 파일이 없거나 비었으면 멈춘다."""
    repo.upsert_areas(read_areas())
    repo.upsert_area_aliases(read_area_aliases())
    repo.upsert_axis_coverage(read_axis_coverage())


# ─────────────────────────────────────────────────────────────────────────────
# 시드 대조 — seed-check (4.3절, 개정 19)
# ─────────────────────────────────────────────────────────────────────────────

def _float_eq(a: object, b: object) -> bool:
    try:
        return abs(float(a) - float(b)) < 1e-9
    except (TypeError, ValueError):
        return a == b


def _check_areas(repo: AbstractRepository, diffs: list[str]) -> None:
    seed_rows = {r["area_id"]: r for r in read_areas()}
    db_rows = {r["area_id"]: r for r in repo.get_areas()}

    for aid in sorted(seed_rows):
        if aid not in db_rows:
            diffs.append(f"[①] areas 빠진 행: {aid}")
        else:
            s, d = seed_rows[aid], db_rows[aid]
            for col in ("name",):
                if s.get(col) != d.get(col):
                    diffs.append(f"[①] areas {aid}.{col}: DB={d.get(col)!r}, 시드={s.get(col)!r}")
            for col in ("center_lat", "center_lng", "radius_km"):
                if not _float_eq(s.get(col), d.get(col)):
                    diffs.append(f"[①] areas {aid}.{col}: DB={d.get(col)}, 시드={s.get(col)}")

    for aid in sorted(db_rows):
        if aid not in seed_rows:
            diffs.append(f"[①] areas 더 있는 행: {aid}")


def _check_area_aliases(repo: AbstractRepository, diffs: list[str]) -> None:
    seed_rows = {r["alias_key"]: r for r in read_area_aliases()}
    db_rows = {r["alias_key"]: r for r in repo.get_area_aliases()}

    for key in sorted(seed_rows):
        if key not in db_rows:
            diffs.append(f"[①] area_aliases 빠진 행: {key!r}")
        else:
            s, d = seed_rows[key], db_rows[key]
            for col in ("area_id", "source"):
                if s.get(col) != d.get(col):
                    diffs.append(f"[①] area_aliases {key!r}.{col}: DB={d.get(col)!r}, 시드={s.get(col)!r}")

    for key in sorted(db_rows):
        if key not in seed_rows:
            diffs.append(f"[①] area_aliases 더 있는 행: {key!r}")


def _normalize_months(val: object) -> list | None:
    if val is None:
        return None
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return val
    return val


def _check_axis_coverage(repo: AbstractRepository, diffs: list[str]) -> None:
    seed_rows = {(r["area_id"], r["axis"]): r for r in read_axis_coverage()}
    db_rows = {(r["area_id"], r["axis"]): r for r in repo.get_axis_coverage()}

    for pk in sorted(seed_rows):
        if pk not in db_rows:
            diffs.append(f"[①] axis_coverage 빠진 행: {pk}")
        else:
            s, d = seed_rows[pk], db_rows[pk]
            if bool(s.get("covered")) != bool(d.get("covered")):
                diffs.append(f"[①] axis_coverage {pk}.covered: DB={d.get('covered')}, 시드={s.get('covered')}")
            sm_s = _normalize_months(s.get("season_months"))
            sm_d = _normalize_months(d.get("season_months"))
            if sm_s != sm_d:
                diffs.append(f"[①] axis_coverage {pk}.season_months: DB={sm_d!r}, 시드={sm_s!r}")
            if s.get("reason") != d.get("reason"):
                diffs.append(f"[①] axis_coverage {pk}.reason: DB={d.get('reason')!r}, 시드={s.get('reason')!r}")

    for pk in sorted(db_rows):
        if pk not in seed_rows:
            diffs.append(f"[①] axis_coverage 더 있는 행: {pk}")


def _check_referential_integrity(repo: AbstractRepository, diffs: list[str]) -> None:
    area_ids = {r["area_id"] for r in repo.get_areas()}

    for r in repo.get_area_aliases():
        if r["area_id"] not in area_ids:
            diffs.append(f"[②] area_aliases {r['alias_key']!r}.area_id={r['area_id']!r} → areas에 없음")

    for r in repo.get_axis_coverage():
        if r["area_id"] not in area_ids:
            diffs.append(f"[②] axis_coverage ({r['area_id']}, {r['axis']}).area_id → areas에 없음")


def _check_bulletin_area_ids(
    repo: AbstractRepository, defs: dict, diffs: list[str], ref_date: date
) -> None:
    b_cfg = (defs or {}).get("bulletin") or {}
    window_days_val = b_cfg.get("current_window_days")
    if _is_pending(window_days_val):
        diffs.append("[③] bulletin.current_window_days 미결 — 속보 area_id 검사 건너뜀")
        return

    window_days = int(window_days_val)
    area_ids = {r["area_id"] for r in repo.get_areas()}
    bda_area_ids = repo.get_bulletin_detail_areas_in_window(window_days, ref_date)

    for aid in sorted(bda_area_ids):
        if aid not in area_ids:
            diffs.append(f"[③] bulletin_detail_areas.area_id={aid!r} → areas에 없음")


def compare_seed_tables(
    repo: AbstractRepository,
    defs: dict,
    ref_date: date | None = None,
) -> list[str]:
    """시드 대조 — 빈 목록이면 일치, 비면 seed-check 종료 1."""
    if ref_date is None:
        from common.clock import kst_today
        ref_date = kst_today()

    diffs: list[str] = []
    _check_areas(repo, diffs)
    _check_area_aliases(repo, diffs)
    _check_axis_coverage(repo, diffs)
    _check_referential_integrity(repo, diffs)
    _check_bulletin_area_ids(repo, defs, diffs, ref_date)
    return diffs

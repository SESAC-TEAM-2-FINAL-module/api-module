#!/usr/bin/env python3
"""
ci/scan_keys.py — 픽스처 원문에 인증키가 노출됐는지 검사 (계획서 A.7·12.1절)
결과는 일치 건수만 출력. 키 값 자체는 출력하지 않는다.
exit 0: 0건 / exit 1: 1건 이상 또는 키 로드 실패
"""
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).parent.parent

KEY_VARS = [
    "DTRECENT_KEY",
    "NIFS_KEY_BULLETIN",
    "NIFS_KEY_LINE",
    "NIFS_KEY_FISHERY_SEA",
]


def _load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env


def _key_values(env: dict[str, str]) -> list[str]:
    values: list[str] = []
    for var in KEY_VARS:
        v = env.get(var, "").strip()
        if len(v) < 8:
            continue
        values.append(v)
        decoded = unquote(v)
        if decoded != v:
            values.append(decoded)
    return values


def _scan(scan_dir: Path, key_values: list[str]) -> list[Path]:
    hits: list[Path] = []
    for fpath in scan_dir.rglob("*"):
        if not fpath.is_file():
            continue
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if any(kv in text for kv in key_values):
            hits.append(fpath)
    return hits


def main() -> int:
    env = _load_env(ROOT / ".env")
    key_values = _key_values(env)

    if not key_values:
        print("scan_keys: .env에서 검사할 키를 찾지 못했습니다.")
        return 1

    scan_dir = ROOT / "fixtures"
    if not scan_dir.exists():
        print("scan_keys: fixtures/ 없음 — 0건")
        return 0

    hits = _scan(scan_dir, key_values)
    print(f"scan_keys: {len(hits)}건")
    for p in hits:
        print(f"  {p.relative_to(ROOT)}")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())

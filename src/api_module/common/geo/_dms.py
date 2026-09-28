"""
이식: $SRC_API/verify_nifs_api.py — DMS_RE, dms_to_decimal()
도분초(°´˝) → 십진도 변환
구분자: °(U+00B0) ´(U+00B4) ˝(U+02DD)
"""
from __future__ import annotations
import re

DMS_RE = re.compile(r"(\d+)\s*[°]\s*(\d+)\s*[´'′]\s*([\d.]+)\s*[˝\"″]?")


def dms_to_decimal(s) -> float | None:
    if not s:
        return None
    s = str(s).strip()
    m = DMS_RE.search(s)
    if m:
        d, mi, sec = float(m.group(1)), float(m.group(2)), float(m.group(3))
        return round(d + mi / 60 + sec / 3600, 6)
    try:
        v = float(s)
        return v if 30 < abs(v) < 140 else None
    except ValueError:
        return None

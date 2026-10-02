"""
날짜 기준 (계획서 3.3절, 개정 17) — 수집 창의 "오늘"은 KST다.
컨테이너 현지 시각(date.today())에 기대지 않는다
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


def kst_today(now_utc: datetime | None = None) -> date:
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(KST).date()


_KST_NAIVE_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M")


def kst_naive_to_utc_iso(value: str | None) -> str | None:
    """원천의 KST naive 시각 문자열 → UTC ISO(초 단위). 알려진 형식이 아니면 None — KST 문자열을 그대로 넘기지 않는다 (5.2절)"""
    s = str(value or "").strip().replace("T", " ")
    for fmt in _KST_NAIVE_FORMATS:
        try:
            kst = datetime.strptime(s, fmt)
        except ValueError:
            continue
        return (kst - timedelta(hours=9)).strftime("%Y-%m-%dT%H:%M:%S")
    return None


def same_day_last_year(d: date) -> date:
    """작년 같은 날 — 그 날이 없으면(2월 29일) 2월 28일 (정선 1년 창의 시작, 3.3절)"""
    try:
        return d.replace(year=d.year - 1)
    except ValueError:
        return date(d.year - 1, 2, 28)


def split_by_month(start: date, end: date) -> list[tuple[date, date]]:
    """[start, end]를 달 경계로 자른다 — 빈틈·겹침 없이 덮는다"""
    out: list[tuple[date, date]] = []
    cur = start
    while cur <= end:
        nxt = date(cur.year + (cur.month == 12), cur.month % 12 + 1, 1)
        seg_end = min(nxt - timedelta(days=1), end)
        out.append((cur, seg_end))
        cur = seg_end + timedelta(days=1)
    return out

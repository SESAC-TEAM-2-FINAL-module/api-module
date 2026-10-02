"""
수집 창 날짜 기준 (계획서 3.3절, 개정 17) — KST, 작년 같은 날, 실행 키
"""
from datetime import date, datetime, timezone

from common.clock import kst_today, same_day_last_year, split_by_month


def test_kst_today_crosses_utc_midnight():
    """UTC 15:00 = KST 다음 날 00:00"""
    assert kst_today(datetime(2026, 9, 30, 14, 59, tzinfo=timezone.utc)) == date(2026, 9, 30)
    assert kst_today(datetime(2026, 9, 30, 15, 0, tzinfo=timezone.utc)) == date(2026, 10, 1)


def test_same_day_last_year_and_leap_day():
    assert same_day_last_year(date(2026, 9, 23)) == date(2025, 9, 23)     # IDW 기준 창의 시작
    assert same_day_last_year(date(2028, 2, 29)) == date(2027, 2, 28)     # 없는 날 → 2월 28일
    assert same_day_last_year(date(2029, 3, 1)) == date(2028, 3, 1)


def test_line_year_window_matches_baseline():
    """정선 1년 창 = 작년 같은 날 ~ 끝, 양끝 포함 — 기준 데이터 20250923~20260923"""
    from collector.adapters.line._adapter import year_window
    s, e = year_window(date(2026, 9, 23))
    assert (s, e) == (date(2025, 9, 23), date(2026, 9, 23))
    assert (e - s).days + 1 == 366


def test_completeness_run_end_is_kst_yesterday():
    from collector._completeness import CompletenessRun
    run = CompletenessRun.start(datetime(2026, 10, 1, 16, 0, tzinfo=timezone.utc))   # KST 10/2 01:00
    assert run.end == date(2026, 10, 1)
    assert run.run_key == "20261001T160000"


def test_fishery_window_on_january_first_is_last_year():
    """1월 1일 실행 → 어제가 속한 해(작년) 1월 1일 ~ 12월 31일 — 창이 비지 않는다"""
    from collector._completeness import CompletenessRun
    run = CompletenessRun.start(datetime(2026, 12, 31, 16, 0, tzinfo=timezone.utc))   # KST 2027-01-01
    assert run.end == date(2026, 12, 31)
    assert date(run.end.year, 1, 1) == date(2026, 1, 1)
    assert len(split_by_month(date(run.end.year, 1, 1), run.end)) == 12


def test_split_by_month_covers_without_gap():
    parts = split_by_month(date(2025, 11, 30), date(2026, 11, 30))
    assert parts[0] == (date(2025, 11, 30), date(2025, 11, 30))
    assert parts[-1][1] == date(2026, 11, 30)
    for (_, e0), (s1, _) in zip(parts, parts[1:]):
        assert (s1 - e0).days == 1

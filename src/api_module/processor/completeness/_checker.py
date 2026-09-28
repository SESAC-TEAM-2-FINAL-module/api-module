"""
완전성 검사 (3.3절)
참고: $SRC_IDW/stage2_collect.py _fetch_all_pages() 건수 대조부
     $SRC_API/verify_nifs_api.py F2 분할 합산 (범위 불일치 결함 수정 — 범위부터 맞춘다)
"""
from __future__ import annotations
from dataclasses import dataclass

from common.classifier import ParsedResponse


@dataclass
class CompletenessResult:
    status: str  # OK | INCOMPLETE | FILTER_IGNORED | COMPARISON_RANGE_MISMATCH
    expected: int | None
    actual: int
    message: str = ""


def check_completeness(
    pr: ParsedResponse,
    rows: list[dict],
    api: str,
    request_window: tuple[str, str] | None = None,
) -> CompletenessResult:
    """
    totalCount 있는 API (dtRecent): 수령 건수 = totalCount
    totalCount 없는 API (NIFS): 분할 합산은 collector-completeness 별도 수행
    필터 파라미터가 있는 API: 반환 행이 요청 창 안인지 확인
    """
    actual = len(rows)

    if pr.total_count is not None:
        if actual != pr.total_count:
            return CompletenessResult(
                status="INCOMPLETE",
                expected=pr.total_count,
                actual=actual,
                message=f"totalCount={pr.total_count} 수령={actual}",
            )
        return CompletenessResult(status="OK", expected=pr.total_count, actual=actual)

    if request_window is not None:
        start, end = request_window
        out_of_window = [
            r for r in rows
            if r.get("date") and not (start <= str(r["date"]) <= end)
        ]
        if out_of_window:
            return CompletenessResult(
                status="FILTER_IGNORED",
                expected=None,
                actual=actual,
                message=f"창 밖 행 {len(out_of_window)}건 (공단 서비스 필터 무시 사례)",
            )

    return CompletenessResult(status="OK", expected=None, actual=actual)


def check_split_completeness(
    single_window: tuple[str, str, int],
    split_windows: list[tuple[str, str, int]],
) -> CompletenessResult:
    """
    분할 합산 비교.
    반드시 비교 범위를 먼저 맞춘다 — 범위 불일치 시 COMPARISON_RANGE_MISMATCH (절단·INCOMPLETE 금지).
    범위 일치 후 분할 합 < 단일 창이면 INCOMPLETE.
    """
    single_start, single_end, single_count = single_window
    if not split_windows:
        return CompletenessResult(status="OK", expected=None, actual=single_count)

    split_start = min(w[0] for w in split_windows)
    split_end = max(w[1] for w in split_windows)

    if split_start != single_start or split_end != single_end:
        return CompletenessResult(
            status="COMPARISON_RANGE_MISMATCH",
            expected=None,
            actual=single_count,
            message=(
                f"단일창={single_start}~{single_end} 분할={split_start}~{split_end} — "
                "범위 불일치, 절단·INCOMPLETE로 판정하지 않는다"
            ),
        )

    split_total = sum(w[2] for w in split_windows)
    if split_total < single_count:
        return CompletenessResult(
            status="INCOMPLETE",
            expected=single_count,
            actual=split_total,
            message=f"분할합={split_total} < 단일창={single_count}",
        )
    return CompletenessResult(status="OK", expected=single_count, actual=split_total)

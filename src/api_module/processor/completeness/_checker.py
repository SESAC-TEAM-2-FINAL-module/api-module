"""
완전성 검사 (3.3절)
참고: $SRC_IDW/stage2_collect.py _fetch_all_pages() 건수 대조부
     $SRC_API/verify_nifs_api.py F2 분할 합산 (범위 불일치 결함 수정 — 범위부터 맞춘다)
"""
from __future__ import annotations
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from common.classifier import ParsedResponse


def item_date(api: str, item: dict) -> str | None:
    """요청 창 밖 행 검사용 원문 항목 날짜(KST, YYYYMMDD) — 적조 day_report, 정선 obs_dtm, 어장환경 DATE_Y/M/D.
    못 읽으면 None — 판정에 쓰지 않는다. api 접미(`-watch` 등)는 떼고 본다"""
    base = api.split("-", 1)[0]
    try:
        if base == "redtideList":
            return str(item.get("day_report") or "")[:8] or None
        if base == "sooList":
            return str(item.get("obs_dtm") or "")[:10].replace("-", "") or None
        if base == "femoSeaList":
            return f"{int(item['DATE_Y']):04d}{int(item['DATE_M']):02d}{int(item['DATE_D']):02d}"
    except (KeyError, TypeError, ValueError):
        return None
    return None


def requested_window(meta: dict) -> tuple[str | None, str | None]:
    """원문 메타의 요청 변수 sdate·edate (params, 없으면 url 쿼리)"""
    params = (meta or {}).get("params") or {}
    if "sdate" not in params and (meta or {}).get("url"):
        q = parse_qs(urlsplit(meta["url"]).query)
        params = {k: v[0] for k, v in q.items()}
    return params.get("sdate"), params.get("edate")


@dataclass
class CompletenessResult:
    status: str  # OK | INCOMPLETE | FILTER_IGNORED | COMPARISON_RANGE_MISMATCH
    expected: int | None
    actual: int
    message: str = ""
    truncated_side: str | None = None  # 분할 합산 INCOMPLETE — SINGLE / SPLIT (개정 17)


def check_completeness(
    pr: ParsedResponse,
    rows: list[dict],
    api: str,
    request_window: tuple[str, str] | None = None,
    actual_items: int | None = None,
) -> CompletenessResult:
    """
    totalCount 있는 API (dtRecent): 수령 건수 = totalCount
      - actual_items: rows가 metric 분해 등으로 items × N이 되는 어댑터는 pr.items 수를 전달한다
    totalCount 없는 API (NIFS): 분할 합산은 collector-completeness 별도 수행
    필터 파라미터가 있는 API: 원문 항목(pr.items)의 날짜가 요청 창(sdate~edate, 양끝 포함) 안인지 확인
    """
    # totalCount 비교 기준: 호출자가 actual_items를 주면 그것(items 단위), 없으면 rows 수
    actual = actual_items if actual_items is not None else len(rows)

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
            it for it in pr.items
            if (d := item_date(api, it)) is not None and not (start <= d <= end)
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
    분할 합산 비교 (3.3절, 개정 17). 날짜는 YYYYMMDD 문자열.
    1) 범위 — 월 분할 창들이 단일 창을 **빈틈·겹침 없이** 덮지 않으면 COMPARISON_RANGE_MISMATCH
       (절단·INCOMPLETE로 판정하지 않는다, N12)
    2) 건수 — 같으면 OK. 다르면 INCOMPLETE이고 작은 쪽을 truncated_side로:
       분할 합 > 단일 창 → SINGLE(단일 창 쪽 절단 의심 — 정기 수집 경로), 분할 합 < 단일 창 → SPLIT (N13)
    """
    single_start, single_end, single_count = single_window
    parts = sorted(split_windows, key=lambda w: w[0])
    if not parts:
        return CompletenessResult(status="COMPARISON_RANGE_MISMATCH", expected=single_count, actual=0,
                                  message="월 분할 없음 — 비교 범위를 맞출 수 없다")

    gap = _range_gap(single_start, single_end, [(w[0], w[1]) for w in parts])
    if gap:
        return CompletenessResult(
            status="COMPARISON_RANGE_MISMATCH", expected=None, actual=single_count,
            message=f"단일창={single_start}~{single_end} 분할={parts[0][0]}~{parts[-1][1]} — {gap}. "
                    "범위 불일치, 절단·INCOMPLETE로 판정하지 않는다",
        )

    split_total = sum(w[2] for w in parts)
    if split_total == single_count:
        return CompletenessResult(status="OK", expected=single_count, actual=split_total)
    side = "SINGLE" if split_total > single_count else "SPLIT"
    return CompletenessResult(
        status="INCOMPLETE", expected=single_count, actual=split_total, truncated_side=side,
        message=f"분할합={split_total} 단일창={single_count} — {'단일 창' if side == 'SINGLE' else '분할'} 쪽 절단 의심",
    )


def _range_gap(start: str, end: str, windows: list[tuple[str, str]]) -> str:
    """windows가 [start, end]를 빈틈·겹침 없이 덮으면 빈 문자열, 아니면 사유"""
    from datetime import date, timedelta

    def d(x: str) -> date:
        return date(int(x[:4]), int(x[4:6]), int(x[6:8]))

    if windows[0][0] != start:
        return f"시작이 다름({windows[0][0]})"
    if windows[-1][1] != end:
        return f"끝이 다름({windows[-1][1]})"
    for (s0, e0), (s1, _e1) in zip(windows, windows[1:]):
        if d(s1) > d(e0) + timedelta(days=1):
            return f"빈틈 {e0}~{s1}"
        if d(s1) <= d(e0):
            return f"겹침 {s1}~{e0}"
    for s0, e0 in windows:
        if d(e0) < d(s0):
            return f"거꾸로 된 창 {s0}~{e0}"
    return ""

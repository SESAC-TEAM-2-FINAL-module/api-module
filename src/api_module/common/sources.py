"""
수집 원천 ↔ api_id 대응표 — 한 곳 (계획서 2.2·4.9·5.3절, 결정 D2)

- api_id   : collector·raw_index.api·obs.loaded.api가 쓰는 이름 (`dtRecent` …). 변형은 접미로 붙는다
             (`femoSeaList-watch`·`femoSeaList-backfill`·`*-completeness`)
- 수집 원천 : obs.loaded.source·adapter_health.adapter·stations.source_api가 쓰는 이름 (`tide` …)
단계 전용 코드끼리 가져다 쓰지 않으므로 대응표는 common/에 둔다 (12절)
"""
from __future__ import annotations

API_SOURCE: dict[str, str] = {
    "dtRecent": "tide",
    "redtideList": "bulletin",
    "sooList": "line",
    "femoSeaList": "fishery",
}

SOURCES: tuple[str, ...] = tuple(API_SOURCE.values())


def base_api(api_id: str) -> str:
    """변형 접미를 뗀 api_id — `femoSeaList-watch` → `femoSeaList`"""
    return api_id.split("-", 1)[0]


def source_of(api_id: str) -> str | None:
    """api_id → 수집 원천. 모르는 api_id면 None"""
    return API_SOURCE.get(base_api(api_id))


def base_api_of(source: str) -> str | None:
    """수집 원천 → 기본 api_id. 모르는 원천이면 None"""
    for api, src in API_SOURCE.items():
        if src == source:
            return api
    return None


# 정기 경로의 api_id 변형 — 분할 합산(`-completeness`)은 축 상태·산출 지연 기준에서 뺀다 (3.3·4.9절, 개정 17)
_REGULAR_SUFFIXES = ("", "-watch", "-backfill")


def regular_api_ids(source: str | None = None) -> list[str]:
    """정기 경로 api_id 목록(명시 목록 — 문자열 패턴으로 조회하지 않는다). source를 주면 그 원천만"""
    bases = [base_api_of(source)] if source else list(API_SOURCE)
    return [b + suf for b in bases if b for suf in _REGULAR_SUFFIXES]


def is_completeness(api_id: str) -> bool:
    return api_id.endswith("-completeness")

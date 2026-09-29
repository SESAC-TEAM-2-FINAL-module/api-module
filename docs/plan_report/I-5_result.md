# I-5 결과 보고서 — 어장환경 해수면 (`femoSeaList`)

작성일: 2026-09-29

---

## 1. 완료 항목

| 항목 | 파일 | 비고 |
|---|---|---|
| 수집 어댑터 | `collector/adapters/fishery/_adapter.py` | `FisheryBackfillAdapter`, `FisheryCompletenessAdapter` |
| 게시 감시 | `collector/fishery_watch.py` | `FisheryWatchAdapter` — 주 1회 사전 읽기, 건수 변화 시 전량 수집 |
| 가공 어댑터 | `processor/adapters/fishery/_adapter.py` | `FisheryProcessorAdapter`, `FisheryWatchProcessorAdapter` |
| 등록 | `collector/adapters/fishery/__init__.py`, `processor/adapters/fishery/__init__.py` | 두 워크로드 등록 |
| 테스트 | `tests/unit/test_fishery_processor.py` | 47 tests passed |
| 원천 기록 | `docs/SOURCES.md` | 원문 필드명 확인 테이블 추가 |

---

## 2. 검사 결과

| # | 입력 | 통과 기준 | 결과 |
|---|---|---|---|
| F1 (2023) | `femoSeaList_f3_2023_*.json` | items=1008, rows=6048 (×6) | ✓ |
| F1 (2024) | `femoSeaList_f3_2024_*.json` | items=1020, rows=6120 (×6) | ✓ |
| F1 (2025) | `femoSeaList_f3_2025_*.json` | items=1022, rows=6132 (×6) | ✓ |
| F2 | `femoSeaList_f1_*.json` (2026 빈) | parse_status=OK, total_count=0, 1행 publication_check | ✓ |
| F3 전체 | `femoSeaList_f2_single_*.json` | items=255, rows=1530 (×6) | ✓ |
| F3 날짜 필터 | 동일 | surveyed_on ≥ 2025-10-01 → 212×6=1272행 | ✓ |
| N8 | NET_ERROR ParsedResponse | total_count=None (게시 대기 금지) | ✓ |
| 단위: _assemble_date | 정상·한 자리·누락 | 형식 / ValueError | ✓ |
| 단위: _parse_value | 정상·ZERO_SENTINEL·클로로필 0 | 값 / 결측 이유 | ✓ |
| 단위: 좌표 | DMS 폐구간 | lat=33.0 포함, 범위 밖 제외 | ✓ |

전체 단위 테스트: **224 passed, 2 skipped** (기존 SKIP 유지)

---

## 3. 설계 결정

### 3-1. metric × layer 6행/레코드

SKILL.md(fishery)에서 metric 3종(`water_temp`·`salinity`·`chlorophyll`) × layer 2종(`S`표층/`B`저층) = 6행. 좌표 검증 통과 후 항상 6행 생성. 좌표 실패 레코드는 전 6행 제외(결측이 아니라 처음부터 생성하지 않음).

### 3-2. R0 ZERO_SENTINEL 범위

`water_temp`·`salinity`의 `0.000` → `ZERO_SENTINEL`. **`chlorophyll`는 제외** — 클로로필 0.0은 유효값.

### 3-3. 게시 감시 실패 처리

호출 실패(`error` 있음) → `total_count=None`, `delta=None`. `OK`·`OK_EMPTY` 외 parse_status → 동일. 0건(게시 대기)으로 삼키지 않는다(N8 통과).

### 3-4. `_load_prev_count()` 스텁

I-6(repository 구현) 전까지 `None` 반환. `prev_count is None` → `changed=True` → 매 실행 전량 수집. DB 연동 후 I-6에서 교체.

### 3-5. DATE_Y/M/D 조립

`$SRC_API/verify_nifs_api.py::extract_dates()`의 결함(한 자리 값 "5" 조용히 넘김) 수정:
- `int(y)`, `int(m)`, `int(d)` 후 `f"{int(y):04d}-{int(m):02d}-{int(d):02d}"` 형식
- `None` 누락 · `int()` 실패 → `ValueError` — 해당 레코드 skip + stderr 출력

---

## 4. 이식 출처 (docs/SOURCES.md 참조)

| 참조 위치 | 출처 | 처리 |
|---|---|---|
| `$SRC_API/verify_nifs_api.py::extract_dates()` | DATE_Y/M/D 조립 결함 | 수정하여 적용 |
| `$SRC_IDW/src/collector.py::collect_fishery_sea()` | 달력 연도 단위 호출 구조 | REFERENCE |
| `common/geo/_dms.py::dms_to_decimal()` | 이미 I-1에서 이식됨 | 재사용 |
| `common/geo/_coords.py::validate_coords_closed()` | 이미 I-1에서 이식됨 | 재사용 |

---

## 5. 원천 필드 확인

픽스처 직접 검사 (`femoSeaList_f3_2023_*.json`):

| metric | layer | 원문 필드 |
|---|---|---|
| water_temp | S | `TEMP_S` |
| water_temp | B | `TEMP_B` |
| salinity | S | `SAL_S` |
| salinity | B | `SAL_B` |
| chlorophyll | S | `CHL_S` |
| chlorophyll | B | `CHL_B` |

`DATE_Y`·`DATE_M`·`DATE_D` — 한 자리 정수값("5") 가능 확인. `LATITUDE`·`LONGITUDE` — DMS 형식 `34°47′19″` 확인.

---

## 6. 계획서 반영 후보

| 항목 | 내용 | 상태 |
|---|---|---|
| 게시 감시 `prev_count=None` 시 동작 | I-5에서 매 실행 전량 수집(스텁). I-6 DB 연동 후 delta 비교로 전환. 계획서에 명시 없음 | 대기 |
| chlorophyll R0 제외 근거 | SKILL.md fishery에 R0 적용 대상 `water_temp`·`salinity`만 명시됨. 클로로필 0.0이 유효값인지 계획서 4.6절에 명시 없음 | 대기 |

---

## 7. 미결 (`<미결>`)

해당 없음 — 이번 지시서 범위에서 미결 설정 키 없음.

---

## 8. 다음 지시서

**I-6** — `repository` skill, DB 접근 계층 구현. `_load_prev_count()` 스텁 교체 포함.

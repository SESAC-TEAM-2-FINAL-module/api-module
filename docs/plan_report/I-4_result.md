# I-4 결과

지시서: line 어댑터 구현 (정선해양관측 sooList)
실행일: 2026-09-29
참조 skill: `line` (`.claude/skills/line/SKILL.md`)

---

## 0. 실행 환경

| 항목 | 값 |
|---|---|
| Python | 3.13.9 |
| pytest | 8.3.3 |
| 수정사항 | 없음 |
| 커밋 해시 | 미커밋 (사용자 대기 중) |

이식 출처 확인:
- `$SRC_IDW/src/normalizer.py` — B v2 수정본 확인 (`normalize_line_with_depth()`, `group_type` 원문 레코드 단위 계산 포함)
- `$SRC_IDW/line_depth_collect_v2.py` — `_assign_casts()` 및 `cast_id_x60_map` 캐스트 로직 확인
- `$SRC_IDW/src/collector.py` — `collect_line_survey()` 1년 창 1회 호출 구조 참고
- 픽스처 원문 필드명 확인: `wtr_tmp`(water_temp) · `sal`(salinity) · `dox`(dissolved_oxygen) — SKILL.md ③-3과 일치

---

## 1. 판정표

| # | 검사 | 결과 |
|---|---|---|
| F4 | B v2 픽스처 총 10,445건, 남해 2,584건, lat=33.0(float '33') 523건 포함 | **통과** |
| F5 | 남해 캐스트 324, 0m 정확히 1개 obs인 캐스트 324, 빈 값 레코드 739 MISSING 저장 | **통과** |
| F6 | 연속 간격 10~720분 0건 → CAST_RULE_ASSUMPTION_BROKEN 0건 | **통과** |
| N9 | 같은 정점 90분 간격 삽입 → CAST_RULE_ASSUMPTION_BROKEN 1건 | **통과** |

**단위 테스트: 31/31 통과 (전체 177/177 통과, 2 skip F11)**

---

## 2. S5 통과 조건: 남해 0m DO 날짜별 집계

픽스처 `sooList_depth_20260923_*.json` (B v2, 수집 창 2025-09-23 ~ 2026-09-23) 기준.

| 항차 날짜 | DO 유효 | DO 빈값 | 비고 |
|---|---|---|---|
| 2025-10-30 | 5 | 0 | ALL_VALID |
| 2025-10-31 | 9 | 0 | ALL_VALID |
| 2025-11-03 | 4 | 0 | ALL_VALID |
| 2025-11-04 | 10 | 0 | ALL_VALID |
| 2025-11-05 | 10 | 0 | ALL_VALID |
| 2025-11-06 | 5 | 0 | ALL_VALID |
| **2025-11-07** | **11** | **0** | **ALL_VALID ← 마지막 유효 날짜** |
| 2025-12-17 ~ 2026-08-31 | 0 | 270 | ALL_BLANK |

- **총 남해 0m 레코드**: 324건
- **DO 유효**: 54건 (7개 항차 날짜, 2025-10-30 ~ 2025-11-07)
- **DO 빈값**: 270건 (36개 항차 날짜, 2025-12-17 이후 전부 빈값)
- **마지막 유효 관측**: **2025-11-07** — v1.5 4.7절 "2025-11 이후 DO 비어 있다" 확인

**DO 신선도 임계 판단 근거**:
- v1.5 권장값 2160h(90일)를 적용하면: 2025-11-07 + 90일 = 2026-02-05 이후 STALE
- 2026-09-29 현재 약 326일 경과 → 데모 전체 기간 STALE
- 관련 미결: `stale_threshold_hours.dissolved_oxygen` — `evaluation` skill이 결정

**거리 집계**: 합성 양식장(`fixtures/synthetic/farms.csv`) 미생성으로 거리 계산 보류. I-grading에서 `grading.line_max_distance_km`와 함께 결정 예정.

---

## 3. 예상과 달랐던 결과

### API 특성

| 항목 | 내용 |
|---|---|
| `obs_dtm` 시간대 | KST naive (간접 증거 3종). 직접 API 문서 확인 불가 — SOURCES.md에 기록, 계획서 반영 후보 등록 |
| `lat` 값 형식 | '33.0' 아닌 '33' (정수 문자열). `float(r.get('lat'))` 비교 필요. 픽스처 F4 테스트에 반영 |
| 이식 출처 파일명 | SKILL.md ④는 `$SRC_IDW/line_depth_collect.py`를 명시하나, 실제 캐스트 로직은 `line_depth_collect_v2.py`에 있음 — **해결됨 (2026-09-29): SKILL.md ④ 수정** |

### 우리 코드·명세 결함

없음.

---

## 4. 새로 발견한 함정

1. **`lat` 필드가 정수 문자열('33')로 저장됨**: 픽스처 남해 lat=33.0 레코드는 `r['lat'] == '33'`이다. `str(r.get('lat')) == '33.0'` 비교는 실패 — `float()` 변환 후 비교해야 한다. `validate_coords_closed`는 `float(r.get('lat'))` 변환 후 호출하므로 어댑터 코드는 정상 동작한다.

2. **0m DO 빈값 실태**: 집계 결과, 2025-11-07 이후 남해 0m DO는 전량 빈값이다. `grading` 단계에서 `line.surface_rule` 결정 전까지 DO = NONE(`SURFACE_RULE_UNDECIDED`)이므로 현재 영향 없으나, 규칙 결정 시 DO 신선도 임계도 함께 정해야 한다.

3. **`cast_rule_version` 형식 정의**: SKILL.md에 형식 미명시 → `f"x{cast_gap_minutes}"` 형식 채택(`x60`). 계획서 반영 후보 등록.

---

## 5. 계획서 반영 후보

### 구현한 *(제안)* 항목

없음.

### 만난 `<미결>` 항목

| 항목 | 절 | 현재 처리 |
|---|---|---|
| `line.surface_rule` | 4.4절, 11절 | `<미결>` 유지. 어댑터에서 읽지 않음 — 저장 시 표층 표시 없음, `depth_m` 보존 |
| `line.cast_gap_minutes` | 4.4절, 11절 | 현재 60 — 결정 대기. `cast_rule_version="x60"`으로 기록 |
| `stale_threshold_hours.dissolved_oxygen` | 4.9절 | DO 마지막 유효 2025-11-07 — 2160h(90일) 적용 시 2026-02-05 이후 STALE. evaluation skill 소유 |

### 새 계획서 반영 후보

| 항목 | 내용 |
|---|---|
| `obs_dtm` 시간대 직접 확인 경로 | IDW 코드 KST 취급하나 API 공식 문서 미확인. 직접 확인 방법 또는 공식 명시 필요 |
| `cast_rule_version` 형식 명시 | `f"x{cast_gap_minutes}"` 형식 채택. 계획서 11절에 정의 요청 |
| SKILL.md ④ 파일명 오기 | `line_depth_collect.py` → 실제는 `line_depth_collect_v2.py`. **해결됨 (2026-09-29)** |

### 참조한 skill 및 커밋

- `.claude/skills/line/SKILL.md` (커밋 해시: 미커밋)

---

*이식 기록 전체: `docs/SOURCES.md`*

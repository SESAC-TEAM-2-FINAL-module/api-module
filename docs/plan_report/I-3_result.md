# I-3 결과

지시서: bulletin (적조정보) adapter 구현  
실행일: 2026-09-28  
참조 skill: `bulletin` (`.claude/skills/bulletin/SKILL.md`)

---

## 0. 실행 환경

| 항목 | 값 |
|---|---|
| Python | 3.13.9 |
| PyYAML | 6.0.3 |
| pytest | 8.3.3 |
| 커밋 해시 | 미커밋 (사용자 대기 중) |

이식 출처 확인:
- `$SRC_API/verify_nifs_api.py` — NIFS 호출 구조 참고, `nested_items` 중첩 처리 참고
- `$SRC_API/probe_followup.py` :: `probe_redtide()` — **사용 금지** (item2 없는 속보 버리는 결함)
- `$SRC_API/output/raw/redtideList_r1_*·r3_*` — 픽스처로 사용 (F7~F10)

---

## 1. 판정표

### 검사 항목

| # | 규칙 (절) | 입력 | 통과 기준 | 결과 |
|---|---|---|---|---|
| F7 (outer) | bulletins 1행 | R1 51건 | bulletins 51행 | **통과** |
| F7 (item2) | bulletin_details | R1 50건 item2 | bulletin_details 50행 | **통과** |
| F7 (missing) | item2 없는 속보 보관 | 20250924-001 | bulletins 1행, grade=UNKNOWN | **통과** |
| F8 (TARGET) | species_class | R1 45건 코클로디니움 | TARGET 45건 | **통과** |
| F8 (grade 10~99) | PRE_ADVISORY | 코클로디니움 10건 | PRE_ADVISORY 10건 | **통과** |
| F8 (grade 100~999) | ADVISORY | 코클로디니움 2건 | ADVISORY 2건 | **통과** |
| F8 (grade 1000+) | WARNING | 코클로디니움 1건 | WARNING 1건 | **통과** |
| F9 (outer) | bulletins | R3 15건 | bulletins 15행 | **통과** |
| F9 (NOT_GRADED) | Chattonella | R3 10건 | NOT_GRADED 10건 | **통과** |
| F9 (areas 합계) | bulletin_detail_areas | R3 | 20행 | **통과** |
| F9 (분리) | "및"·"~" 분리 | 5건 | 각 2행, 나머지 10건 각 1행 | **통과** |
| F10 (day_report) | 고유 day_report | R1+R3 | 66건 | **통과** |
| F10 (여수) | txt_seas 정규화 | "전남 여수 " | "전남 여수" 1종 | **통과** |
| N10 | Margalefidinium 150 | 밀도 150 | ADVISORY | **통과** |

**단위 테스트: 47/47 통과 / 전체 누적: 146/146 통과, 2 skip (F11 — I-2 로컬 수동 전용)**

---

## 2. 예상과 달랐던 결과

### API 특성

| 항목 | 내용 |
|---|---|
| `item2` 없는 속보 | 20250924-001 — 예상대로 1건 존재. outer 기준 bulletins 1행 보관 확인. |
| `day_report` vs `cod_news` 앞 8자리 불일치 | R1+R3에서 5건, 최대 14일 차이(20260526-001: day_report=20260514). 둘 다 저장하는 설계 확인. |
| `txt_seas` CR·LF | 20240808 "경남 남해군 미조~상주면\r\n" — 1단계 strip에서 처리. |
| NIFS classifier | parse() 결과 total_count=None (페이징 없음), items=51. NIFS 계열 분기(최상위 header+body) 정상 동작. |

### 우리 코드·명세 결함

| 항목 | 코드 상태 | 내용 |
|---|---|---|
| `probe_followup.py` 사용 금지 | **코드에 반영 완료** | `probe_redtide()` line 176 `item2 or []`가 item2 없는 속보를 버리는 결함. processor에서 직접 `outer.get("item2") or []` 사용하고 item2 없어도 bulletins 1행 생성. |
| unmapped_locations DB 저장 | **미구현 — I-6 이후 보완 예정** | 미매핑 지점(area_id=None)을 현재는 stderr 로그만. DB 접근 계층(I-6)이 구현된 후 unmapped_locations 테이블 적재. |

---

## 3. 새로 발견한 함정

1. **`txt_seas`의 "해역" 접미 위치** (**코드에 반영 완료**): "충남 서산 창리 해역(내측)" 같이 "해역" 뒤에 괄호 부가 설명이 따라오는 경우가 있다. regex `\s*해역(\([^)]*\))?$`로 처리.

2. **오타 "충천남도"는 시도 약칭 미적용** (**알려진 한계 — 시드 내용 미결**): 3단계 시도 약칭에서 "충천남도"(오타)는 딕셔너리에 없어 변환 안 됨. 정규화 후 "충천남도 천수만"으로 남아 "충남 천수만"과 다른 key가 됨. area_aliases.yaml에 별칭 등록으로 해소 가능하나 시드 내용이 미결.

3. **`_SEEDS_DIR` 경로 깊이** (**코드에 반영 완료**): processor 어댑터(`parents[5]`)에서 저장소 루트의 `seeds/` 디렉토리를 참조. 경로 계층이 변경되면 조정 필요.

4. **bulletin_detail_areas가 normalize()에서 생성** (**설계 선택**): interpret()는 bulletin/bulletin_detail만 반환하고, normalize()에서 txt_seas 정규화 후 bulletin_detail_area 행을 추가한다. rows 내 `_type` 필드로 테이블 구분. processor/main.py 흐름(obs.loaded payload)에는 `station_id`/`observed_at_utc` 없이도 동작.

---

## 4. 계획서 반영 후보

### 구현한 *(제안)* 항목

없음.

### 만난 `<미결>` 항목

| 항목 | 절 | 현재 처리 |
|---|---|---|
| 시드 내용 (`areas`·`area_aliases`·`axis_coverage`) | 5.3절, 11절 | 형식과 로딩 코드만. 내용 비움. |
| `bulletin.current_window_days` | 4.8절 | 이 어댑터 범위 밖 (`grading` 담당). 미처리. |

### 새 *(제안)* 등록 요청

| 항목 | 내용 |
|---|---|
| `unmapped_locations` 적재 시점 | 현재 normalize() 중 미매핑 지점을 stderr로만 로그. I-6 이후 DB 접재로 전환 시 normalize() 인터페이스(return type 또는 side-effect)에 대한 정책 명시 필요. |

### 참조한 skill 및 커밋

- `.claude/skills/bulletin/SKILL.md` (커밋 해시: 미커밋)

---

*이식 기록 전체: `docs/SOURCES.md`*

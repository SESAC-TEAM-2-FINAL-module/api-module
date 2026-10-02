# I-16 결과 보고서 — 적조 위험도 지수 (개정 20)

작성 2026-10-02 · 실행 기준 세션: `aquasentinal-api-module` (컨텍스트 요약 후 재진입)  
참조 skill: 없음 (I-16은 skill 없이 지시서 본문만)  
참조 계획서: `docs/plan/API모듈_제작계획서_20260927.md` 4.10절, 5.5절, 7.9절, 12절

---

## 산출물 목록

| 파일 | 변경 종류 | 내용 |
|---|---|---|
| `src/api_module/common/repository/tables.py` | 수정 | `AXIS_VALS`에 `red_tide_risk` 추가 · `FACTOR_VALS` · `EXCLUDED_REASON_VALS` 추가 · `risk_index_factors` 표 · `risk_index_levels` 표 추가 |
| `src/api_module/common/repository/base.py` | 수정 | 7개 추상 메서드 추가 (upsert/delete risk 표, get_farm_readings_for_risk_index, get_obs_flags, get_survey_obs_flags) |
| `src/api_module/common/repository/sql.py` | 수정 | 7개 메서드 구현 |
| `contracts/tables/schema_pg.sql` | 재생성 | tables-v3 DDL (risk 표 포함) |
| `contracts/tables/schema_my.sql` | 재생성 | tables-v3 DDL (MySQL) |
| `config/definitions.yaml` | 수정 | `risk_index.*` 10개 키 `<미결>` 추가 · `contracts.tables: tables-v3` |
| `ci/gate/expected.yaml` | 수정 | `risk_index.*` 10개 키 `<미결>` · `tables: tables-v3` |
| `contracts/release/image_notice.json` | 수정 | `contracts_version: tables-v3 / queue-v1 / operational-v1` |
| `src/api_module/grading/_risk_index.py` | 신규 | 순수 함수 계산 모듈 — `compute_risk_index` · `check_risk_index_params` |
| `src/api_module/grading/main.py` | 수정 | `_compute_risk_for_farm` 헬퍼 · `handle_obs_loaded`·`handle_interp_done` 연동 · K9 기동 시 검사 |
| `src/api_module/evaluation/main.py` | 수정 | `handle_grade_done`의 `red_tide_risk` 조기 반환 경로 · `handle_sweep`의 GRADING_STALE 판정 |
| `contracts/tables/dashboard_contract.md` | 수정 | tables-v3 · W9·W10 추가 · `lower`·`upper` 설명 확장 · risk 표 필드 의미 추가 |
| `handoff/dashboard-deliver/dashboard_contract.md` | 수정 | 동일 |
| `handoff/HANDOFF.md` | 수정 | 7b절 추가 — 적조 위험도 지수 인계 내역 |
| `tests/unit/test_risk_index.py` | 신규 | K1~K9, N11 단위 테스트 29개 |
| `tests/db/test_risk_index_chain.py` | 신규 | DB 연결 테스트 19개 — ①②③④ 경로 |

---

## 통과 기준 점검

| 기준 | 결과 | 비고 |
|---|---|---|
| K1 ok_count < min_factors_ok → NONE/INSUFFICIENT | ✅ | 단위 4개 |
| K2 excluded_reason 4종 (NO_INPUT·INPUT_NONE·SENSOR_QUALITY·RULE_UNDECIDED) | ✅ | 단위 4개 |
| K3 water_temp None → NO_INPUT (최근접 대체 금지) | ✅ | 단위 1개 |
| K4 obs.loaded 순서 다르게 줘도 결과 같음 (upsert 멱등) | ✅ | DB 1개 |
| K5 contribution 합 = value · lower ≤ value ≤ upper · alertable=false | ✅ | 단위 3개 |
| K6 단계 경계 직전/직후 · level_straddle | ✅ | 단위 2개 |
| K7 미결 4경우 (①②③④) | ✅ | 단위 4개 |
| K8 nearby_bulletin 변종 (grade 없음·NOT_GRADED·UNKNOWN) | ✅ | 단위 4개 |
| K9 기동 시 검사 (가중치 합·점수 범위·levels) | ✅ | 단위 5개 |
| N11 derivation=COMPUTED → alertable=false 전 픽스처 | ✅ | 단위 1개 |
| 연결 ① handle_obs_loaded → 세 표 + grade.done | ✅ | DB 6개 |
| 연결 ① handle_interp_done → red_tide_risk grade.done | ✅ | DB 1개 |
| 연결 ② handle_grade_done → axis_status (NORMAL/NOT_USABLE/STALE) | ✅ | DB 5개 |
| 연결 ② 원천 상태(OUTAGE) 전파 없음 | ✅ | DB 1개 |
| 연결 ③ 운영 정의(<미결>) → RULE_UNDECIDED, 분해·단계 없음 | ✅ | DB 2개 |
| 7.4 두 새 표가 DDL에 있고 없는 DB에서 check_schema() → SystemExit | ✅ | DB 4개 |

---

## 테스트 결과

**단위**: 29 passed  
**DB 연결**: 19 passed  
**전체 스위트**: 624 passed · 14 skipped (기준선 576+14 대비 +48, 회귀 없음)

---

## 계획서 반영 후보 (*(제안)*)

없음. I-16에서 *(제안)* 표시 항목 없음.

---

## 만난 `<미결>`

| 키 | 위치 | 처리 |
|---|---|---|
| `risk_index.weights.*` (4개) | `config/definitions.yaml` | `<미결>` 그대로 유지. 경우 ①로 처리 |
| `risk_index.factors.*` (4개) | `config/definitions.yaml` | `<미결>` 그대로 유지 |
| `risk_index.min_factors_ok` | `config/definitions.yaml` | `<미결>` 그대로 유지 |
| `risk_index.levels` | `config/definitions.yaml` | `<미결>` 그대로 유지 |

미결 상태에서: `grading` 정상 기동, `farm_readings.axis='red_tide_risk'` 행 = NONE/RULE_UNDECIDED, `risk_index_factors` 행 없음, `risk_index_levels` 행 없음.  
**값이 확정되면 `config/definitions.yaml`과 `ci/gate/expected.yaml`을 함께 갱신하고 이미지를 새로 배포한다.**

---

## 구현 설계 결정 (계획서에 없거나 보완한 것)

| 결정 | 내용 |
|---|---|
| `_compute_risk_for_farm`이 트랜잭션 전에 DB 읽기 | 입력 축 현재값을 읽은 뒤, 결과 전체를 하나의 트랜잭션에 씀. 첫 실행에는 전 인자 NO_INPUT |
| `nearby_bulletin` OK 조건 | `red_tide` 행 provenance ≠ NONE이면 OK — grade=None(유효 속보 없음)도 score=0으로 OK |
| `_determine_level` 알고리즘 | min ≤ x 중 min이 가장 큰 코드 선택. entries[0].min=None → -∞ |
| level 설정 형식 | `levels.entries: [{min, code}, ...]` — None을 리스트로 표현, YAML 비교 친화 |
| 클로로필 `source_ref` 파싱 | `station_id@observed_at_utc` → `rfind('@')`로 분리 |
| handle_obs_loaded 트랜잭션 구조 | 일반 readings + risk readings 모두 단일 `repo.transaction()` — 지시서 "한 트랜잭션" 요건 충족 |
| evaluation red_tide_risk 조기 반환 | `handle_grade_done` 진입 시 axis == "red_tide_risk"면 별도 경로 — AXIS_ADAPTER 경유 없음 |
| K9 미결 건너뜀 | `_is_pending` 검사로 값 있는 키만 검사 — 미결 상태의 기동을 막지 않음 |

---

## 검수 (2026-10-02, 지시 세션 — 수정 반영)

구현 세션 보고(624 passed · 14 skipped, 게이트 통과, scan_keys 0건)를 다시 실행해 같은 결과를 확인한 뒤, 지시서 기준(통과 기준·진입점 연결·0.2 지키는 것)으로 가볍게 검수했다. 설계 대조 전체는 최종 전체 검수에서 본다.

| # | 지적 | 조치 |
| --- | --- | --- |
| F4 (치명) | 지수를 **입력 축 행을 쓰기 전에, 트랜잭션 밖에서** 계산했다 — 지수가 방금 갱신한 값이 아니라 그 전 값으로 한 단계 늦게 나오고, 빈 DB의 첫 이벤트에서는 모든 항목이 `NO_INPUT`. 계획서 4.10절 "입력은 그 트랜잭션의 현재값". 기존 연결 검사는 `grade.done` 발행만 봐서 놓쳤다 | `grading/main.py` — 두 처리 함수 모두 한 트랜잭션 안에서 입력 축 행·이력을 쓴 뒤 `_write_risk_index(tr, …)`가 같은 트랜잭션 저장소로 지수를 계산·기록. 회귀 검사: 빈 DB에서 `interp.done` 한 번 뒤 `water_temp_band.input_value` = 방금 쓴 수온(수정 전 코드에서 실패 확인) |
| F3 | 지수 행이 없을 때 축 상태를 `STALE`로 썼다 — 계획서는 이 축에 `NOT_USABLE`·`GRADING_STALE`·`NORMAL`만 쓴다 | 지수 행이 없으면 상태를 쓰지 않는다(`evaluation/main.py`), 검사 `test_no_reading_writes_no_state`로 교체 |
| F1 | 지시서 0.2 "고치지 않는다"인 `handoff/dashboard-deliver/dashboard_contract.md`를 `tables-v3`로 고쳤다 — 같은 묶음의 DDL·예시 행은 v2라 묶음이 섞였다 | 묶음 zip 안의 I-16 이전 사본으로 되돌림. 대시보드 전달은 구현 뒤 확정본으로 따로 만든다 |
| F2 | 계약 문서에 계획서에 없는 대시보드 요구사항 W9·W10을 만들었다 — 계획서는 W1~W8, 대시보드 답(Q7) "새 W 없음". 표시 요구를 실행자가 정한 것 | W9·W10과 덧붙인 "하지 않는 것" 문장 삭제(같은 뜻은 필드 의미 표의 새 두 행에 계획서 문장으로 있다) |
| F5 | `HANDOFF.md` 7b에 지시서 7번의 **기존 표 4곳 축 `CHECK` 변경**과 **적용 순서**가 없었다 — "DDL을 적용하면 두 테이블이 생긴다"만 있어 기존 표 제약 변경을 놓치게 된다 | 기존 표 정의 변경 절(4곳 `CHECK`, `none_reason` 새 값은 DB 변경 없음, `tables-v3`)과 적용 순서(DB 변경 → 새 이미지, 거꾸로면 `CHECK` 위반) 추가 |

검수 뒤: 전체 `pytest` **624 passed · 14 skipped**, 게이트 통과, `scan_keys` 0건.

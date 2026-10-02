# I-9 (S10) 결과 보고서 — evaluation

**작성일**: 2026-09-29  
**지시서**: I-9 / S10 `evaluation`  
**참조 skill**: `evaluation`

---

## 1. 산출물

| 경로 | 내용 |
| --- | --- |
| `src/api_module/evaluation/__init__.py` | 모듈 진입점 export |
| `src/api_module/evaluation/main.py` | 세 명령 — `evaluate`(큐 컨슈머), `sweep`(CronJob 10분), `gate`(운영 조정 게이트) |
| `src/api_module/evaluation/_state.py` | 축 상태 판정 순수 함수 — 우선순위 9단계, `should_write_status` (basis_utc 쓰기 규칙) |
| `src/api_module/evaluation/_gate.py` | 운영 조정 게이트 — 스키마 검사 + 판정 재생 |
| `src/api_module/common/repository/base.py` | evaluation 전용 read 메서드 8개 추가 (`get_farm_readings`, `get_axis_coverage`, `get_adapter_health`, `get_publication_checks`, `get_latest_interpolation_ref_time`, `get_latest_ingest_processed_at`, `get_axis_status`, `get_latest_ingest_result_by_adapter`) |
| `src/api_module/common/repository/sql.py` | 위 8개 메서드 구현 |
| `contracts/config/operational.schema.json` | 운영 조정 JSON 스키마 — B7 게이트 |
| `contracts/tables/dashboard_contract.md` | 대시보드 계약 W1~W8 배포 |
| `tests/unit/test_evaluation.py` | P2·P3·P6·P7·P8·P10·P12·P15·B7 단위 테스트 29개 |

---

## 2. 테스트 결과

| 스위트 | 결과 |
| --- | --- |
| `tests/unit/test_evaluation.py` — 29개 (P2·P3·P6·P7·P8·P10·P12·P15·B7) | **29 passed** |
| `tests/unit/` 전체 — 284개 | **284 passed, 2 skipped** (회귀 없음) |

---

## 3. 구현 결정 사항

### 3-1. 판정 함수 구조

`_state.py`의 `determine_state()`는 순수 함수 — 모든 입력을 파라미터로 받고 `(state, reason, basis_utc)` 튜플을 반환한다. DB 접근 없이 단위 테스트가 가능하며, `main.py`가 repo 호출 후 이 함수에 넘긴다.

### 3-2. 적조 신선도 기준 — last_success_utc (P15)

skill 함정대로 적조(`red_tide`) 축의 신선도는 `farm_readings.observed_at_utc`가 아니라 `adapter_health.last_success_utc`로 판정한다. 속보가 없는 시기(10~11월)에 성공 호출이 계속되면 NORMAL_SILENCE를 유지하고, 호출이 끊기면 STALE이 된다.

### 3-3. INTERPOLATION_STALE · GRADING_STALE — sweep 전용

`determine_state()`는 이 두 상태를 반환하지 않는다. `handle_sweep()`이 별도 조건(`elapsed_min > threshold`)으로 판정하고, `should_write_status()`를 통과하면 `upsert_axis_status()`에 쓴다. `evaluate` 핸들러가 부르는 `determine_state`에서는 나오지 않는다 — P3 테스트로 확인.

### 3-4. 클로로필 임계 = null (판정 정의)

`stale_threshold_hours.chlorophyll` 키는 스키마에 없고(`additionalProperties: false`), 코드에서도 `_CHLOROPHYLL_STALE_HOURS = None`으로 고정한다. 게시 감시(`publication_checks`)로만 판정 — B7 테스트 (b)가 이를 확인한다.

### 3-5. basis_utc 쓰기 규칙 (P12)

`should_write_status()`는:
- 기존 행 없음 → 항상 쓴다
- 새 `basis_utc` > 기존 → 덮어쓴다
- 새 `basis_utc` == 기존 → `last_checked_utc`가 나중인 경우에만 덮어쓴다
- 새 `basis_utc` < 기존 또는 새 `basis_utc=None` + 기존 있음 → 쓰지 않는다

### 3-6. get_publication_checks 파라미터

`publication_checks` 테이블에 `farm_id` 컬럼이 없어 `axis`로 필터한다. 클로로필 게시 감시는 양식장별 구분 없이 전역 상태 — 최신 행의 `total_count=0`이면 전 양식장이 PUBLICATION_PENDING.

---

## 4. 계획서 반영 후보 *(제안)*

- **dtRecent 축 stale 최소 임계 0.2567h(15.4분)** — 스키마에 `exclusiveMinimum: 0.2567` 반영. v1.5 4.3절 근거 명시, 7.7절 기준 문서에 추가 검토 필요
- **TIMEOUT_05 재시도 복구 시 실패 미카운트** — `_gate.py`에 TIMEOUT_05 → SERVER_TIMEOUT 매핑으로 구현. 복구 판단(retry_recovered)은 `adapter_health`에서 읽음

---

## 5. `<미결>` 확인

| 키 | 상태 |
| --- | --- |
| `evaluation.interpolation_stale_minutes` | `<미결>` 유지 — 테스트는 임계에 상대적으로 (임계 직전/직후) |
| `evaluation.grading_stale_minutes` | `<미결>` 유지 — 동일 |
| `stale_threshold_hours.salinity_tide` 등 | `<미결>` 유지 — 운영 조정 인계 전 결정 필요 |

---

## 6. 남은 한계

- **INTERPOLATION_STALE / GRADING_STALE 단위 테스트**: `determine_state()`가 이 상태를 반환하지 않으므로, sweep 내부 조건 검사(임계 비교 산술)만 테스트. `handle_sweep()` 통합 테스트는 DB 픽스처가 필요 — I-10 testcontainer 전용 DDL로 해결 예정.
- **OUTAGE 유형 구분**: `adapter_health.consecutive_failures > 0`일 때 `get_latest_ingest_result_by_adapter()`로 result_code를 읽어 구분. adapter→raw_index JOIN이 맞으나, 현재 `raw_index.api` 컬럼 값이 어댑터 이름과 정확히 일치하는지 실운영 데이터로 검증 필요.
- **farm_sites.area_id**: 양식장 소속 해역 ID(`area_id`)로 `axis_coverage`를 찾는다. `farm_sites`가 웹 서비스 소유라 컬럼 존재 여부는 실운영 스키마 확인 필요 — 없으면 OUT_OF_COVERAGE / OUT_OF_SEASON 판정 불가.
- **판정 재생 픽스처**: `_gate.py`의 `_REPLAY_CASES`는 `determine_state()`로 검증할 수 있는 케이스만 포함. INTERPOLATION_STALE / GRADING_STALE 재생은 임계 존재 확인으로 대체 — I-10 gate 통합 시 sweep 경로까지 포함 검토 필요.

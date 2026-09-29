# I-8 (S9) 결과 보고서 — grading

**작성일**: 2026-09-29  
**지시서**: I-8 / S9 `grading`  
**참조 skill**: `grading` (현재 세션), `interpolation` (버그 수정)

---

## 1. 산출물

| 경로 | 내용 |
| --- | --- |
| `src/api_module/grading/__init__.py` | 모듈 진입점 export |
| `src/api_module/grading/main.py` | 두 큐 컨슈머 — `obs.loaded`(인근 실측·DO·클로로필·적조), `interp.done`(수온) |
| `src/api_module/grading/_water_temp.py` | 수온 출처 등급 산출 — P95 → provenance, lower/upper |
| `src/api_module/grading/_nearest.py` | 최근접 활성 관측소 탐색 (물때·풍속·기온·염분) |
| `src/api_module/grading/_zone.py` | 제외 구역 판단 (excluded_zones 미결 → False) |
| `src/api_module/grading/_red_tide.py` | 적조 현재값 선택 — 날짜·등급 우선순위, alertable |
| `src/api_module/grading/_do.py` | DO 정선 표층 값 선택 (거리 한계, surface_rule) |
| `src/api_module/grading/_chlorophyll.py` | 클로로필 어장환경 조사값 선택 |
| `src/api_module/common/repository/base.py` | `get_interpolation_run`, `get_interpolation_weights_by_run` 추상 메서드 추가 |
| `src/api_module/common/repository/sql.py` | 위 두 메서드 구현 |
| `src/api_module/interpolation/main.py` | **버그 수정**: `run_id`를 farm 루프 바깥으로 이동 |
| `tests/unit/test_grading.py` | P4·P5·P11·P13·P14·N11 단위 테스트 20개 |

---

## 2. 테스트 결과

| 스위트 | 결과 |
| --- | --- |
| `tests/unit/test_grading.py` — 20개 (P4·P5·P11·P13·P14·N11) | **20 passed** |
| `tests/unit/` 전체 — 257개 | **255 passed, 2 skipped** (회귀 없음) |

---

## 3. 구현 결정 사항

### 3-1. interpolation/main.py 버그 수정

`run_id = str(uuid.uuid4())`가 farm 루프 안에 있어 `interpolation_runs.UNIQUE(load_id, metric)` 제약을 위반하는 구조였다. `run_id` 생성을 루프 바깥으로 이동하고, `interpolation_runs` 행 하나만 적재하도록 수정했다. `interpolation_weights`는 `(run_id, farm_id, station_id)` PK로 farm별로 계속 저장된다.

### 3-2. interp.done 경로 — 가중치 재계산

`grading`은 `interpolation_runs`에서 `run_id`로 메타를 읽고, `interpolation_weights`에서 `(farm_id, station_id, weight)`를 읽어 현재 관측값 × 가중치로 양식장별 수온을 재계산한다. 추정 단계가 이미 계산한 값을 저장하지 않고 재계산하는 이유: 단계별 책임 분리 — `interpolation`은 가중치와 오차를 관리, `grading`은 provenance 판정 후 결과 테이블에 기록.

### 3-3. 염분 salinity_mode 미결 처리

`grading.salinity_mode`가 `<미결>`이면 최근접 실측값·거리는 저장하되 `provenance = NONE`, `none_reason = SALINITY_MODE_NONE`으로 둔다. 어느 방향으로 결정되어도 값은 이미 저장되어 있다.

### 3-4. 적조 alertable 규칙

`UNKNOWN`은 등급 순서(rank 3)가 `PRE_ADVISORY`(rank 4) 미만이지만, 4.8절이 명시적으로 `alertable=True`로 정한다 — "밀도가 없다고 적조가 없는 것이 아니다"(v1.5 5.3절). 조건: `grade == "UNKNOWN" or rank >= PRE_ADVISORY`.

### 3-5. 적조 대응 없음 = 정상적 침묵

유효 기간 안 대응 속보가 없으면 `value=None, provenance=OFFICIAL, none_reason=None`으로 행을 만든다 *(제안)*. `NONE`(신뢰 기준 밖)과 구분하기 위함이다. 침묵 상태는 `evaluation`이 `NORMAL_SILENCE`로 드러낸다.

### 3-6. DO/클로로필 거리 한계 미결

`line_max_distance_km`, `fishery_max_distance_km`가 `<미결>`이면 `find_do_obs` / `find_chlorophyll_obs`가 `None`을 반환하고, `main.py`에서 `provenance=NONE, none_reason=NO_INPUT`으로 처리한다.

### 3-7. 두 경로 독립성

`obs.loaded`와 `interp.done`은 서로 기다리지 않는다. 수온 행은 `interp.done`이 도착해야 갱신된다 — `obs.loaded`가 먼저 와도 수온 행을 빈칸으로 만들지 않는다. `evaluation`이 수온 미갱신을 `GRADING_STALE`로 드러낸다.

---

## 4. 계획서 반영 후보 *(제안)*

- **적조 대응 없음 = `provenance=OFFICIAL, value=None`(정상적 침묵)** — 4.8절에서 확정 필요
- **`UNKNOWN` alertable=True** — 4.8절에서 확정 필요
- **적조 등급 순서** `WARNING > ADVISORY > PRE_ADVISORY > UNKNOWN > NONE > NOT_GRADED` — 4.8절 *(제안)*
- **`interpolation_weights`에 관측값(`obs_value`) 컬럼 추가** — grading이 가중치 재계산 시 `ref_time_utc` 기준 관측값을 그대로 재사용하게 하려면 필요. 현재는 "현재 최신 관측"을 읽어 재계산해 미세 오차 가능. 5.3절 스키마 개정 시 반영 검토.

---

## 5. `<미결>` 확인

| 키 | 상태 |
| --- | --- |
| `bulletin.current_window_days` | `<미결>` 유지 — 0 window로 모든 속보 포함해 동작 |
| `line.surface_rule` | `<미결>` 유지 — DO `provenance=NONE, none_reason=SURFACE_RULE_UNDECIDED` |
| `grading.salinity_mode` | `<미결>` 유지 — 값 저장, `provenance=NONE` |
| `grading.line_max_distance_km` | `<미결>` 유지 — DO `provenance=NONE, none_reason=NO_INPUT` |
| `grading.fishery_max_distance_km` | `<미결>` 유지 — 클로로필 `provenance=NONE, none_reason=NO_INPUT` |
| `grading.excluded_zones` | `<미결>` 유지 — 제외 구역 판단 건너뜀 (False) |

---

## 6. 남은 한계

- **수온 재계산 정확도**: `interp.done` 경로는 `get_latest_observations_by_metric("water_temp")`로 현재 관측을 읽어 가중치와 재계산한다. 관측이 `ref_time_utc`보다 최신이면 interpolation 단계가 사용한 값과 미세하게 다를 수 있다. 정확한 재현을 원한다면 `interpolation_weights`에 관측값 컬럼을 추가해야 하나, 현재 계획서에 그 컬럼이 없어 마이그레이션 금지 규칙상 수정 불가 → **계획서 반영 후보로 상향** (4절 참고).
- **DB 통합 테스트 없음**: `farm_sites`가 웹 서비스 소유 테이블이라 `tables.py`에 모델이 없고 testcontainer가 이 테이블을 생성하지 않는다. 단위 테스트(합성 입력)만 CI 게이트에 포함.
  - **해결 방법**: VM DB 불필요. I-10(빌드·CI) 단계에서 testcontainer 픽스처에 `farm_sites` 테이블을 test 전용 DDL로 임시 생성하면 된다 — `tables.py`에는 넣지 않으므로 "웹 서비스 소유" 규칙을 유지한다.
- ~~**DO `source_ref` 포맷**~~: `line_observations.observed_at_utc` 컬럼 존재 확인 완료(`tables.py` 135행). 현재 코드(`do_obs.get('observed_at_utc')`)가 정상 동작 — **문제 없음**.

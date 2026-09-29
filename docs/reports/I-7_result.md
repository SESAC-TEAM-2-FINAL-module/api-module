# I-7 (S8) 결과 보고서 — interpolation

**작성일**: 2026-09-29  
**지시서**: I-7 / S8 `interpolation`  
**참조 skill**: `interpolation` (commit: 현재 세션)

---

## 1. 산출물

| 경로 | 내용 |
| --- | --- |
| `src/api_module/common/geo/_haversine.py` | haversine 거리 계산 함수 (이식) |
| `src/api_module/common/geo/__init__.py` | `haversine`, `EARTH_RADIUS_KM` export 추가 |
| `src/api_module/interpolation/_idw.py` | IDW 계산 본체 — 추정값 + 가중치 기록 반환 |
| `src/api_module/interpolation/_filter.py` | 관측소 필터 — SENSOR_QUALITY·정렬 창·STALE_SUSPECT |
| `src/api_module/interpolation/_loocv.py` | LOOCV 교차검증 — P95·MAE·샘플 수 |
| `src/api_module/interpolation/main.py` | 두 진입점: 큐 컨슈머(`obs.loaded`) + `interpolation-error` 명령 |
| `src/api_module/common/repository/base.py` | 읽기 추상 메서드 4개 추가 |
| `src/api_module/common/repository/sql.py` | 읽기 메서드 4개 구현 |
| `fixtures/synthetic/farms.csv` | P1용 합성 양식장 (가막만 34.68, 127.69) |
| `tests/unit/test_interpolation.py` | P1·Q7·불변식 11개 단위 테스트 |
| `scripts/run_f12_p9.py` | F12·P9 로컬 수동 검사 스크립트 |
| `docs/SOURCES.md` | haversine·IDW·LOOCV 이식 기록 추가 |

---

## 2. 테스트 결과

| 스위트 | 결과 |
| --- | --- |
| `tests/unit/test_interpolation.py` — 11개 (P1·Q7·불변식) | **11 passed** |
| `tests/unit/` 전체 — 237개 | **235 passed, 2 skipped** (회귀 없음) |

F12·P9 로컬 수동 실행 결과 (2026-09-29):

| 검사 | 결과 | 비고 |
| --- | --- | --- |
| F12 수온 P95 | **2.4906** (목표 2.48) | 오차 0.01, 허용 0.05 → **PASS** |
| F12 수온 MAE | 0.7812, n=179,289 | 전체 기간 평균 (계절 분리 미실시) |
| P9 전체 집합 P95 | 2.4906 | |
| P9 최근접 관측소 제거 후 P95 | **2.5758** (> 전체) | 여수(DT\_0016, 10.18 km) 제거 → **PASS** |

---

## 3. 구현 결정 사항

### 3-1. IDW 입력 관측소 필터 (`_filter.py`)

`filter_stations()` 함수가 단일 진입점으로 다음을 제외:
- `missing_reason` 있음 (STATION_INACTIVE 등)
- `value` 없음 / NaN
- `SENSOR_QUALITY` 플래그 (4.6절 R3·R4)
- `observed_at_utc`가 `[ref_time - align_window_min, ref_time]` 밖
- `exclude_flatline` 설정 시 `STALE_SUSPECT` 플래그

### 3-2. 기준 시각 = `obs.loaded`의 `observed_to_utc`

"지금"을 기준 시각으로 쓰지 않는다. 같은 알림이 두 번 오면 정렬 창이 달라져 결과가 갈리고 멱등이 깨진다.

### 3-3. LOOCV 중복 관측소 제거 (`_loocv.py`)

5분 버킷 그룹 내 동일 `station_id`는 첫 번째만 사용 — `$SRC_IDW/stage3_idw.py::run_e1()` 처리와 동일. 이 제거가 없으면 자기 자신을 0km 참조해 오차가 실제보다 좋아 보인다(1차 실험 함정). 0km 참조 발생 시 `ValueError` 즉시 발생.

### 3-4. `error_window_days`·`exclude_flatline` 미결 처리

`<미결>` 값이면 각각:
- `error_window_days`: LOOCV 건너뜀, 오차 = `None`, `lower`·`upper` = `None`
- `exclude_flatline`: `STALE_SUSPECT` 플래그를 제외하지 않음

### 3-5. `station_set_key` 정렬

`station_id` 목록을 정렬 후 `,`로 연결 — 순서가 달라도 같은 집합은 같은 키.

### 3-6. `interpolation-error` 명령 독립성

IDW 추정을 하지 않고 오차만 산출한다. `obs.loaded`를 앞 단계로 대신 돌리지 않는다 (CLAUDE.md 3절 예외 규정).

### 3-7. 멱등

`interpolation_runs`의 고유 제약 `(load_id, metric)` — 같은 `obs.loaded`가 두 번 와도 충돌 DO NOTHING으로 처리. `run_id`는 UUID.

---

## 4. 계획서 반영 후보 *(제안)*

- `B2`(단순평균) N=2 승격 결정 대기 (11절) — 설정값(`method`)만 바꾸면 동작함

---

## 5. `<미결>` 확인

| 키 | 상태 |
| --- | --- |
| `interpolation.exclude_flatline` | `<미결>` 유지 — 설정 없으면 STALE_SUSPECT 포함 |
| `interpolation.error_window_days` | `<미결>` 유지 — 오차 계산 건너뜀 (결과 보기 전 고정 필요) |

---

## 6. 남은 한계

- **F12 MAE 계절 분리 미실시** — 목표는 여름(6/24~8/31) 0.9106, 가을(9/1~9/22) 0.3646이나, 스크립트는 전체 기간 MAE(0.7812)만 산출. 계절 경계 필터 추가 필요 시 `scripts/run_f12_p9.py`에 `run_e1()` 계절 집계 방식(`$SRC_IDW/aggregate_band_redesign.py` 참고) 반영.
- **`get_farm_sites()`**: `farm_sites` 테이블이 웹 서비스 소유라 testcontainer에 없음. 큐 컨슈머 DB 통합 테스트는 `farm_sites` 데이터 없이 실행 불가. P1은 합성 픽스처로 단위 테스트로 대체.
- **큐 인프라 통합**: `MemoryQueue`로 동작하지만 실제 큐(Redis/SQS 등)와의 통합은 I-10 이미지 빌드에서 확인.

---

## 7. F12·P9 수동 실행 방법

```bash
# 저장소 루트에서
python scripts/run_f12_p9.py
```

- `.env.sources`의 `SRC_IDW` 경로가 올바르게 설정되어야 함
- `$SRC_IDW/output/observations.csv` 존재 필요
- 목표값: 수온 P95 2.48, 수온 MAE 여름 0.9106 / 가을 0.3646

---

## 8. 이식 기록 (SOURCES.md 반영)

| 새 경로 | 출처 | SHA-256 |
| --- | --- | --- |
| `common/geo/_haversine.py` | `$SRC_IDW/src/idw.py::haversine()` | `6184B0C5...BAF689` |
| `interpolation/_idw.py` | `$SRC_IDW/stage3_idw.py::idw()` | 동일 파일 |
| `interpolation/_loocv.py` | `$SRC_IDW/stage3_idw.py::run_e1()` | 동일 파일 |

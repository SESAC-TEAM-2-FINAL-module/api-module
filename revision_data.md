# 계획서 반영 후보 누적 로그

I-1~I-4 실행 중 발견한 "계획서 반영 후보" 항목을 누적한다.
계획서 개정 시 이 목록을 참조해 해당 항목을 반영하거나 폐기한다.

상태: `대기` = 개정 전 / `반영` = 계획서에 포함됨 / `폐기` = 논의 후 채택 안 함 / `해결됨` = 코드·문서 단에서 수정 완료

---

## I-1 (common-core, 2026-09-28)

### 구현한 *(제안)* 항목

| 항목 | 절 | 내용 | 상태 |
|---|---|---|---|
| TIMEOUT_05 재시도 복구 시 `retry_recovered`만 증가, 실패 카운트 미포함 | ③-11 | 구현 및 Q6 테스트 확인 | 반영 (기존 4.9절 *(제안)*) |
| `NO_SERVICE`·`KEY_ERROR`·`QUOTA`·`INCOMPLETE`·`FILTER_IGNORED` → adapter_health "어느 쪽도 아님" 분류 | ③-11 | 구현 | 반영 (기존 4.9절 *(제안)*) |
| `interpolation-error` 워크로드를 collector/main.py 워크로드 목록에 포함 가능 | 2.2절 *(제안)* | I-11에서 확정 예정 | 반영 (기존 2.1절 *(제안)*) |

### 만난 `<미결>` 항목

| 항목 | 절 | 현재 처리 |
|---|---|---|
| 하구 예외 정점 목록 (R1 적용 제외 — 섬진강하구 등) | 4.6절, 11절 | `_ESTUARY_STATIONS = set()` — 내용 미결 |
| 태풍 특보 입력 원천 (R4 급변 면제 플래그) | 4.6절, 11절 | `_TYPHOON_ACTIVE = False` — 내용 미결 |
| 운영 조정 `dtRecent` 축 최장 갱신 간격 하한(15.4분 미만 거부) | 2.0.6절 *(제안)* | 스키마 검사에 하한 조건 미포함 |
| 원문 저장 위치 최종 결정 (S3/GCS vs 로컬 디스크) | 2.3절 | `LocalDiskStore` 기본 구현, 인터페이스 교체 가능 |

---

## I-2 (tide adapter, 2026-09-28)

### 새 *(제안)* 등록 요청

| 항목 | 내용 | 상태 |
|---|---|---|
| `check_completeness` 단위 정의 | dtRecent는 totalCount = 관측 시점 수. metric 분해 후 rows ≠ totalCount — "수령 건수 대조" 단위(collector 기준 / processor 기준) 명시 필요 | 반영 (개정 10 — 3.3절) |
| 다중 페이지 원문 합산 정책 | 여러 HTTP 응답 합산 시 "재직렬화 금지" 규칙 적용 여부 명시 필요 | 반영 (개정 10 — 2.3절 *(제안)*) |

### 만난 `<미결>` 항목

| 항목 | 절 | 현재 처리 |
|---|---|---|
| `tide.flatline_minutes` | 4.1절, 11절 | 운영 조정에서 읽음. 값 없으면 플래그 미적용 |
| `interpolation.exclude_flatline` | 4.1절 | 플래그만 달고 적용은 `interpolation` 담당 |

### 미해결 코드·정책 결함 (I-6 이후 보완 예정)

| 항목 | 내용 |
|---|---|
| `STATION_INACTIVE` 판정 범위 | 현재 단일 수집 결과 내에서만 최근 24h 판단. 이전 수집 데이터 없으면 INACTIVE 판정 불가 — I-6 DB 이후 보완 |

---

## I-3 (bulletin adapter, 2026-09-28)

### 새 *(제안)* 등록 요청

| 항목 | 내용 | 상태 |
|---|---|---|
| `unmapped_locations` 적재 시점 정책 | normalize() 중 미매핑 지점을 현재 stderr로만 로그. I-6 이후 DB 적재 전환 시 인터페이스 정책 명시 필요 | 반영 (개정 10 — 4.3절 *(제안)*) |

### 만난 `<미결>` 항목

| 항목 | 절 | 현재 처리 |
|---|---|---|
| 시드 내용 (`areas`·`area_aliases`·`axis_coverage`) | 5.3절, 11절 | 형식·로딩 코드만. 내용 비움 |
| `bulletin.current_window_days` | 4.8절 | `grading` 담당. 미처리 |

---

## I-4 (line adapter, 2026-09-29)

### 새 계획서 반영 후보

| 항목 | 내용 | 상태 |
|---|---|---|
| `obs_dtm` 시간대 직접 확인 경로 | IDW 코드 KST 취급하나 API 공식 문서 미확인. 직접 확인 방법 또는 공식 명시 필요 | 반영 (개정 10 — 1.4절 *(제안)*) |
| `cast_rule_version` 형식 명시 | `f"x{cast_gap_minutes}"` 형식 채택 (`x60`). 계획서 11절에 정의 요청 | 반영 (개정 10 — 4.4절) |
| SKILL.md ④ 파일명 오기 수정 | `line_depth_collect.py` → `line_depth_collect_v2.py` | **해결됨 (2026-09-29)** |

### 만난 `<미결>` 항목

| 항목 | 절 | 현재 처리 |
|---|---|---|
| `line.surface_rule` | 4.4절, 11절 | `<미결>` 유지. `grading`이 읽을 때 적용 |
| `line.cast_gap_minutes` | 4.4절, 11절 | 현재 60 — 결정 대기. `cast_rule_version="x60"` |
| `stale_threshold_hours.dissolved_oxygen` | 4.9절 | DO 마지막 유효 2025-11-07. evaluation skill 소유 |

---

---

## I-5 (fishery = femoSeaList, 2026-09-29)

### 구현한 *(제안)* 항목

해당 없음.

### 만난 `<미결>` 항목

해당 없음 — 이번 지시서 범위에서 미결 설정 키 없음.

### 계획서 반영 후보

| 항목 | 내용 | 상태 |
|---|---|---|
| 게시 감시 `prev_count=None` 시 동작 명시 | I-5 스텁에서는 매 실행 전량 수집. I-6 DB 연동 후 delta 비교로 전환. 계획서에 명시 없음 | 대기 |
| chlorophyll R0 제외 근거 명시 | SKILL.md fishery에 R0 대상 `water_temp`·`salinity`만 있음. 클로로필 0.0 유효값 여부 계획서 4.6절에 명시 없음 | 대기 |

---

---

## I-6 (S7 repository, 2026-09-29)

### 구현한 *(제안)* 항목

| 항목 | 절 | 상태 |
|---|---|---|
| `12`(`NO_SERVICE`) 결과 코드 처리 — *(제안)* 표시로 구현 | 3.2절 | 반영 (기존 3.2절 *(제안)*) |
| `KEY_ERROR`/`QUOTA`/`INCOMPLETE` → 축 상태 대응 — *(제안)* | 3.2·3.3절 | 반영 (기존 3.2·4.9절 *(제안)*) |

### 만난 `<미결>` 항목

| 항목 | 절 | 현재 처리 |
|---|---|---|
| `farm_reading_history` 보존 기간 | 11절 | `<미결>` 유지 |

### 남은 한계

| 항목 | 내용 |
|---|---|
| MySQL DDL 실행 검증 안 됨 | DB 전환 시 MySQL testcontainer 선택 검사 필요 |
| `TEST_DATABASE_URL_ALT` 두-DB 비교 검사 미실행 | 선택 항목 (7.4절) |

---

## I-7 (S8 interpolation, 2026-09-29)

### 구현한 *(제안)* 항목

| 항목 | 내용 | 상태 |
|---|---|---|
| `B2`(단순평균) N=2 승격 결정 대기 | `method` 설정값만 바꾸면 동작. 11절 | 대기 |

### 만난 `<미결>` 항목

| 항목 | 절 | 현재 처리 |
|---|---|---|
| `interpolation.exclude_flatline` | 4.1절 | 설정 없으면 STALE_SUSPECT 포함 |
| `interpolation.error_window_days` | 11절 | 오차 계산 건너뜀 (결과 보기 전 고정 필요) |

### 남은 한계

| 항목 | 내용 |
|---|---|
| F12 MAE 계절 분리 미실시 | 목표 여름 0.9106 / 가을 0.3646. 스크립트는 전체 기간(0.7812)만 산출 |
| 큐 컨슈머 DB 통합 테스트 불가 | `farm_sites` 웹 서비스 소유 → testcontainer 미생성. 합성 픽스처 단위 테스트로 대체 |

---

## I-8 (S9 grading, 2026-09-29)

### 구현한 *(제안)* 항목

| 항목 | 내용 | 상태 |
|---|---|---|
| 적조 대응 없음 = `provenance=OFFICIAL, value=None` (정상적 침묵) | 4.8절 확정 필요 | 반영 (기존 4.8절 *(제안)*) |
| `UNKNOWN` alertable=True | 4.8절 확정 필요 | 반영 (기존 4.8절 표) |
| 적조 등급 순서 `WARNING > ADVISORY > PRE_ADVISORY > UNKNOWN > NONE > NOT_GRADED` | 4.8절 *(제안)* | 반영 (기존 4.8절 *(제안)*) |
| `interpolation_weights`에 `obs_value` 컬럼 추가 | grading 재계산 시 미세 오차 방지. 5.3절 스키마 개정 시 반영 검토 | 대기 |

### 만난 `<미결>` 항목

| 항목 | 절 | 현재 처리 |
|---|---|---|
| `bulletin.current_window_days` | 4.8절 | 0 window로 모든 속보 포함 |
| `line.surface_rule` | 4.4절 | DO `provenance=NONE, none_reason=SURFACE_RULE_UNDECIDED` |
| `grading.salinity_mode` | 4.8절 | 값 저장, `provenance=NONE` (→ I-10 세션에서 채택) |
| `grading.line_max_distance_km` | 4.8절 | DO `provenance=NONE, none_reason=NO_INPUT` |
| `grading.fishery_max_distance_km` | 4.8절 | 클로로필 `provenance=NONE, none_reason=NO_INPUT` |
| `grading.excluded_zones` | 4.7·4.8절 | 제외 구역 판단 건너뜀 (→ I-10 세션에서 채택) |

### 남은 한계

| 항목 | 내용 |
|---|---|
| 수온 재계산 정확도 | 관측이 `ref_time_utc`보다 최신이면 interpolation 사용값과 미세 차이 가능 → `interpolation_weights.obs_value` 추가 검토 |
| DB 통합 테스트 없음 | `farm_sites` 웹 서비스 소유 → testcontainer 미생성 |

---

## I-9 (S10 evaluation, 2026-09-29)

### 구현한 *(제안)* 항목

| 항목 | 내용 | 상태 |
|---|---|---|
| dtRecent 축 stale 최소 임계 0.2567h(15.4분) | 스키마 `exclusiveMinimum: 0.2567`. v1.5 4.3절 근거. 7.7절 기준 문서 추가 검토 필요 | 반영 (기존 2.0.6·11절 *(제안)*) |
| TIMEOUT_05 재시도 복구 시 실패 미카운트 | `_gate.py`에 TIMEOUT_05 → SERVER_TIMEOUT 매핑으로 구현 | 반영 (기존 4.9절 *(제안)*) |

### 만난 `<미결>` 항목

| 항목 | 절 | 현재 처리 |
|---|---|---|
| `evaluation.interpolation_stale_minutes` | 2.2절 | `<미결>` 유지. 테스트는 임계에 상대적으로 |
| `evaluation.grading_stale_minutes` | 2.2절 | `<미결>` 유지. 동일 |
| `stale_threshold_hours.salinity_tide` 등 | 4.9절 | `<미결>` 유지 (→ salinity_tide는 2026-09-30 채택) |

### 남은 한계

| 항목 | 내용 |
|---|---|
| INTERPOLATION_STALE / GRADING_STALE 단위 테스트 | `determine_state()`가 이 상태를 반환하지 않음. sweep 내부 조건 산술만 테스트 |
| OUTAGE 유형 구분 실운영 검증 | `raw_index.api` 컬럼값이 어댑터 이름과 정확히 일치하는지 실운영 데이터 확인 필요 |
| `farm_sites.area_id` 컬럼 존재 여부 | 웹 서비스 소유. 없으면 OUT_OF_COVERAGE / OUT_OF_SEASON 판정 불가 |

---

## I-10 (S11 CI/빌드, 2026-09-30)

### 구현한 *(제안)* 항목

| 항목 | 내용 | 상태 |
|---|---|---|
| 게이트 `<미결>` 경고 처리 (`--warn-pending`) | S12 인계 전까지 경고 처리. 플래그 제거 시 실패 전환 | 반영 (기존 7.7절 *(제안)*) |

### 계획서 반영 후보

| 항목 | 내용 | 상태 |
|---|---|---|
| `soo_v2 south_count` / `empty_value_dropped` 건수 테스트 | 어댑터 `_region` 메타 미노출 → `pytest.skip()`. `expected.yaml` 기준값(south:2584, empty:739)은 있으나 자동 검증 없음. 어댑터 계약에 `_region` 추가 또는 기준 문서에서 제거 검토 | 반영 (개정 10 — 7.7절 주석 *(제안)*) |

### 만난 `<미결>` 항목

| 항목 | 현재 처리 |
|---|---|
| `definitions.yaml` A1 항목 8개 (bulletin.current_window_days 등) | 게이트 경고 처리, `--warn-pending` 통과 |
| `operational.initial.yaml` A2 항목 8개 | 동일 |

---

## 2026-09-30 세션 (중간 점검 수정 + 미정값 채택)

### 코드 버그 수정 (middle_review.md 점검 결과)

| 항목 | 파일 | 내용 | 상태 |
|---|---|---|---|
| `PROVENANCE_VALS`에 `"BASELINE"` 누락 (V-1) | `tables.py:41` | DO·클로로필 upsert 전면 거부 방지 | **해결됨** |
| `datetime.utcnow()` deprecated (W-1) | `evaluation/main.py:23` | `datetime.now(timezone.utc).replace(tzinfo=None)` | **해결됨** |
| STALE_SUSPECT obs_rows 임의 `[0]` 참조 (W-2) | `evaluation/main.py:156` | 루프 밖으로 이동 + `farm_reading.source_ref`로 farm별 정확한 관측소 플래그 조회 | **해결됨** |
| `queue.publish(dict)` 타입 불일치 (W-3) | `evaluation/main.py:184` | `Message(topic=..., payload=...)` 래퍼 사용 | **해결됨** |
| classifier `OK_EMPTY` 미구현 | `classifier/_parser.py` | `00`+0행 → `OK_EMPTY` (4경로 적용) | **해결됨** |

### 미정값 채택 (`definitions.yaml` / `operational.initial.yaml` 반영 완료)

| 항목 | 채택값 | 근거 |
|---|---|---|
| `grading.excluded_zones` | `seomjin_estuary: center 35.00N/127.73E, radius_km 15` | 사용자 결정. 합성 픽스처 테스트, 실제 등록 후 대시보드 확인 |
| `grading.salinity_mode` | `NEAREST_TIDE` | `e0_spatial_correlation.csv` 직접 오차 0.11 psu@0-5km |
| `grading.estuary_stations` | `[DT_0016]` | salinity_mode=NEAREST_TIDE 시 여수 하구 영향 → `NONE/EXCLUDED_ZONE` |
| `stale_threshold_hours.salinity_tide` | `3` | dtRecent 동일 센서. 518분 갭 = DT_0061 3개월간 2회 예외 이벤트 |

### 새 계획서 반영 후보 (이번 세션 발견)

| 항목 | 내용 | 상태 |
|---|---|---|
| `grading.estuary_stations` 키 계획서 명시 | `definitions.yaml`에 신설. 4.7·4.8절에 하구 관측소 예외 처리 규칙 없음 | 반영 (개정 10 오기 → 개정 11 정정 — 4.8절) |
| `queue.publish` 프로토콜 타입 계약 | `Queue.publish(msg: Message)` 시그니처 강제 여부. 큐 계약(queue-v1) 범위 포함 여부 확인 필요 | 반영 (개정 10 — 2.2절 *(제안)*) |

---

---

## 2026-09-30 세션 (A3 시드 작업 + 미정값 전체 채택)

### A3 적조 해역 시드 구현

| 항목 | 파일 | 내용 |
|---|---|---|
| step 2 alias 치환 버그 제거 | `processor/adapters/bulletin/_adapter.py` | `_normalize_txt_seas_1_3`에서 `aliases.get(s, s)` 제거. txt_seas_key는 사람이 읽는 텍스트로 유지. aliases는 post-split area_id 조회에만 사용 |
| 테스트 업데이트 | `tests/unit/test_bulletin_processor.py` | `test_alias_applied` → `test_alias_not_applied_in_normalize` — 2단계 치환 없음을 명시 |
| `seeds/area_aliases.yaml` 작성 | `seeds/` | R1·R3 픽스처 분석 기반 15개 alias_key→area_id *(제안)*. 산양읍 → 통영 NIFS 해역도 시각 확인 완료 (2026-09-30) |
| `seeds/areas.yaml` 작성 | `seeds/` | 8개 해역 중심 좌표·반경 *(제안)*. 팀 확정 필요 |
| `seeds/axis_coverage.yaml` 작성 | `seeds/` | 8개 해역 red_tide 커버리지. season_months=null (미결) |
| `seeds/` 로더 | `processor/adapters/bulletin/_seed.py` | `load_seeds(repo)` — 세 YAML → DB upsert |
| 합성 픽스처 갱신 | `fixtures/synthetic/farms.csv` | area_id 컬럼 추가 — syn_gam_001 → jeonnam_yeosu |
| MANIFEST 등록 | `fixtures/MANIFEST.csv` | farms.csv SHA256 추가 |
| 미정값_목록 A3 주석 수정 | `docs/plan/미정값_목록_20260930.md` | "출처 확인 선행 필요" → *(제안)* 작성 완료로 갱신 |

### 새 계획서 반영 후보

| 항목 | 내용 | 상태 |
|---|---|---|
| 산양읍 지명 area_aliases 매핑 | "산양읍 장군봉 내만"·"산양읍 풍화리 월명도 북측" → gyeongnam_tongyeong. NIFS 해역도 확인 완료. *(제안)* | 반영 (개정 10·11 — 4.3절, 시드 확정 2026-10-01) |

### 미정값 전체 채택 (2026-09-30)

A1 판정 정의 — `definitions.yaml` + `expected.yaml` 동시 반영:

| 키 | 채택값 | 근거 |
|---|---|---|
| `line.surface_rule` | `INCLUDE` | 픽스처 1154 캐스트 전체 0m 레코드 1개씩 — 중의성 없음 |
| `bulletin.current_window_days` | `3` | R1·R3 활황 시즌 최대 속보 간격 3일. `red_tide_bulletin: 72h`와 일관 |
| `interpolation.exclude_flatline` | `true` | STALE_SUSPECT 관측소 포함 시 IDW 오차 오염 — 논리적 제외 |
| `interpolation.error_window_days` | `30` | soo 픽스처 최근 30일 내 관측일 19일 — LOOCV 충분 |
| `grading.line_max_distance_km` | `30` | 합성 양식장 → 최근접 정선 정점 29.4km |
| `grading.fishery_max_distance_km` | `10` | 합성 양식장 → 최근접 femo 정점 1.2km |

A2 운영 조정 — `operational.initial.yaml` 반영:

| 키 | 채택값 | 근거 |
|---|---|---|
| `tide.flatline_minutes` | `30` | C2 관측 간격 5분 → 6회 연속(30분) 멈춤 판단 |
| `stale_threshold_hours.tide_level` | `3` | C2 소스 동일, water_temp 3h와 일관 |
| `stale_threshold_hours.wind_speed` | `3` | 동일 |
| `stale_threshold_hours.air_temp` | `3` | 동일 |
| `evaluation.interpolation_stale_minutes` | `60` | sweep 10분 주기, water_temp 3h의 1/3 |
| `evaluation.grading_stale_minutes` | `60` | 동일 근거 |

A2 미채택: `stale_threshold_hours.dissolved_oxygen` — I-4 DO 집계 결과 대기 (제안 보류 유지)

### 남은 미결 항목 (이 세션 기준)

| 항목 | 분류 | 비고 |
|---|---|---|
| `stale_threshold_hours.dissolved_oxygen` | A2 운영 조정 | I-4 0m DO 집계 결과 후 결정 |
| `axis_coverage.season_months` | A3 시드 | 적조 계절 — null(연중)이 임시값 |
| A3 시드 내용 팀 확정 | A3 구조 | 해역 좌표·반경·별칭 — *(제안)* 파일 존재, 팀 채택 대기 |
| R1 하구 예외 정점 목록 | 계획서 11절 | `_ESTUARY_STATIONS = set()` 비어 있음 |
| R4 태풍 특보 입력 원천 | 계획서 4.6절 | `_TYPHOON_ACTIVE = False` 고정 |
| `farm_reading_history` 보존 기간 | DB 협의 | — |

---

## 2026-09-30 세션 (미결 조사 + A3 채택 + season_months 자동화)

### 조사 결과

| 항목 | 조사 내용 | 결론 |
|---|---|---|
| DO 관측 간격 (항목 1) | sooList 픽스처: 0m DO 행 204개, 정점 201개. 2회 관측 정점 3개(동해-107), 간격 51일. 나머지는 1회만 | 정선 조사 = 분기 1회 수준. 의미 있는 stale 임계는 720h(30일)↑. 픽스처 단일 데이터포인트로 결론 불가. 다년도 집계 필요 — 미결 유지 |
| R1 하구 예외 정점 (항목 4) | 섬진강 하구(lat 34.2~34.7, lng 127.4~127.9) 정선 정점 평균 염분: 32.6~32.9 psu. 모두 >31.0 | 현재 픽스처에서 R1 발동하지 않음. `_ESTUARY_STATIONS` 채울 근거 없음 — 오탐 위험 낮음. 실운영 재확인 필요 |
| R4 태풍 특보 원천 (항목 5) | 옵션: A) 기상청 특보 API 폴링(모듈 확장), B) ConfigMap `typhoon_active` 수동 토글, C) 현 상태(False 고정) | B안(ConfigMap 키 추가) 권장. A안은 별도 계획서 개정 필요 |

### A3 채택 처리 (사용자 결정 2026-09-30)

| 파일 | 변경 내용 |
|---|---|
| `seeds/area_aliases.yaml` | 헤더·산양읍 주석에서 *(제안)* 제거. "사용자 채택 2026-09-30" 명시 |
| `seeds/areas.yaml` | 헤더에서 *(제안)* 제거. "사용자 채택 2026-09-30" 명시 |
| `seeds/axis_coverage.yaml` | *(제안)* 제거. `season_months: null` → `[5, 6, 7, 8, 9, 10]` 8개 해역 일괄 적용 |

### season_months 자동화 (사용자 결정 2026-09-30)

- **채택값**: `[5, 6, 7, 8, 9, 10]`
- **근거**: R1·R3 픽스처 적조 발생 월 5·6·8·9월 (2025-2026) + 10월 안전 여유
- **동작**: `evaluation/_state.py`의 `_is_in_season()` 함수가 매 판정마다 `ref_utc.month`를 `season_months` 리스트와 대조 → 11월~4월 자동 `OUT_OF_SEASON` 판정 (수동 개입 불필요)

### 갱신된 남은 미결 항목

| 항목 | 분류 | 비고 |
|---|---|---|
| `stale_threshold_hours.dissolved_oxygen` | A2 운영 조정 | 픽스처 분석: 정선 조사 51일 간격 (단일 데이터). 다년도 집계 후 결정 |
| R1 하구 예외 정점 목록 | 계획서 11절 | 현재 픽스처 오탐 없음. 실운영 데이터로 재확인 |
| R4 태풍 특보 원천 | 계획서 4.6절 | B안(ConfigMap `typhoon_active` 수동 토글) 권장. 계획서 개정 필요 |
| `farm_reading_history` 보존 기간 | DB 협의 | — |

---

*갱신: 2026-09-30 미결 조사·A3 채택·season_months 자동화 반영*

---

## 2026-09-30 세션 (남은 미결 처리 — DO 임시값·typhoon_active·A4 정리)

### 처리 내용

| 항목 | 결정 | 변경 파일 |
|---|---|---|
| `stale_threshold_hours.dissolved_oxygen` | `1224h` (51일) 임시 채택. 픽스처 유일 관측 간격 51일 기반. 다년도 집계 후 재결정 | `config/operational.initial.yaml` |
| `typhoon_active` | 운영 조정 `false` 초기값. 운영자 수동 토글 방식. collector 완성 시 자동화 가능 | `contracts/config/operational.schema.json`, `config/operational.initial.yaml`, `processor/quality/_rules.py`, `tests/unit/test_quality.py` |
| R1 하구 예외 정점 | 픽스처 내 오탐 없음. I-11 실측 시 확인 예정 | 코드 변경 없음 |

### `typhoon_active` 구현 상세

- `operational.schema.json`: 최상위 `properties`에 `typhoon_active: boolean` 추가 (optional, `required` 미포함)
- `operational.initial.yaml`: `typhoon_active: false` 추가
- `_rules.py`: `_TYPHOON_ACTIVE` 모듈 변수 제거. `apply_quality(operational=...)` 파라미터로 읽기. `_r4_rapid_change(typhoon_active=False)` 파라미터 추가
- `test_quality.py`: `_rules._TYPHOON_ACTIVE = True` → `operational={"typhoon_active": True}` 파라미터 주입 방식으로 교체

### 남은 미결 항목 (이 세션 기준)

| 항목 | 분류 | 비고 |
|---|---|---|
| `stale_threshold_hours.dissolved_oxygen` 재결정 | A2 운영 조정 (임시값 사용 중) | 다년도 DO 집계 후 재결정 |
| R1 하구 예외 정점 목록 | 계획서 11절 | I-11 실측 시 확인 |
| R4 태풍 collector | 미래 작업 | 기상청 API collector 완성 시 자동 연결 |
| `farm_reading_history` 보존 기간 | DB 협의 | — |

---

*갱신: 2026-09-30 DO 임시값·typhoon_active 운영 조정 처리*

---

## 2026-09-30 세션 (I-11 — 실수집 확인·인계물 작성)

### 코드 수정

| 파일 | 변경 요약 | 계획서 반영 후보 |
|---|---|---|
| `common/config/_env.py` — `get_key()` | `urllib.parse.unquote()` 추가. 포털에서 복사한 URL-encoded 인증키(`%XX` 형태)를 자동 디코딩. 원문이면 no-op. 근본 해결: httpx `params=`가 `%` → `%25` 이중 인코딩하는 버그 방지 | — |
| `common/http/_client.py` | `httpx.Timeout` 시그니처 수정 (버전 호환). `_mask_key()` URL-encoded 형태 마스킹 추가 | — |
| `ci/gate/run_gate.py` | `--warn-pending` `default=True` → `default=False` 버그 수정. 이전에는 항상 경고 모드 | — |
| `config/operational.initial.yaml` | 주석 `<미결>` 문자열 제거 — 게이트 원문 검색 오탐 해소 | — |

### 수정 분류: 계획서 반영 후보

| 항목 | 현황 |
|---|---|
| `get_key()` URL-decode — 포털 복사 키 자동 처리 | 계획서에 명시 없음. 실운영 필수. I-11 결과보고서에 기록 |

### handoff 산출물

| 산출물 | 계획서 근거 |
|---|---|
| `handoff/k8s/*.yaml` 12종 | 2.0.2절 매니페스트 초기본 |
| `handoff/observability/metrics.yaml` | 7.7절 운영 지표 |
| `handoff/HANDOFF.md` | A.6 I-11 인계물 |

### F11 테스트 수정

`tests/unit/test_tide_processor.py` — `IDW_OUTPUT_DIR` 게이트 F11 두 케이스:

| 항목 | 변경 전 | 변경 후 |
|---|---|---|
| BOM | `utf-8` | `utf-8-sig` |
| station_id | `"tide:DT_XXXX"` | `"DT_XXXX"` |
| 값 접근 | wide(`water_temp`/`salinity` 컬럼) | long(`metric`/`value` 컬럼) |
| 시각 컬럼 | `observed_at_utc` | `observed_at` |

### F11 수동 실행 결과

| 케이스 | 결과 | 비고 |
|---|---|---|
| F11-1: DT_0049·DT_0092 STATION_INACTIVE | **통과** | 전 행 water_temp·salinity = 0.0 결측 확인 |
| F11-2: DT_0061 연속 결측 ≥ 518분 | **실패** | 현재 observations.csv 최장 27분. 데이터 갱신 추정 |

F11-2 임계(518분)는 현재 `$SRC_IDW/output/observations.csv` 데이터와 불일치. **결정 대기**: 임계 낮추기(27분) / 테스트 제거 / 구 CSV 복원.

### 남은 미결 항목 (이 세션 기준)

| 항목 | 분류 | 비고 |
|---|---|---|
| `stale_threshold_hours.dissolved_oxygen` 재결정 | A2 운영 조정 임시값 | 다년도 DO 집계 후 재결정 |
| F11-2 DT_0061 임계 불일치 | 테스트 | 사용자 결정 대기 |
| R4 태풍 collector | 미래 작업 | 기상청 API 완성 시 |
| `farm_reading_history` 보존 기간 | DB 협의 | — |

---

*갱신: 2026-09-30 I-11 실수집 확인·get_key() 수정·F11 테스트 수정*

---

## 2026-10-01 세션 (F11-2 B안·F12/P9 공식화·A3 확정·replay/pipeline 테스트)

### F11-2 재구현 (B안 확정)

| 항목 | 변경 전 | 변경 후 |
|---|---|---|
| 임계 수치 | 518분 (`zero_by_station.py` 측정값) | 180분 (`stale_threshold_hours.salinity_tide` — 운영 조정) |
| 측정 방식 | `zero_start → next_nonzero` 구간 | 연속 정상(비0·비결측)값 사이 최대 간격 (`max_gap_min`) |
| 판정 근거 | 단순 구간 추출 — STALE 로직과 불일치 | `determine_state()` STALE 판정이 보는 신선도 간격과 동일 |

**DT_0061 확인된 이상 관측:**

| 구간 | 길이 | 추정 원인 |
|---|---|---|
| 2026-07-05 04:13 → 12:51 | 518분 | 0값 1개 후 관측 중단 — 센서 교체 추정 |
| 2026-08-01 23:59 → 08-04 00:00 | 2881분(~48h) | 장기 점검 또는 통신 장애 추정 |

두 이벤트 모두 stale_threshold(180분) 충분히 초과 — STALE 시나리오 픽스처 존재 확인.

### A3 시드 확정 (2026-10-01)

| 파일 | 헤더 변경 |
|---|---|
| `seeds/areas.yaml` | "사용자 채택 2026-09-30" → "확정 2026-10-01" |
| `seeds/area_aliases.yaml` | 동일 |
| `seeds/axis_coverage.yaml` | 동일 |

`tests/db/test_seeds.py` 5개 추가 (Docker 기반 PostgreSQL 16 testcontainer): areas=8, area_aliases=15, axis_coverage=8(모두 red_tide), upsert 멱등성 검증. 28 passed.

### F12/P9 pytest 공식화 (`tests/pipeline/test_f12_p9.py`)

| 테스트 | 내용 | 결과 |
|---|---|---|
| `test_f12_water_temp_p95` | P95 = 2.4906, 목표 2.48 ±0.05 | **PASS** |
| `test_f12_sample_count` | n=179,289 >= 100,000 | **PASS** |
| `test_p9_nearest_removal_increases_error` | 제거 후 P95 2.5758 >= 전체 2.4906 (제거 정점: DT_0016, 10.18 km) | **PASS** |

실행: IDW_OUTPUT_DIR = `$SRC_IDW/output` 설정 후 `python -m pytest tests/pipeline/ -v` (88초).

### `tests/replay/test_tide_observations.py` 구현 및 실행

`observations.csv`가 IDW 보간 입력 전용(water_temp·salinity만)임을 확인 — tide_level·wind_speed·air_temp는 DB 적재 경로.

| 테스트 | 결과 |
|---|---|
| `test_all_tide_stations_present` (9개 정점 전체) | **PASS** |
| `test_all_metrics_per_station` (water_temp·salinity × 정점) | **PASS** |
| `test_minimum_observation_count` (>= 1,000행/정점-지표) | **PASS** |
| `test_value_range[water_temp]` (−2.0~40.0) | **PASS** |
| `test_value_range[salinity]` (0.0~40.0) | **PASS** |
| `test_date_coverage_at_least_30_days` | **PASS** |

실행: IDW_OUTPUT_DIR 설정 후 `python -m pytest tests/replay/ -v` (19초).

### DASHBOARD_HANDOFF.md 작성

대시보드 팀 공유용. 읽어야 할 테이블 8종·쓰지 말아야 할 테이블 13종·단계 간 알림 계약(queue-v1)·축 상태 17종·필드 의미 W1~W8·미결 항목 4종.

### 새 계획서 반영 후보

| 항목 | 내용 | 상태 |
|---|---|---|
| `observations.csv` 지표 범위 명시 | IDW 보간 입력 파일은 water_temp·salinity만 포함. tide_level·wind_speed·air_temp는 DB 적재 경로. 계획서 6.2절(검증 폴더 정의)에 포함 여부 검토 | 반영 (개정 10 — 6.2절) |

### 테스트 현황 (2026-10-01 기준)

- 일반 단위 + DB(Docker): 336 passed, 4 skipped (F11 2개 IDW_OUTPUT_DIR 미설정)
- replay(IDW_OUTPUT_DIR 설정 시): 6 passed
- pipeline(IDW_OUTPUT_DIR 설정 시): 3 passed (88초)
- 게이트: 통과 (경고 없음)

---

*갱신: 2026-10-01 F11-2 B안·F12/P9 공식화·A3 확정·tests/replay·tests/pipeline*

---

## 2026-10-01 계획서 개정 11 (점검 후 정정·채택값 흡수)

근거: `docs/reports/review_20261001_rev10.md` (개정 10 직후 로컬 전반 점검). 계획서·skill 8종·이 파일·`미정값_목록_20260930.md`·`handoff/HANDOFF.md`를 같은 작업에서 갱신. `CLAUDE.md`는 값·미결 목록을 담지 않아 변경 없음.

### 개정 10 정정

| 항목 | 개정 10 | 개정 11 |
|---|---|---|
| `grading.estuary_stations` 의미 | R1 하구 예외 정점 목록(4.6절), 값 4.6절 `[DT_0016]` / 7.7절 `[]` | 2026-09-30 채택 의미로 정정 — `salinity_mode = NEAREST_TIDE`에서 염분 영역 판정을 `NONE`(`EXCLUDED_ZONE`)으로 돌릴 하구 영향 **조위관측소**(4.8절). 값 `[DT_0016]`(7.7절 일치). 대조는 `tide:` 접두어를 뗀 코드로 |
| R1 하구 예외 정점 목록 | `grading.estuary_stations` | **미결로 되돌림**(4.6·11절) — 정선·어장환경 정점 목록, 별도 키 미정 |
| 산양읍 별칭 | 본문 "채택" + *(제안)* | *(제안)* 제거 — 적조 해역 시드 2026-10-01 확정 |

### 채택값 흡수 (계획서에 값으로 기록)

| 구분 | 키 | 계획서 위치 |
|---|---|---|
| 판정 정의 | `bulletin.current_window_days: 3`, `line.surface_rule: INCLUDE`, `interpolation.exclude_flatline: true`, `interpolation.error_window_days: 30`, `grading.salinity_mode: NEAREST_TIDE`, `grading.estuary_stations: [DT_0016]`, `grading.line_max_distance_km: 30`, `grading.fishery_max_distance_km: 10`, `grading.excluded_zones: seomjin_estuary` | 4.4·4.7·4.8절, 7.7절 settings, 11절 |
| 운영 조정 | `tide.flatline_minutes: 30`, `stale_threshold_hours.salinity_tide/tide_level/wind_speed/air_temp: 3`, `dissolved_oxygen: 1224`(임시), `evaluation.*_stale_minutes: 60`, `typhoon_active: false` | 2.0.6절(키 등록), 4.6·4.9절, 7.7절 운영 조정 블록, 11절 |
| 시드 | 적조 해역 시드 3종 확정, `season_months: [5..10]` | 4.3·11절 |
| 검증 | F11 `DT_0061` 기대값을 `salinity_tide` 임계 상대로(B안), counts `coord_excluded: 1029` | 7.1·7.7절 |
| 진행도 | S1~S12 `보고 검토` (I-0 보고서 없음, 점검 결함으로 `완료` 보류) | 10절 |

### 남은 계획서 반영 후보 (미흡수)

| 항목 | 내용 | 상태 |
|---|---|---|
| R1 하구 예외 목록의 키·값 | 정선·어장환경 정점. I-11 실측 재확인 | 키 반영 (개정 13 — `quality.r1_estuary_stations: <미결>`), 값은 대기 |
| R4 태풍 특보 자동 입력 원천 | 기상청 특보 API 등 — 채택 시 모듈 범위 확장 | 대기 |
| `typhoon_active` 스키마 필수 여부 | 스키마는 optional(`required` 미포함) — 2.0.6절 "키 집합 고정(누락 실패)"과 어긋남 | 반영 (개정 13 — 필수 키) |
| `get_key()` URL 디코딩 | 포털 복사 키(`%XX`) 자동 디코딩 — 계획서 3.1절 명시 검토 | 반영 (개정 13 — 3.1절) |
| `obs_dtm` KST 근거 | 1.4절 근거가 IDW 재검증 — sooList 원문 대조 근거 보강 검토 | 반영 (개정 13 — 간접 증거 둘, `SOURCES.md` ③ 무효 정정) |
| 게시 감시 `prev_count=None` · chlorophyll R0 · `interpolation_weights.obs_value` · `B2` 승격 | 위 각 절 | 대기 (변동 없음) |

### 코드 결함 (점검 1절 — 계획서 개정 대상 아님, 미처리)

A1 processor 품질 규칙 미연결 · A2 processor 적재 미연결 · A3 R2 키 `max`/`value` · A4 `estuary_stations` 접두어 대조 · A5 CI 선택 빌드 경로 · A6 운영 조정 누락 시 기본값 진행 · A7 `axis_coverage` 선언 없음 처리 · A8 interpolation 기본값 대체 · A9 R1 예외 하드코딩

---

*갱신: 2026-10-01 계획서 개정 11*

---

## 2026-10-01 코드 수정 (점검 A1~A9)

결과: `docs/reports/review_20261001_rev10.md` "권장 순서 3". A1·A3·A4·A5·A6·A8 해결, A7 결함 아님(문서 오기), A9 유지(미결), A2 보류.

### 구현한 *(제안)* 항목

| 항목 | 내용 | 상태 |
|---|---|---|
| R4 "1시간 전" 관측 창 | `[t−60분−15.4분, t−60분]`의 같은 관측소 마지막 유효 수온 — 15.4분은 관측소 최장 갱신 간격(4.7절 근거). 계획서 4.6절에 정의 없음 | 반영 (개정 13 — 판정 정의 `quality.r4_lookback_tolerance_min`) |
| R2·R4 직전 값 탐색 범위 | 같은 수집(원문) 안에서만 찾는다. 앞 수집과의 비교는 DB 읽기(A2) 이후 | 반영 (개정 13 — 같은 수집 → 적재된 DB, 구현은 I-12 이후) |

### 새 계획서 반영 후보

| 항목 | 내용 | 상태 |
|---|---|---|
| collector·processor DB 적재 연결 (A2) | 운영 코드의 테이블 쓰기 호출처 0 — 지시서 단위 작업 필요 | 대기 |
| 원문 ID 형식 | `raw_store` 객체 키(문자열) vs `ingest_runs.raw_id`·관측 `raw_id`(BigInteger, `raw_index.id`) — 2.2·2.3·5.3절 | 대기 |
| `survey_observations.flags` 열 | 어장환경 R1·R2 `SENSOR_QUALITY` 저장 위치 없음 — 5.3절 | 대기 |
| `adapter_health.retry_recovered` 타입 | 테이블 Boolean vs Q6 "1 증가" — 5.3·7.8절 | 대기 |
| `obs.loaded` payload | `source`는 수집 원천, `topic` 필수 — 계약 `queue-v1`대로 수정함. 2.2절 예시에 `topic` 명시 검토 | 대기 |

---

*갱신: 2026-10-01 코드 수정 (A1~A9)*

---

## 2026-10-01 A2 원인 확인 · 지시서 I-12 작성

- 통합계획서 v1.5(`docs/plan/AquaSentinel_통합계획서_v1_5.md`) 12.1절(C안)·13절(데이터 모델 스케치, "2주차 스택 확정 후 반영")에 A2 쟁점의 답 없음
- 원인은 v1.5가 아니라 **제작계획서 내부 배정 누락** — 10절 "DB 적재는 S7에서 붙인다" vs A.6 I-6 산출물(`common/repository/`·DDL만). 적재 변환 코드는 `tests/db/test_counts.py`에만 있었다
- 지시서 초안 `docs/instructions/I-12_DB적재연결.md` — 전달 전 계획서 개정 12(A.6 행 추가 + 결정 D1~D6) 필요

| 결정 | 내용 | 상태 |
|---|---|---|
| D1 | `raw_index` 작성 주체 · `raw.fetched.raw_id` 의미 (권고: processor가 작성, raw_id = 객체 키) | 반영 (개정 12 — 2026-10-01 사용자 허가) |
| D2 | `raw_index.api`·`adapter_health.adapter` 값 (권고: api_id / 수집 원천) — evaluation 조회와 지금 불일치 | 반영 (개정 12 — 2026-10-01 사용자 허가) |
| D3 | `survey_observations.flags` 추가 (권고) | 반영 (개정 12 — 2026-10-01 사용자 허가) |
| D4 | `adapter_health.retry_recovered` Integer (권고) | 반영 (개정 12 — 2026-10-01 사용자 허가) |
| D5 | `stations` 마스터 작성 주체 (권고: processor가 원문 좌표로) | 반영 (개정 12 — 2026-10-01 사용자 허가) |
| D6 | `ingest_runs.status` = 응답 상태 (권고) | 반영 (개정 12 — 2026-10-01 사용자 허가) |

---

*갱신: 2026-10-01 A2 원인 확인 · I-12 초안*

---

## 2026-10-01 계획서 개정 13 (P1·P2·P3·후보 4건 — 사용자 수락)

| 항목 | 반영 |
|---|---|
| P1 R4 "1시간 전" | 4.6절 정의 + 판정 정의 `quality.r4_lookback_tolerance_min: 15.4`(`definitions.yaml`·`expected.yaml` 같은 커밋), 7.8 Q2 창 밖 사례. `_rules.py`가 키를 읽고, 없으면 R4 미판정 |
| P2 R2·R4 직전 값 범위 | 4.6절 "같은 수집 → 적재된 DB", 11절 행 추가. **구현은 I-12 이후 후속 지시서** |
| P3 `SOURCES.md` `lot` 기록 | I-12 지시서 산출물·작업에 정정 포함 |
| R1 하구 예외 키 | 판정 정의 `quality.r1_estuary_stations: <미결>` — 게이트 `--warn-pending` 경고 1건. `_rules.py` 하드코딩 빈 집합 제거(미결이면 예외 없음) |
| `typhoon_active` 필수 | `operational.schema.json` `required` 추가, 2.0.6절. 테스트 추가 |
| 키 URL 디코딩 | 3.1절 기록 |
| `obs_dtm` KST 근거 | 1.4절 간접 증거 둘로 정정, `SOURCES.md` 증거 ③ 무효 표시 |

검사: `pytest` 370 passed / 13 skipped, 게이트(`--warn-pending`) 통과 — 경고 `quality.r1_estuary_stations` 1건(플래그 없이 돌리면 이 항목으로 실패), `scan_keys` 0건.

---

*갱신: 2026-10-01 계획서 개정 13*

---

## 2026-10-01 I-12 실행 (DB 적재 연결)

결과: `docs/reports/I-12_result.md`. `pytest` 387 passed / 13 skipped / 5 xfailed. 판별력 점검 — 적재를 끊으면 신설 검사 13/14 실패.

### 새 계획서 반영 후보

| 항목 | 내용 | 상태 |
|---|---|---|
| 어장환경 원문 완전 중복 | 연도마다 8건(`임원`) — PK 적재 1000·1012·1014 vs `expected.yaml` stored 1008·1020·1022. 7.7절 counts 기준 구분 필요 | 반영 (개정 14 — 합침 유지, 기준 `loaded` 추가) |
| `bulletin_details` `min/max_watertemp` | 5.3절에 열 없음 — `LOAD_COLUMNS_DROPPED`로 기록 중 | 대기 |
| HTTP 타임아웃 → `NET_ERROR` | 3.2절 명시 *(제안)* | 대기 |
| 재시도 후 성공 → `retry_recovered` +1 | 4.9절 *(제안)* | 대기 |
| 검토 큐 `OUT_OF_SCOPE` 판별 규칙 | 4.3절 — 현재 전부 `PARSE_FAILED` | 대기 |
| R2·R4 DB 조회 메서드 | `get_observations_in_window`, `get_previous_survey` 제안 — 후속 지시서 | 대기 |
| 다른 단계 결함 | grading `grade.done`(axis·schema·topic), grading·interpolation `env.database_url` → **해결됨**(2026-10-01). 남은 것: evaluation `farm_sites.area_id`(계약에 열 없음 — 1.6·5.3절), processor `reprocess` 범위 인자 ↔ 매니페스트, 컨슈머 큐 구현(MemoryQueue), `*-completeness` 소비자 없음, collector(다중 페이지 재구성·감시 payload·직전 건수 stub·05 재시도·precheck_code) | 일부 해결 |

---

*갱신: 2026-10-01 I-12 실행*

---

## 2026-10-01 계획서 개정 14 (어장환경 조사 시각 키 — B안, 사용자 결정)

| 항목 | 반영 |
|---|---|
| 조사 시각 | `TIME_H`·`TIME_I` **KST 확정**(사용자). `survey_observations` PK = (정점·`observed_at_utc`·층·항목), `surveyed_on`은 조회용 (1.5·4.5·5.3절) |
| R2 직전 | 조사 시각 기준 (4.6절) |
| 클로로필 현재값 | 최신 = 조사 시각 기준, `farm_readings.observed_at_utc` = 조사 시각 (4.8절) |
| `source_ref` | DO·클로로필 = `station_id@observed_at_utc` — 결과 테이블 계약 **`tables-v2`**(`definitions.yaml`·`expected.yaml` 같은 커밋, `DASHBOARD_HANDOFF.md`·`dashboard_contract.md` 변경 공지). DO는 코드가 이미 관측 시각을 쓰고 있었다 — 계획서가 코드에 맞춰졌다 |
| 기준 문서 | `femo_*`에 `loaded` 추가 (7.7절) |
| `CLAUDE.md` | 6절 `source_ref` 정의 갱신 (계획서 개정과 같은 작업) |

검사: `pytest` 401 passed / 13 skipped / 1 xfailed, 게이트 통과, `scan_keys` 0건.

---

*갱신: 2026-10-01 계획서 개정 14*

---

## 2026-10-01 L6 결함 수정

| 항목 | 상태 |
|---|---|
| grading `grade.done` 축별 발행·`schema`·`topic` | 해결됨 |
| grading·interpolation·processor DB 연결 — `common.config.database_url()` | 해결됨 |
| 진입점이 매니페스트 명령 수용(evaluation 컨슈머·`sweep`, interpolation `error`, processor 컨슈머) | 해결됨 |
| `farm_sites.area_id` 계약 부재 | 반영 (개정 15 — 모듈이 정해 `farm_areas`로 알림) |
| `reprocess` 범위 인자 | 반영 (개정 15 — `raw_index.id` 범위) |

검사: `pytest` 412 passed / 13 skipped / 0 xfailed.

---

*갱신: 2026-10-01 L6 결함 수정*

---

## 2026-10-01 계획서 개정 15 (양식장 해역·재처리 범위·큐 — 사용자 결정)

| 항목 | 결정·반영 |
|---|---|
| 양식장 해역 | 모듈이 정해 알린다 — 어업자가 해역 경계를 가질 수 없고 구역마다 모양이 다르며, 원천이 IoT 실측이 아니라 근사로 충분(사용자). 규칙 반경 안 해역 중 중심 최근접 1개(같으면 `area_id` 순). `common/farm_sites/assign_area`, 결과 테이블 **`farm_areas`**(`tables-v2`에 포함), evaluation이 판정 때마다 기록하고 커버리지·계절 선언에 쓴다. `farm_sites.area_id`는 읽지 않는다 (1.6·4.9·5.3·5.5절, `CLAUDE.md` 6절, skill 3종, `DASHBOARD_HANDOFF.md` §1-9) |
| `reprocess` | 원문 ID = `raw_index.id` 범위 `--raw-id-from`·`--raw-id-to`(양끝 포함) — 매니페스트와 일치. 파서 버전을 올린 이미지로 (2.1절, `HANDOFF.md`) |
| 큐 | 미결 유지 — 인프라 리전 동작 시험 후 붙이고, 그 전에는 앱 안(`MemoryQueue`) 전달로 시험 (11절) |

검사: `pytest` 419 passed / 13 skipped, 게이트 통과, `scan_keys` 0건. 신설: `tests/unit/test_farm_area.py`, DB — 해역 기록·계절 밖 판정, 범위 재처리.

---

*갱신: 2026-10-01 계획서 개정 15*

---

## 2026-10-01 연결 결함 원인 추론 · 수정 · 계획서 개정 16

**원인 추론**: 부품 단위 검증(7.1~7.8 — 함수·어댑터에 입력을 직접 넣음)만 있고 부품을 잇는 부분은 어떤 검사도 실행하지 않았다. 사용자 가설("테스트 안에서 진행하고 모듈로 안 옮김")은 DB 적재(변환이 `tests/db/test_counts.py`에만)·Q6(테스트 안 가짜 클래스)에 그대로 맞고, 나머지(진입점·이름·알림 필드·분할 합산)는 "부품만 검증, 연결은 담당 없음"이다. 분할 합산은 원문 여럿을 모아야 해서 원문 하나 처리 구조와 맞지 않는 **설계 공백**이다.

| 항목 | 상태 |
|---|---|
| collector 진입점 — 워크로드 이름(매니페스트) 해석, 어댑터 import, `__main__` 레지스트리 분리 | 해결됨 |
| `collector.fishery_watch` 실행 블록 없음 | 해결됨 |
| collector 호출 실패 원문 폐기(2.3절 위반 → `OUTAGE` 판정 불가) | 해결됨 — 저장·발행 |
| 감시 `raw.fetched` 계약 밖 키 | 해결됨 — 대상 연도·직전 건수는 processor가 tag·DB로 |
| 7.9 연결 검사 E1~E6 | 반영 (개정 16) — `tests/unit/test_wiring.py`(9), `tests/db/test_collector_e2e.py`(8) |
| 분할 합산 비교 처리 경로 | **해결됨** — 개정 17(완료 알림 + 독립 검사기), 구현·E7 통과 |
| collector 남은 것 | 대기 — tide 다중 페이지 재구성 본문, 직전 감시 건수 stub, `05` 재시도 = HTTP 타임아웃, `precheck_code` 미기록 |

검사: `pytest` 436 passed / 13 skipped, 게이트 통과, `scan_keys` 0건.

---

*갱신: 2026-10-01 계획서 개정 16*

---

## 2026-10-01 계획서 개정 17 — 분할 합산 처리 경로 (설계 검수 5회 → PASS, 구현)

**설계 경과**: 1~3차 검수 FAIL은 모두 "원문마다 processor가 중간 상태(도착 수)를 써서 마지막 원문이 판정"하는 구조의 경합(키 충돌·늦은 쓰기·`ABANDONED`). 사용자 제안(collector 완료 알림 → 독립 검사기)으로 중간 상태를 없애 경합을 근본에서 제거. 4차 FAIL(분할 호출을 `adapter_health`에 넣어 적조 신선도·원인 분류가 깨짐) 수정 후 5차 PASS. 처리 단계를 판정 뒤로 미루는 안은 검토 후 제외(주기 불일치·장애 전파·판정값 쓸 곳 없음).

| 결정 (사용자 수락) | 내용 |
|---|---|
| 수집 | 같은 실행에서 단일 창 먼저 + 월 분할, 창 끝 = KST 어제(워크로드 시작 때 고정), 다 받으면 `completeness.collected`(받은 목록만) |
| 정선 1년 창 | 작년 같은 날(없으면 2/28) ~ 끝, 양끝 포함(366일) — IDW 기준 데이터와 같음. 권고 C(365일) 철회 |
| 어장환경 창 | 어제가 속한 해 1월 1일 ~ 어제 |
| 검사기 | `processor.main completeness-check`, KEDA 밖 1대, 원문 저장소 직접 읽음 |
| 판정 | `INVALID`(PART_STATUS·FILTER_IGNORED·WINDOW_MISMATCH·RAW_MISSING) / 빈틈·겹침 → RANGE_MISMATCH / **양방향** INCOMPLETE(`truncated_side`) |
| 기록 | `completeness_checks` 한 행, 같은 결과면 안 씀, RAW_MISSING은 판정 행을 덮지 않음, 이벤트는 같은 트랜잭션·지표는 커밋 뒤 |
| processor | **분할 원문을 받지 않는다**(개정 17 보완) — collector가 `raw.fetched`를 내지 않고 검사기만 원문 저장소에서 읽는다. `raw_index`·`ingest_runs`·`adapter_health`·관측 테이블 어디에도 없음 |
| evaluation | 최근 결과·산출 지연 기준 = 정기 경로 api 명시 목록 |
| 계약 | `queue-v1`에 새 주제(같은 버전 — 2.2절 규칙 신설), `completeness_checks`는 결과 계약 밖, processor만 기동 검사 |

**함께 고친 기존 결함**: evaluation 원인 분류가 `result_code`로 응답 상태 표를 찾음(`_state.py`) → `status`로 / MySQL "있으면 그대로" 업서트가 일반 INSERT(`dialect.py`) → 무변경 ON DUPLICATE KEY / 수집 창의 오늘이 컨테이너 시각(`date.today()`) → KST.

| 남은 것 | 상태 |
|---|---|
| 분할 합산 결과를 축 상태에 반영하지 않음 | *(제안)* — 채택 대기 |
| 적조 14일 창은 대개 월 분할 1개(단일 창과 같은 범위) — 비교가 같은 요청 두 번의 대조가 됨 | 계획서 반영 후보 |
| 검사기 매니페스트·큐 주제·`completeness_checks` DB 적용 | 인프라·DB 소유 측 요청(`HANDOFF.md`) |
| MySQL 분기 실행 검증 | 고른 DB가 PostgreSQL이라 미검증(7.4 선택 검사) |
| collector 남은 결함 — tide 다중 페이지 재구성 본문, 직전 감시 건수 stub, `05` 재시도 = HTTP 타임아웃, `precheck_code` 미기록 | 대기 |

검사: `pytest` 461 passed / 13 skipped, 게이트 통과, `scan_keys` 0건. 신설 검사 — `tests/db/test_completeness_e2e.py`(E7, 10), `tests/unit/test_clock.py`(6), `test_completeness.py` 빈틈·겹침·양방향(+8), `test_wiring.py`(+2).

---

### 개정 17 보완 (2026-10-01, 사용자 결정 · 검수 PASS 후 구현)

processor 경유는 `adapter_health` 갱신용이었고 4차 검수에서 그것을 뺀 뒤 `raw_index`·`ingest_runs` 행을 쓰는 곳이 없었다 → 분할 원문의 `raw.fetched` 발행 제거.

| 바뀐 곳 | 내용 |
|---|---|
| 코드 | `collector/_completeness.py` 발행 제거(저장 + 완료 알림만), `processor/main.py`·`_load.py`의 분할 원문 분기 제거 |
| 문서 | 계획서 2.1·2.2·2.3·3.3(다시 판정 행 *(제안)*)·4.9·5.3·7.9 E2/E7·11절(원문 보존 기준 — 색인 없는 분할 원문), skill common-core·bulletin·line·repository, `HANDOFF.md` |
| 검사 | E7 첫 검사 = `raw.fetched` 0건·`raw_index`·`ingest_runs`·`adapter_health` 0행, collector E2E 분할 검사 교체, E2 배선 검사에서 `is_completeness` 허용 제거 |

| 남은 것 | 상태 |
|---|---|
| 다시 판정 경로 — 같은 `completeness.collected` 재발행(수동) | *(제안)* — 채택 대기 |
| 원문 보존·정리 기준에 색인 없는 분할 원문 포함 | 11절 미결 — 팀·인프라 |

검사: `pytest` 461 passed / 13 skipped(환경 의존 기존 skip), 게이트 통과, `scan_keys` 0건.

---

### 개정 18 (2026-10-02, 사용자 결정 · I-13 근거) — 적조 수집 창·절단 감시 재설계

근거: `docs/reports/I-13_result.md` — `redtideList` 실호출 7회(지시서 I-13 머리말 허용) + 명세 PDF 대조. `sdate`/`edate`는 `day_report`(조사일시)로 거르고, 등록일(`cod_news`, 속보코드)로 거르는 변수는 없다(명세 밖 `cod_news`는 무시, 날짜 없으면 `04`).

| # | 결정 | 반영 |
|---|---|---|
| 1 | 다시 판정 = `completeness.collected` 손 재발행 — 지금 구현 사용, 큐 확정 등 변경 시 재정의 | 3.3 "다시 판정" *(제안)* → 확정 |
| 2 | 원문 보존 정책에 키 접두 기준 포함 — 방향만, 기간 미결 | 11절 |
| 3 | 분할 합산 결과를 축 상태에 반영하지 않음 | 3.3 "축 상태" *(제안)* → 확정 |
| 4 | 적조를 분할 합산에서 제외 | 2.1·3.3·5.3·7.9 E7·8절, skill bulletin·common-core |
| 5 | 정기 창 14일 → **30일** (관측 최대 등록 지연 14일, `20260526-002`가 14일 창에서 영원히 빠짐) | 1.3·2.1·8절 |
| 6 | 적조 절단 감시 = **직전 원문 대조**(4-A) — 직전 정기 원문의 속보가 이번 창 안인데 빠지면 `BULLETIN_WINDOW_MISSING`, 응답 상태·축 상태 불변 | 3.3·5.3·7.2 N15·N16·9·10(S2)절 |
| 7 | 짧은 창 교차 호출(4-B′) 보류 — 4-A 시험 뒤 결정 | 11절 |

기각: 번호 연속성 검사(4-B) — `day_report`당 1건만 제공(66/66), 같은 날 번호 결번 7일이 정상.

| 남은 것 | 상태 |
|---|---|
| 4-A 구현·시험 | **완료** — 검수 1차 FAIL(8건) → 반영 → 2차 PASS, I-14 실행(`docs/reports/I-14_result.md`, 479 passed) |
| 4-B′ 채택 여부 | 사용자 — 4-A 시험 뒤 |
| 결과 코드 `04` → `BAD_REQUEST` | *(제안)* — 11절 |
| 등록 지연 상한 | 11절 미결 — 지연 분포 지표 *(제안)* |
| `handoff/` 매니페스트 주석·`HANDOFF.md`의 "14일" | **반영** — 인계 전이라 초기본 수정(2026-10-02, 사용자 지시) |

---

### 개정 18 보완 — 점검 후속 (2026-10-02, 사용자 승인)

점검 `docs/reports/review_20261002_rev18.md` 후속. 원문 저장소는 로컬 디스크 구현만 두고 객체 저장소는 인프라 확정 뒤(11절, `RAW_STORE_DSN`이 있으면 기동 멈춤 — D4). Dockerfile 복사 규칙에 운영 조정 스키마·적조 시드(2.0.2절, `CLAUDE.md` 4절 — D5). 코드 수정 C1·D1·D2·D3·D5·C6 — 483 passed, 이미지 4종 빌드 확인.

점검 후속 2차(같은 날, **코드만 — 계획서 변경 없음**, 계획서 규칙을 구현한 것): C3 결과 코드 `05` 재시도(3.1절)·헬스 최종 `TIMEOUT_05` = 실패(4.9절), C7 직전 감시 건수(2.1절)·전량 호출 실패 원문 보관(2.3절), C8 `precheck_code`(2.3절), C12 백필 실패 시 멈춤(4.5·3.1절) — 493 passed. C2(조위 다중 페이지)는 2.3절 *(제안)*과 처리 구조가 맞지 않아 결정 대기 — 결정되면 개정 대상

---

*갱신: 2026-10-02 계획서 개정 18 보완(점검 후속)*


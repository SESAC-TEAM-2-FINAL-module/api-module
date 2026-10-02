# 대시보드 인계 문서 — API 모듈 → 대시보드 계약

**작성일**: 2026-10-01  
**계획서 근거**: 5.5절, 4.9절, 2.2절, 2.0.6절  
**원천 파일**: `contracts/tables/dashboard_contract.md`, `config/definitions.yaml`, `config/operational.initial.yaml`, `seeds/`  

> **역할 구분**: 판정(provenance·오차·침묵 분류 계산)은 이 모듈. 배지·화면 문구·노출·발송 시점은 대시보드.  
> 대시보드는 이 값들을 **다시 계산하지 않는다.**

> **계약 변경 — `tables-v2` (2026-10-01, 계획서 개정 14)**
> - `farm_readings.source_ref`: DO·클로로필이 `station_id@surveyed_on`(날짜) → **`station_id@observed_at_utc`**(조사·관측 시각, UTC ISO `YYYY-MM-DDTHH:MM:SS`)
> - 클로로필 `farm_readings.observed_at_utc`: 비어 있던 값 → **조사 시각**(UTC). 모니터링 시간축에 그대로 쓴다
> - 같은 정점에서 하루에 여러 번 조사하면 각각의 시각으로 남는다(전에는 날짜 하나로 합쳐질 수 있었다)
> - **새 테이블 `farm_areas`**(§1-9) — 양식장 해역을 모듈이 정해 알린다 (개정 15)

---

## 1. 대시보드가 읽는 테이블

### 1-1. `farm_readings` — 양식장별 현재값 ★주 조회 대상

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `farm_id` | VARCHAR(64) | 양식장 ID (PK 구성) |
| `axis` | VARCHAR(64) | 축 이름 → §6 열거형 참조 |
| `value` | DOUBLE PRECISION | 현재값. `NULL` = 정상적 침묵(적조 없음) |
| `lower` / `upper` | DOUBLE PRECISION | **수온 전용**: `value ∓ 오늘의 오차 P95`. 최솟·최댓값 아님 |
| `unit` | VARCHAR(64) | 단위 문자열 |
| `derivation` | VARCHAR(16) | 값 유래 → §6 열거형 참조 |
| `provenance` | VARCHAR(16) | 영역 판정 등급 → §6 열거형 / §3 주의사항 참조 |
| `none_reason` | VARCHAR(64) | `provenance=NONE`일 때 사유 코드. 화면 표시용 아님 |
| `validated_scope` | VARCHAR(64) | `COMPUTED` 값의 검증 범위. `STATION_SITES` = 관측소 위치에서만 교차검증 |
| `grade` | VARCHAR(16) | 적조 4단계 등급 → §6 열거형 / §3 주의사항 참조 |
| `alertable` | BOOLEAN | 발송 자격 — 정적 자격, 신선도 미포함 → §4 W5 참조 |
| `source_ref` | VARCHAR(255) | 근거 원천 키 (운영 확인용, 화면 표시용 아님). DO·클로로필은 `station_id@observed_at_utc`(UTC ISO) — `tables-v2` |
| `distance_km` | DOUBLE PRECISION | 인근 실측 거리 |
| `observed_at_utc` | TIMESTAMP | 관측 시각(UTC naive) |
| `computed_at_utc` | TIMESTAMP | 산출 시각(UTC naive) |

**PK**: `(farm_id, axis)` — 행이 없으면 아직 산출 전.

---

### 1-2. `axis_status` — 양식장별 축 상태 ★신선도·침묵 분류

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `farm_id` | VARCHAR(64) | |
| `axis` | VARCHAR(64) | |
| `state` | VARCHAR(32) | 침묵 분류 17종 → §5 상태 목록 참조 |
| `reason` | VARCHAR(255) | 상태 사유 코드. 화면 문구 아님 — 문구는 대시보드가 정함(W8) |
| `basis_utc` | TIMESTAMP | 판정에 쓴 가장 새 입력의 시각(UTC naive) |
| `last_checked_utc` | TIMESTAMP | 판정 시각(UTC naive). 신선도 한계 판단 기준(W3) |

**PK**: `(farm_id, axis)`.

> **타이밍 주의** (W4): `farm_readings`(grading 적재)와 `axis_status`(evaluation 적재)는 쓰는 시점이 다름.  
> `axis_status.basis_utc < farm_readings.computed_at_utc`이면 상태가 아직 새 값을 반영 전.

---

### 1-3. `farm_reading_history` — 이력

`farm_readings`와 동일 컬럼 구성, 추가 컬럼 `ts_utc` (이력 시각).  
발송 안 된 것 패널·변화 감지용(W7).

---

### 1-4. `bulletins` — 적조 속보 헤더

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `cod_news` | VARCHAR(64) | PK. 속보 ID |
| `day_report` | DATE | 발표일 |
| `grade` | VARCHAR(16) | 속보 최고 등급(세부 행 집계값). `NONE` = 예비특보 미만 |
| `detail_count` | INTEGER | 세부 행 수 |
| `raw_id` | BIGINT | 원문 참조 |

---

### 1-5. `bulletin_details` — 적조 속보 세부 (생물종·해역·밀도·등급)

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `cod_news` | VARCHAR(64) | FK → bulletins |
| `seq` | INTEGER | 세부 행 번호 |
| `nam_biology` | VARCHAR(255) | 원인 생물 학명 |
| `species_class` | VARCHAR(16) | `TARGET`(대상 종) / `NON_TARGET` / `MISSING` |
| `txt_seas_raw` | VARCHAR(255) | 원문 해역명 |
| `txt_seas_key` | VARCHAR(255) | 정규화된 해역 키 |
| `min_density` / `max_density` | DOUBLE PRECISION | 셀 밀도(cells/mL) |
| `grade` | VARCHAR(16) | 세부 행 등급 → §6 열거형 |

---

### 1-6. `bulletin_detail_areas` — 속보 세부 ↔ 해역 매핑

| 컬럼 | 설명 |
|---|---|
| `cod_news`, `seq`, `part_no` | 복합 키 |
| `area_key` | 정규화 해역 키 |
| `area_id` | 매핑된 해역 ID (미매핑이면 NULL) |

> 해역 없는 속보(`bulletins`에만 있고 대응 양식장 없음)의 표시 정책은 대시보드가 정함(W6).

---

### 1-7. `areas` — 해역 정의

| 컬럼 | 설명 |
|---|---|
| `area_id` | PK |
| `name` | 표시용 한글명 |
| `center_lat` / `center_lng` | 중심 좌표(WGS84 십진도) |
| `radius_km` | 판정 반경 |

현재 등록 해역 8개:

| area_id | name | center_lat | center_lng | radius_km |
|---|---|---|---|---|
| gyeongnam_tongyeong | 경남 통영 | 34.845 | 128.435 | 25 |
| gyeongnam_geoje | 경남 거제 | 34.800 | 128.621 | 20 |
| gyeongnam_sacheon | 경남 사천 | 34.915 | 128.075 | 15 |
| gyeongnam_namhae | 경남 남해 | 34.840 | 127.892 | 22 |
| jeonnam_yeosu | 전남 여수 | 34.740 | 127.730 | 20 |
| jeonnam_deukryang | 전남 득량만 | 34.610 | 127.235 | 15 |
| jeonnam_yeoja | 전남 여자만 | 34.680 | 127.520 | 13 |
| jeonnam_goheung | 전남 고흥 | 34.608 | 127.280 | 20 |

---

### 1-8. `axis_coverage` — 해역 × 축 커버리지

| 컬럼 | 설명 |
|---|---|
| `area_id` | 해역 |
| `axis` | 축 |
| `covered` | 커버리지 여부 |
| `season_months` | JSON 정수 배열. `[5,6,7,8,9,10]` = 5~10월만 활성. NULL = 연중 |
| `reason` | `covered=false` 사유 |

현재 `red_tide` 축만 선언됨(8개 해역 모두 `covered=true`, `season_months=[5,6,7,8,9,10]`).  
선언 없는 해역×축 조합은 `axis_status.state = OUT_OF_COVERAGE`로 나타남.

---


### 1-9. `farm_areas` — 양식장 해역 (모듈이 정함) ★개정 15

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `farm_id` | VARCHAR(64) | 양식장 ID (PK) |
| `area_id` | VARCHAR(64) | 모듈이 정한 해역. `NULL` = 반경 안 해역 없음 |
| `distance_km` | DOUBLE PRECISION | 해역 중심까지 거리 |
| `rule` | VARCHAR(64) | 판정 규칙 — `NEAREST_CENTER_WITHIN_RADIUS`(반경 안 해역 중 중심이 가장 가까운 하나) |
| `computed_at_utc` | TIMESTAMP | 판정 시각 |

- 양식장 좌표 계약에는 해역이 없다 — **어업자가 해역을 입력하지 않는다.** 이 모듈이 좌표로 정해 알린다
- 커버리지 밖·계절 밖(`axis_status.state`) 판정에 쓴 해역이 이것이다. 화면에서 "이 양식장의 해역"을 보일 때 이 값을 쓴다
- 적조 속보 대응은 반경 안 해역을 **모두** 쓴다 — 이 열 하나로 적조 해역을 다시 고르지 않는다

## 2. 단계 간 알림 — `result.updated`

이 모듈이 `axis_status` 갱신 후 발행. 대시보드는 이 토픽을 구독해 화면을 갱신한다.

```
topic: result.updated
payload:
  farm_ids: ["farm_a", "farm_b", ...]   # 갱신된 양식장 목록
  axes:     ["water_temp", ...]          # 갱신된 축 목록
  updated_at_utc: "2026-10-01T03:00:00" # 판정 시각 ISO
```

**계약 버전**: `queue-v1` (definitions.yaml `contracts.queue`).  
버전이 다른 알림을 조용히 읽으면 안 됨 — 버전 불일치 시 처리 중단 후 보고.

---

## 3. 필드 의미 주의사항

### `provenance` — 배지가 아니다

| 값 | 의미 |
|---|---|
| `OBSERVED` | 해당 양식장 인근 관측소 직접 실측 |
| `NEAREST` | 가장 가까운 관측소 값 사용 |
| `BASELINE` | 기준선(다년 평균) 사용 |
| `INTERPOLATED` | IDW 공간 추정 |
| `OFFICIAL` | 기관 공식 발표값 |
| `SURVEY` | 조사 측정값 |
| `NONE` | **신뢰 기준 밖** — "값 없음"이 아님. `value`는 저장되어 있을 수 있음 |

- `provenance=NONE` 값은 화면에 표시하지 않는다(W2).  
- 배지(`인근 실측`, `공식 발표` 등)는 `derivation`과 축 조합으로 결정한다(W1). `provenance`에서 끌어내지 않는다.

### `grade` — `provenance.NONE`과 다른 `NONE`

`bulletins.grade` / `bulletin_details.grade` / `farm_readings.grade`의 `NONE`은  
**예비특보 미만(정상)** 의미. `provenance=NONE`(신뢰 기준 밖)과 **완전히 다름**.

### `alertable` — 신선도를 담지 않는다

`alertable=true`는 계산 시점의 정적 자격. 실제 발송 후보는 `axis_status.state`와 조합해 판단 (W5):

```
발송 후보 = alertable=true AND axis_status.state = 'NORMAL'
```

### `lower` / `upper` — 수온 전용 오차 구간

`value ∓ 오늘의 오차 P95`. 수온 외 축에서는 NULL. 최솟·최댓값 아님.

### 시각 필드 — 모두 UTC naive

| 필드 | 의미 |
|---|---|
| `observed_at_utc` | 관측 시각 |
| `computed_at_utc` | grading 산출 시각 |
| `basis_utc` (axis_status) | 판정에 쓴 가장 새 입력의 시각 |
| `last_checked_utc` (axis_status) | 판정(evaluation) 시각 |

KST 변환은 대시보드가 한다(+9h). 저장 형식은 `DATETIME(naive)`, tz 정보 없음.

---

## 4. 대시보드 요구사항 W1–W8

| # | 요구사항 | 근거 |
|---|---|---|
| W1 | 배지는 `derivation` + 축으로 결정. `provenance`에서 끌어내지 않는다. `derivation=COMPUTED`에 `인근 실측`·`공식 발표` 배지 금지 | v1.5 1.4절 |
| W2 | `provenance=NONE` 값은 화면에 표시하지 않는다. 값은 운영 확인용으로 DB에 존재함 | v1.5 4.6.1절 |
| W3 | `axis_status.last_checked_utc`로 신선도 판단. 한계 초과 시 값 대신 "확인 불가"류 표시. 한계값은 대시보드 설정 | v1.5 S3 |
| W4 | `farm_readings`와 `axis_status` 순간 불일치 감안. `axis_status.basis_utc < farm_readings.computed_at_utc`이면 상태가 아직 새 값 반영 전 | 4.9절 |
| W5 | 발송 시점은 대시보드가 정한다. `alertable=true` AND `state=NORMAL`만 발송 후보. 두 판정 조합만, 재계산 없음 | v1.5 8.1절 |
| W6 | 해역 없는 속보(`bulletin_detail_areas.area_id=NULL`) 표시 정책은 대시보드가 정함 | 4.8절 |
| W7 | "발송 안 된 것" 패널 변화 감지는 `farm_reading_history` + `alertable`로 함 | v1.5 S2' |
| W8 | 침묵 분류(`state`)별 화면 문구는 대시보드가 정함. v1.5 4.5절 "화면" 열 참조 | v1.5 4.5절 |

---

## 5. `axis_status.state` 값 17종

| state | 한국어 의미 | 주요 원인 |
|---|---|---|
| `NORMAL` | 정상 | 신선도 임계 안의 최신 값 |
| `NORMAL_SILENCE` | 정상적 침묵 | `OK_EMPTY` / 적조 속보 없음 (호출은 성공) |
| `PUBLICATION_PENDING` | 게시 대기 | 클로로필: publication_checks total_count=0 |
| `NO_MATCH` | 조건 불일치 | 결과 코드 `03` (NO_DATA) |
| `ITEM_SUSPENDED` | 관측 항목 일시 중단 | 결과 코드 `41` |
| `OUT_OF_COVERAGE` | 커버리지 밖 | `axis_coverage.covered=false` 또는 선언 없음 |
| `OUT_OF_SEASON` | 계절 밖 | `axis_coverage.season_months` 밖 월 |
| `VALUE_FROZEN` | 값 멈춤(확인 중) | `STALE_SUSPECT` 플래그 감지 |
| `STALE` | 확인 불가 | 신선도 임계 초과, 원인 미상 |
| `SERVER_TIMEOUT` | 서버 타임아웃 | 결과 코드 `05` 재시도 후 |
| `REQUEST_ERROR` | 요청 오류 | `BAD_REQUEST` / `NO_SERVICE` / `KEY_ERROR` |
| `PARSE_FAILURE` | 파싱 실패 | `PARSE_FAILURE` / `INCOMPLETE` |
| `OUTAGE` | 진짜 장애 | `HTTP_ERROR` / `NET_ERROR` / `QUOTA` |
| `FILTER_IGNORED` | 필터 무시 | `FILTER_IGNORED` |
| `INTERPOLATION_STALE` | 추정 지연 | sweep 판정 — 최신 IDW 추정 후 경과 초과 |
| `GRADING_STALE` | 산출 지연 | sweep 판정 — grading 산출 후 경과 초과 |
| `NOT_USABLE` | 값 사용 불가 | `farm_readings.provenance=NONE` (좌표 이상·제외 구역 등) |

겹칠 때 우선순위: `OUT_OF_COVERAGE` > `OUT_OF_SEASON` > 원천 오류류 > `NOT_USABLE` > `STALE` > `VALUE_FROZEN` > `PUBLICATION_PENDING` > `NORMAL_SILENCE` > `NORMAL`.

---

## 6. 열거형 값 목록

### `axis` (8종)
```
water_temp | salinity | tide_level | wind_speed | air_temp
red_tide | dissolved_oxygen | chlorophyll
```

### `derivation` (4종)
```
COMPUTED   — IDW·기준선 등 계산값
MEASURED   — 인근 관측소 실측
OFFICIAL   — 기관 공식 발표
SURVEY     — 조사 측정값
```

### `provenance` (7종)
```
NONE | OBSERVED | NEAREST | BASELINE | INTERPOLATED | OFFICIAL | SURVEY
```

### `grade` (6종, bulletins 및 farm_readings)
```
NONE          — 예비특보 미만 (정상)
PRE_ADVISORY  — 예비특보
ADVISORY      — 주의보
WARNING       — 경보
NOT_GRADED    — 비대상 종
UNKNOWN       — 원인생물·밀도·세부 행 불명
```

### `species_class` (bulletin_details, 3종)
```
TARGET | NON_TARGET | MISSING
```

---

## 7. 운영 임계 — 현재 설정값

대시보드가 "신선도 경과 기준"을 자체 설정할 때 참고. 이 값은 운영 조정 ConfigMap 소유이며 변경될 수 있음.

| 축 | 신선도 임계 | 비고 |
|---|---|---|
| water_temp | 3h | |
| salinity | 3h (`salinity_tide`) | |
| tide_level | 3h | |
| wind_speed | 3h | |
| air_temp | 3h | |
| red_tide | 72h (`red_tide_bulletin`) | 수집 주기 고려 |
| dissolved_oxygen | 1224h (약 51일) | **임시값** — 다년도 집계 후 재결정 예정 |
| chlorophyll | — | 게시 감시(`PUBLICATION_PENDING`)로 판정, 신선도 임계 없음 |

`tide.flatline_minutes = 30`: 관측값이 30분 이상 동일하면 `STALE_SUSPECT` 플래그.

---

## 8. 대시보드가 읽지 않는 테이블

| 테이블 | 이유 |
|---|---|
| `raw_index` | 원문 저장소 인덱스 — 운영 전용 |
| `ingest_runs` | 수집 실행 이력 — 운영 전용 |
| `ops_events` | 운영 이벤트 로그 |
| `adapter_health` | 어댑터 건강 상태 — 내부 판정용 |
| `observations` | 관측소 원시 데이터 |
| `line_observations` | 정선 관측 원시 데이터 |
| `survey_observations` | 조사 관측 원시 데이터 |
| `interpolation_runs` / `interpolation_weights` | IDW 추정 내부 메타 |
| `interpolation_error` | 오차 이력 — 필드 `lower`/`upper`로 이미 반영됨 |
| `publication_checks` | 게시 감시 내부 — `PUBLICATION_PENDING` 상태로 반영됨 |
| `unmapped_locations` | 미매핑 해역 로그 — 운영 전용 |
| `area_aliases` | 속보 해역명 정규화 내부 매핑 |
| `stations` | 관측소 메타 — 대시보드 직접 참조 불필요 |

---

## 9. 미결 항목 (대시보드 영향)

| 항목 | 현황 | 대시보드 영향 |
|---|---|---|
| `stale_threshold_hours.dissolved_oxygen` | 임시값 1224h. 다년도 DO 집계 후 재결정 | DO 신선도 판정 기준이 바뀔 수 있음 |
| `R1 하구 예외 정점` | `estuary_stations=[DT_0016]` 선언됨, 추가 제외 대상 미확정 | salinity `provenance=NONE` 범위 변동 가능 |
| `R4 태풍 collector 자동화` | `typhoon_active: false` 수동 토글 임시 | 태풍 시 R4 급변 면제 수동 운영 |
| `axis_coverage` 추가 해역 | 현재 red_tide 8개 해역만 선언. 나머지 축 커버리지 미선언 | 미선언 축 = `OUT_OF_COVERAGE` 상태 |

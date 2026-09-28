---
name: fishery
description: "어장환경 해수면(femoSeaList) 수집·가공과 게시 감시 — src/api_module/collector/adapters/fishery/, collector/fishery_watch.py, processor/adapters/fishery/ 를 만들거나 고칠 때 쓴다 (지시서 I-5). 달력 연도 단위 호출, 주 1회 올해 창 건수 감시와 같은 실행 안의 전량 수집(publication_checks), 과거 연도 백필, 분할 수집, DATE_Y/M/D 조립, 도분초 좌표, metric 3종(수온·염분·클로로필)의 표층/저층(layer) 조사값. 게시 대기 판정(evaluation), 양식장별 클로로필 정점 선택(grading) 작업에는 쓰지 않는다."
---

# fishery

국립수산과학원 어장환경 해수면 `femoSeaList`를 수집·가공하고, 올해 조사값이 **게시되었는지** 주 1회 감시한다. 이 원천은 조사가 아니라 **게시**가 드문 축이다. 공용 용어는 `CLAUDE.md` 6절에 있다. 괄호 속 "N절"은 계획서의 절이다.

---

## ① 범위

| 경로 | 이 skill이 만드는 것 |
| --- | --- |
| `collector/fishery_watch.py` | **게시 감시** — 주 1회 올해 창 호출, 원문 저장 요청. `collector-fishery-watch` 명령에 **등록** |
| `collector/adapters/fishery/` | 달력 연도 단위 호출, **과거 연도 백필**(`collector-fishery-backfill`), `collector-completeness`용 **분할 수집** |
| `processor/adapters/fishery/` | 해석된 응답 → `survey_observations` 행, 게시 감시 결과 → `publication_checks` 행. `processor/main.py`에 **등록** |

**만들지 않는 것**

- 호출층·응답 해석·원문 저장·분할 합산 **비교**·도분초 변환과 좌표 검증 함수·품질 규칙 구현 → `common-core`
- **게시 대기 판정**(`PUBLICATION_PENDING`) → `evaluation`. 이 skill은 `publication_checks`에 **기록만** 한다
- 양식장별 클로로필 정점 선택(거리 한계 `grading.fishery_max_distance_km`), 조사 기준 추정 계산 스위치(`grading.chlorophyll_estimate_enabled`) → `grading`

---

## ② 원천 절 (계획서)

1.1(`femoSeaList` 행) · 1.5 · 2.1(`collector-fishery-watch`·`collector-fishery-backfill`·`collector-completeness`, 사전 읽기 범위) · 3.3(분할 합산) · 4.5 · 4.6(fishery 적용 규칙) · 5.3(`survey_observations`·`publication_checks`) · 6.3(fishery 행) · 8절

---

## ③ 사실

### ③-1 API (1.1·1.5절)

| 축 | API | 기관 | 엔드포인트 | 키 | 형식 | 페이징 | 수집 주기 (워크로드 권장값) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 클로로필·기준선 | 어장환경 해수면 `femoSeaList` | 국립수산과학원 | 같음 | `NIFS_KEY_FISHERY_SEA` | JSON | 없음 | **주 1회 게시 감시** + 게시 시 전량 |

| 항목 | 사양 |
| --- | --- |
| 요청 | 달력 연도 단위 `sdate`/`edate`. 연 약 1,000건 |
| 날짜 | `DATE_Y`·`DATE_M`·`DATE_D` **분리, 한 자리 가능**(`"5"`) → 정수 변환 후 조립 |
| 좌표 | 도분초 문자열, 구분자 `°`(U+00B0) `´`(U+00B4) `˝`(U+02DD) |
| 정점 키 | `FISHERY`(만 이름) + `LOCATION_POINT`. **어장명은 행정구역이 아니다** |
| 항목 | 수온·염분·pH·DO·COD·영양염·**클로로필(`CHL_S`/`CHL_B`)** 표층/저층 |
| 게시 상태 | **2025-11-05 이후 없음. 2026년 전 월 `00`+0건** (쿼리 결함 아님) |
| 운영 | 과거 연도 1회 보관 + **주 1회 올해 창 건수 감시** |

- 키는 **nifs.go.kr 자체 키** `NIFS_KEY_FISHERY_SEA`다. 키 파라미터명 `key` — `final_url`까지 마스킹된다(`common-core`)
- 요청주소는 적조·정선과 같다(`/OpenAPI_json` → `/api/OpenAPI_json` 리다이렉트)

### ③-2 수집 (2.1·3.3·8절)

| 워크로드 | 주기 | 하는 일 |
| --- | --- | --- |
| `collector-fishery-watch` | CronJob, 주 1회 | 올해 창 건수(사전 읽기)를 **직전 감시 원문의 메타 건수**와 비교 → 다르면 **같은 실행에서** 해당 연도 전량 호출. 이벤트를 받는 별도 워크로드는 없다 |
| `collector-fishery-backfill` | Job, 1회 (수동) | 과거 연도 보관 — **올해 직전 연도부터 한 해씩 거슬러 올라가며**, 연속 2개 연도 0건이면 정지 |
| `collector-completeness` | CronJob, 주 1회 | 같은 창을 월 분할로 수집(`tag = completeness`). 비교는 `common-core` |

- 단 **수집 범위를 정하는 사전 읽기**는 허용한다 — 결과 코드 존재 여부, `totalCount`(다음 페이지 요청), 어장환경 올해 창 건수(직전 감시 원문의 메타 건수와 비교해 전량 수집 여부). 사전 읽기 결과는 수집 범위에만 쓰고 **상태 판정·적재에는 쓰지 않는다.** 판정은 processor가 원문으로 다시 한다

- **페이징이 없다**(`pageNo` 무시). 완전성은 분할 합산으로 본다 — **비교 범위를 먼저 맞춘다**(N12)
- 호출은 **달력 연도 단위**로 한다. 호출 예산: 게시 감시 주 1회

### ③-3 정규화 (1.5·4.5·5.3절)

| 테이블 | 핵심 컬럼 | 비고 |
| --- | --- | --- |
| `survey_observations` | `station_id`, `surveyed_on`, `layer`, `metric`, `value`, `raw_id` | PK (`station_id`, `surveyed_on`, `layer`, `metric`) |
| `publication_checks` | 4.5절 | PK `raw_id` — 감시 호출 한 번 = 원문 하나 = 기록 하나 |

- 출력: `survey_observations(station_id, surveyed_on, layer('S'|'B'), metric, value)`
- **metric은 3종** — `water_temp` · `salinity` · `chlorophyll`, 각각 층(`S` 표층 / `B` 저층)별. 쓰임이 정해진 것만 저장한다: 클로로필은 양식장 클로로필 칸(4.8절 — 표층 `CHL_S`)과 R2, 수온·염분은 R3·R1. pH·DO·COD·영양염은 저장하지 않는다 — 원문이 보관되므로 필요해지면 `reprocess`로 추가한다(정선관측 4.4절과 같은 원칙). 원문 필드명은 `CHL_S`·`CHL_B` 외에는 I-5에서 원문으로 확인한다
- **게시 감시**: `publication_checks(axis, checked_at_utc, target_year, total_count, prev_total_count, delta, raw_id)`
  - 0건 → `publication_checks`에 기록. **게시 대기 판정은 `evaluation`이 이 기록으로 한다**(4.9절)
  - 증가 → `publication_checks`에 기록(`delta` > 0) + 보관본 비교. **전량 수집은 collector가 이미 같은 실행에서 했다**(2.1절) — processor는 이벤트를 내지 않는다
  - 호출 실패 → 3.2절 상태 그대로 (**게시 대기로 삼키지 않는다**)
- 백필 대조값: 2023 1,008 / 2024 1,020 / 2025 1,022 — 다르면 "제공기관 데이터 변동"으로 기록
- 날짜는 `DATE_Y`·`DATE_M`·`DATE_D`를 **정수로 바꾼 뒤** 조립한다 — 한 자리(`"5"`)로 온다. **날짜를 못 찾으면 명시적 오류로** 처리한다. 조용히 넘어가지 않는다
- 좌표는 도분초 문자열이다. 변환·검증은 `common-core`의 `common/geo/`를 쓴다(구분자 `°`·`´`·`˝`, 폐구간)
- 정점 키는 `FISHERY`(만 이름) + `LOCATION_POINT`다. **`station_id`는 `fishery:` + 두 값을 `-`로 이은 값**이다 — `stations.id` 형식 `원천:원천키`(5.3절). **어장명은 행정구역이 아니다** — 시군구로 해석하지 않는다
- 표층/저층은 `layer`(`S`/`B`)로 둔다. 클로로필은 `CHL_S`(표층)·`CHL_B`(저층)이며, 양식장 클로로필 칸은 **표층(`CHL_S`)**을 쓴다(4.8절 — `grading`)

### ③-4 게시 감시의 결과 해석 (4.5·4.9절)

| 감시 호출 결과 | 이 skill이 하는 일 | 그 뒤 |
| --- | --- | --- |
| `OK_EMPTY`(`00` + 0건) | `publication_checks`에 0건 기록 | `evaluation`이 **게시 대기**로 판정 |
| 건수 증가 | collector가 **같은 실행에서** 해당 연도 전량을 이미 호출했다. processor는 `publication_checks`에 기록(`delta` > 0)하고 보관본과 비교한다 — 이벤트를 내지 않는다 | 새 조사 연월로 갱신 |
| 호출 실패(`NET_ERROR`·`TIMEOUT_05`·`PARSE_FAILURE` 등) | 3.2절 상태 그대로 둔다 | **게시 대기로 삼키지 않는다** — `evaluation`이 확인 불가류로 판정 |

- 클로로필 축은 신선도 임계가 없다(`stale_threshold_hours.chlorophyll: null`, **판정 정의**). 이 skill은 이 설정을 쓰지 않는다 — 게시 시계로 판정하는 것은 `evaluation`이다
- 백필 대조값: **2023 1,008 / 2024 1,020 / 2025 1,022.** 다르면 "제공기관 데이터 변동"으로 기록한다 — 기대값을 고치지 않는다

### ③-5 이 원천에 적용되는 품질 규칙 (4.6절)

구현은 `common-core`(`processor/quality/`)다.

| 규칙 | 적용 원천 | 조건 | 판정 |
| --- | --- | --- | --- |
| **R7** 파싱 실패 (최우선) | 전부 | 알려진 응답 스키마 어디에도 맞지 않음, 결과 코드를 못 찾음·빈 값 (3.2절) | `PARSE_FAILURE` — 원문 보관, 검토 대상. "데이터 없음"으로 축약하지 않는다 |
| **R0** 결측 | tide·line·fishery | 수온·염분·pH가 `0.000` / 수온·염분·DO가 모두 빈 문자열인 레코드 | 결측(`MISSING`) — 관측 건수·커버리지에서 제외, 행은 저장 |
| **R1** 생물부착 의심 | line·fishery | 염분 < 31.0 psu (정상 32~33). **하구 예외**: 섬진강하구 등 하구 정점은 적용하지 않는다 | `SENSOR_QUALITY` |
| **R2** 클로로필 급변 | fishery | 클로로필 > 10.0 이고 직전 대비 증가 > 5.0. **직전 = 같은 정점(`FISHERY` + `LOCATION_POINT`)·같은 층의 바로 이전 조사** | `SENSOR_QUALITY` (해조류 간섭 의심) |
| **R3** 물리 범위 | 전부 | 수온 < 0 또는 > 35 ℃ | `SENSOR_QUALITY` |
| **R5** 침묵 | 전부 | 마지막 관측 이후 경과 > 축별 임계(4.9절 표). **적조는 예외 — 마지막 속보가 아니라 마지막 성공 호출 이후 경과**로 본다. 속보가 없는 것은 정상이고 호출 실패만 장애다(v1.5 7.3절 "이벤트성 — 호출 실패만 장애"). 클로로필은 임계 없이 게시 감시(4.5절) | `STALE` |

- **R2(클로로필 급변)는 이 원천에만 적용된다** — 해조류 간섭 의심. 직전은 **같은 정점·같은 층의 바로 이전 조사**다. 이 어댑터는 비교에 필요한 정점 키·층·조사일을 정확히 넘겨야 한다
- R1(생물부착)은 이 원천에도 적용된다 — 하구 정점 예외 목록은 미결(11절)

---

## ④ 이식 출처와 사용 금지 (6.3절)

검증 폴더는 별칭으로만 부르고 **읽기만** 한다. 이식할 때마다 `docs/SOURCES.md`에 `새 경로 | 출처 파일::함수 | 출처 파일 SHA-256 | 바꾼 점`을 남긴다.

| 새 경로 | 검증 코드 위치 | 처리 | 이식 시 반드시 바꿀 것 |
| --- | --- | --- | --- |
| `collector/adapters/fishery/` · `collector/fishery_watch.py` · `processor/adapters/fishery/` | `$SRC_IDW/src/collector.py` `collect_fishery_sea()` | 참고 | 달력 연도 단위 호출 — 백필 구조 참고 |
| | `$SRC_API/verify_nifs_api.py` `extract_dates()` | 참고 | `DATE_Y/M/D` 조립. **날짜를 못 찾으면 조용히 넘어가는 결함** → 명시적 오류로 |
| | `$SRC_API/verify_nifs_api.py` `check_liveness()` | **사용 금지** | 실패 시 작년 창으로 폴백 |
| | 게시 감시 | 신규 | 검증 코드 없음. 규칙은 ③-4 |
| (좌표) | `$SRC_API/verify_nifs_api.py` `DMS_RE`, `dms_to_decimal()` | **이식** — 단 `common-core`가 `common/geo/`로 | 이 skill은 호출만 한다 |

---

## ⑤ 함정

- **2026년 올해 창은 `00` + 0건이다.** 쿼리 결함이 아니다. 이것은 **정상적 침묵(게시 대기)**이며 장애가 아니다 — 조사 간격 기준으로 판정하면 데모 내내 STALE이 된다
- **호출 실패를 게시 대기로 삼키지 않는다.** 연결 실패·타임아웃·파싱 실패는 각각의 상태로 남아야 한다(N8). "0건"과 "못 읽음"은 다르다
- **빈 결과 코드를 `00`으로 읽으면 게시 대기로 보인다** — 파서 사고가 그대로 "정상적 침묵"이 된다. 판별은 `common-core`가 `PARSE_FAILURE`로 한다
- **실패했다고 작년 창으로 폴백하지 않는다** — 1주차 스크립트(`check_liveness()`)의 결함이다. 폴백하면 게시 여부를 영영 알 수 없다
- **`DATE_D`가 한 자리로 온다**(`"5"`). 문자열 이어붙이기로 날짜를 만들면 틀린다
- **날짜를 못 찾은 행을 조용히 넘기지 않는다** — 건수가 조용히 줄어 백필 대조가 어긋난다
- **1년 창 단일 호출과 월 분할을 그대로 비교하지 않는다.** 단일 255건과 분할 합 212건의 차이는 절단이 아니라 범위 차이(2025-09-24~30의 43건)였다(F3)
- **어장명은 행정구역이 아니다** — 만 이름이다
- **원문 필드명을 그대로 metric 이름으로 쓰지 않는다** — `chlorophyll`로 정규화하지 않으면 `grading`이 양식장 클로로필 칸을 채우지 못하고 R2도 조용히 적용되지 않는다. 3종 밖의 수치 필드는 저장하지 않는다(원문에는 남는다)
- **백필은 연속 2개 연도 0건이면 멈춘다.** 그 전의 0건 한 해를 "끝"으로 보지 않는다

---

## ⑥ 검사와 기대값

| # | 입력 | 통과 기준 |
| --- | --- | --- |
| F1 | A `femoSeaList` 2023·2024·2025 연도 원문 | 건수 1,008 / 1,020 / 1,022, 전부 `OK` |
| F2 | A `femoSeaList` 2026 창 | `OK_EMPTY`, `publication_checks`에 0건 기록 (게시 대기 판정은 7.5 P6) |
| F3 | A `femoSeaList` 1년 창 단일 | 255건, 2025-10-01 이후 212건 |

| # | 입력 | 기대 |
| --- | --- | --- |
| N8 | 게시 감시 호출 연결 실패 | `NET_ERROR`, **`PUBLICATION_PENDING` 아님** |

- 원문: `$SRC_API/output/raw/`의 `femoSeaList_f3_2023_*`·`_2024_*`·`_2025_*`(F1), `femoSeaList_f1_*`(F2), `femoSeaList_f2_single_*`(F3) → `fixtures/raw/`(A.7절)
- 게이트 기대값(7.7절 `counts`): `femo_2023·2024·2025: {raw = stored = 1008 / 1020 / 1022}`, `femo_2026: {raw: 0, status: OK_EMPTY, publication_check_rows: 1}`
- 관련 검사(다른 skill 소유): N12·N13(분할 합산), Q4(R2)·Q3(R1)·Q1(R3) — `common-core` / P6(게시 대기 판정) — `evaluation` / 클로로필 정점 선택 — `grading`

---

## ⑦ 주인이 아닌 사실 — 참조만

| 사실 | 주인 |
| --- | --- |
| 상태 이름표, 필드 의미, `_utc` 규칙 | `CLAUDE.md` 6절 |
| 호출층, 응답 해석, 원문 저장, 분할 합산 비교, 도분초 변환·좌표 검증, 품질 규칙 구현 | `common-core` |
| 게시 대기 판정, 클로로필 게시 시계(`chlorophyll: null`) | `evaluation` |
| 양식장별 클로로필 정점 선택, 조사 기준 추정 계산 여부 | `grading` |

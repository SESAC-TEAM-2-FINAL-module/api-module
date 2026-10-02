---
name: tide
description: "조위관측소 최신관측(dtRecent) 수집·가공 어댑터 — src/api_module/collector/adapters/tide/ 와 processor/adapters/tide/ 를 만들거나 고칠 때 쓴다 (지시서 I-2). 9개 관측소 전 페이지 수령, 6개 metric 정규화, 0.000 결측, 경도 필드 lot, 값 멈춤 플래그(STALE_SUSPECT), 관측소 미가동(STATION_INACTIVE). 응답 해석·완전성 비교·품질 규칙 구현(common-core), IDW(interpolation) 작업에는 쓰지 않는다."
---

# tide

국립해양조사원 조위관측소 최신관측 `dtRecent`를 수집하고, 해석된 응답을 관측값으로 정규화한다. 공용 용어(상태 이름, 필드 의미, `_utc` 규칙)는 `CLAUDE.md` 6절에 있다. 괄호 속 "N절"은 계획서의 절이다.

---

## ① 범위

| 경로 | 이 skill이 만드는 것 |
| --- | --- |
| `collector/adapters/tide/` | 9개 관측소 호출, **`totalCount`까지 전 페이지 수령**, 원문 저장 요청. `collector/main.py`의 `collector-tide` 명령에 **등록** |
| `processor/adapters/tide/` | 해석된 응답(`common/classifier` 결과) → `observations` 행 정규화, `0.000` 결측, 값 멈춤 플래그, 관측소 미가동 판정. `processor/main.py`에 **등록** |

**만들지 않는 것**

- 호출층·응답 해석·원문 저장 형식·`totalCount` 대조(수령 건수 비교)·품질 규칙 R0~R7의 구현 → `common-core`. 이 skill은 어댑터가 그 결과를 쓰는 부분만 만든다
- IDW에서 값 멈춤 관측소를 뺄지(`interpolation.exclude_flatline`)의 적용 → `interpolation`
- 신선도 임계 판정과 축 상태(`값 멈춤`·`커버리지 밖`) 기록 → `evaluation`
- 양식장별 최근접 활성 관측소 선택 → `grading`
- 분할 합산 수집은 없다 — `dtRecent`는 `totalCount`가 있어 수령 건수 대조로 완전성을 본다(3.3절)

---

## ② 원천 절 (계획서)

1.1(`dtRecent` 행) · 1.2 · 2.1(`collector-tide`) · 4.1 · 4.6(tide 적용 규칙) · 6.3(tide 행) · 8절(호출 예산)

---

## ③ 사실

### ③-1 API (1.1·1.2절)

| 축 | API | 기관 | 엔드포인트 | 키 | 형식 | 페이징 | 수집 주기 (워크로드 권장값) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 수온·염분·조위·풍속·기온 | 조위관측소 최신관측 `dtRecent` | 국립해양조사원 `1192136` | `https://apis.data.go.kr/1192136/dtRecent/GetDTRecentApiService` | data.go.kr 일반 인증키 (Decoding, `params=`) | JSON | **`totalCount` 있음 — 전 페이지 수령** | **10분** |

| 항목 | 사양 |
| --- | --- |
| 관측소 | 시연권역 신청 9 — `DT_0014` 통영 · `DT_0016` 여수 · `DT_0029` 거제도 · `DT_0061` 삼천포 · `DT_0026` 고흥발포 · `DT_0062` 마산 · `DT_0063` 가덕도 · `DT_0049` 광양 · `DT_0092` 여호항 |
| 실효 | **7개소.** `DT_0049`·`DT_0092`는 90일 전 기간 수온·염분 100% `0.000` → 수집은 계속하되 "관측소 미가동"으로 판정 |
| 갱신 | 관측소별 3.6~15.4분 |
| 사용 필드 | 수온·염분·**조위·풍속·기온**(v1.5 추가)·좌표 |
| 좌표 | 경도 필드명이 **`lot`** (오타 아님) |
| 결측 | **`0.000`** = 결측 (R0). 수온·염분·pH에 적용 |
| 스키마 | `response.header` / `OpenAPI_ServiceResponse.cmmMsgHeader` / **최상위 `header`** 가능 — 3종 모두 처리 |
| 함정 | 마지막 페이지의 마지막 시각 그룹이 잘리면 "관측소 동시 무응답"처럼 보인다 → **수령 건수 = `totalCount`까지**. `totalCount`는 **관측 시점 수**다 — metric 분해 후 행 수와 다르다(3.3절) |

- 키는 data.go.kr 일반 인증키 **Decoding 값을 `params=`로** 넘긴다. URL 문자열에 키를 조립하지 않는다(Encoding/Decoding 혼용 위험 — ④ 사용 금지)
- 관측소 목록은 판정 정의 **`tide.stations`**(`config/definitions.yaml`)에서 읽는다. 현재 값: `[DT_0014, DT_0016, DT_0029, DT_0061, DT_0026, DT_0062, DT_0063, DT_0049, DT_0092]`. 코드에 박지 않는다
- 미가동 2개소(`DT_0049`·`DT_0092`)도 **수집은 계속**한다. 미가동 판정은 processor가 한다

### ③-2 수집 (2.1·8절)

- 워크로드 `collector-tide` — CronJob 10분(워크로드 설정, `HANDOFF.md` 권장값). `dtRecent` 9개소 → 원문 → `raw.fetched`
- 호출 예산: 회당 9(+페이지), 하루 약 1,300. data.go.kr 개발계정 한도는 **실측 전**이다 — 한도 초과 코드 `22`는 `QUOTA`로 분리 기록된다(`common-core`)
- collector는 **판정하지 않는다.** 전 페이지를 받기 위해 첫 응답의 `totalCount`를 **사전 읽기로만** 쓴다. 그 값을 상태 판정·적재에 쓰지 않는다 — 수령 건수 대조는 processor가 원문으로 다시 한다
- 실패한 호출을 다른 창·파라미터로 자동 대체하지 않는다. 재시도는 `05`에만 1회(`common-core`)

### ③-3 정규화 (4.1절)

- 출력: `observations(station_id, observed_at_utc, metric, value, …)` — metric은 `water_temp`·`salinity`·`tide_level`·`wind_speed`·`wind_dir`·`air_temp`
- **`0.000`은 결측 행으로 저장** (`value = NULL`, `missing_reason = 'ZERO_SENTINEL'`) — 버리지 않는다. 결측 구간 자체가 화면 정보다
- **값 멈춤 감지**: 같은 값이 연속 N분 → `STALE_SUSPECT` 플래그. **N은 별도 설정값**(`tide.flatline_minutes`, 운영 조정 — 값 미결, 11절)이다. v1.5 7.3절 `stale_threshold`(새 값이 **안 들어오는** 시간)와 다른 개념이므로 가져다 쓰지 않는다. 판정이 아니라 플래그 — 축 상태 `값 멈춤`으로 기록한다(4.9절)
- 잔잔한 시기에는 정상 관측소도 같은 값이 이어질 수 있다. 그래서 `STALE_SUSPECT` 관측소를 IDW에서 빼는지 여부도 **설정값**(`interpolation.exclude_flatline`)으로 두고 CI 게이트 기준 문서에 등록한다
- 관측소 미가동: 최근 24시간 전 행이 결측이면 `STATION_INACTIVE` — 분류는 **커버리지 밖** (v1.5 22절 "침묵 11번째 분류 미신설" 결정)

- **`station_id`는 `tide:` + 관측소 코드**다(예: `tide:DT_0016`) — `stations.id` 형식 `원천:원천키`(5.3절). 설정 `tide.stations`의 값(`DT_0016`)은 접두어 없는 원천 코드다
- 출력 행은 `observations`(PK `station_id`, `observed_at_utc`, `metric`)에 들어간다. 필드: `station_id`, `observed_at_utc`, `metric`, `value`(nullable), `missing_reason`, `flags`, `raw_id`(5.3절)
- **같은 관측이 두 수집 원문에 함께 올 수 있다**(관측소 갱신 3.6~15.4분, 수집 10분). 적재 키가 관측 시각 기준이므로 중복 행이 생기지 않아야 한다 — 같은 알림·같은 원문을 두 번 처리해도 결과가 같아야 한다(2.2절 멱등)
- `obs.loaded`의 `source`는 `tide`, `api`는 `dtRecent`다(2.2절). 이 알림을 `interpolation`(수온)과 `grading`(모든 축)이 받는다
- **원천 시각의 시간대**는 계획서에 적혀 있지 않다. I-2에서 원문으로 확인해 `docs/SOURCES.md`에 기록하고 UTC로 변환한다 — **추정하지 않는다**. 모르면 멈추고 보고한다

### ③-4 이 원천에 적용되는 품질 규칙 (4.6절)

구현은 `common-core`(`processor/quality/`)다. 이 어댑터는 규칙이 쓰는 값·시각을 정확히 넘겨야 한다.

| 규칙 | 적용 원천 | 조건 | 판정 |
| --- | --- | --- | --- |
| **R7** 파싱 실패 (최우선) | 전부 | 알려진 응답 스키마 어디에도 맞지 않음, 결과 코드를 못 찾음·빈 값 (3.2절) | `PARSE_FAILURE` — 원문 보관, 검토 대상. "데이터 없음"으로 축약하지 않는다 |
| **R0** 결측 | tide·line·fishery | 수온·염분·pH가 `0.000` / 수온·염분·DO가 모두 빈 문자열인 레코드 | 결측(`MISSING`) — 관측 건수·커버리지에서 제외, 행은 저장 |
| **R3** 물리 범위 | 전부 | 수온 < 0 또는 > 35 ℃ | `SENSOR_QUALITY` |
| **R4** 급변 | tide | 수온 1시간 변화 절댓값 > 5.0 ℃. **1시간 전 값 = 같은 관측소 수온 중 관측 시각이 [t − 60분 − 허용, t − 60분]인 가장 늦은 유효값** — 허용은 판정 정의 `quality.r4_lookback_tolerance_min`(15.4 = 관측소 최장 갱신 간격, 1.2절). 창 안에 값이 없으면 R4를 판정하지 않는다. **태풍 특보 중에는 면제** | `SENSOR_QUALITY` |
| **R5** 침묵 | 전부 | 마지막 관측 이후 경과 > 축별 임계(4.9절 표). **적조는 예외 — 마지막 속보가 아니라 마지막 성공 호출 이후 경과**로 본다. 속보가 없는 것은 정상이고 호출 실패만 장애다(v1.5 7.3절 "이벤트성 — 호출 실패만 장애"). 클로로필은 임계 없이 게시 감시(4.5절) | `STALE` |

- R1(생물부착)은 **`dtRecent` 염분에 적용하지 않는다** — 정선·어장환경 전용이다
- `SENSOR_QUALITY` 관측값은 IDW 입력에서 빠진다(4.7절 — `interpolation`)

### ③-5 설정 (2.0.6절)

| 키 | 구분 | 이 skill에서의 쓰임 |
| --- | --- | --- |
| `tide.stations` | 판정 정의 | 수집 대상 관측소 |
| `tide.flatline_minutes` | **운영 조정** — 인계 초기값 30(2026-09-30) | 값 멈춤 감지의 N분. 테스트는 이 값에 상대적으로 짠다. ConfigMap에 없으면 멈추고 보고한다 — 기본값으로 감지를 끄지 않는다(2.0.6절) |
| `interpolation.exclude_flatline` | 판정 정의 (주인 `interpolation`) | 이 skill은 플래그만 단다. 제외 여부는 쓰지 않는다 |

- `tide.flatline_minutes`는 운영 조정 키 중 **`processor`가 쓰는 유일한 키**다. 운영 조정 게이트의 판정 재생(`evaluation` 이미지)으로 확인되지 않고, **스키마 검사와 PR 리뷰로만** 지켜진다(2.0.6절 남는 한계)

---

## ④ 이식 출처와 사용 금지 (6.3절)

검증 폴더는 별칭으로만 부르고 **읽기만** 한다. 이식할 때마다 `docs/SOURCES.md`에 `새 경로 | 출처 파일::함수 | 출처 파일 SHA-256 | 바꾼 점`을 남긴다.

| 새 경로 | 검증 코드 위치 | 처리 | 이식 시 반드시 바꿀 것 |
| --- | --- | --- | --- |
| `collector/adapters/tide/` (페이지 넘김) | `$SRC_IDW/stage2_collect.py` `_fetch_all_pages()` | **이식** | `totalCount`까지 수령. 마지막 페이지 절단 함정. `totalCount`는 사전 읽기로만 |
| `collector/adapters/tide/` · `processor/adapters/tide/` | `$SRC_IDW/stage2_collect.py` (dtRecent 수집·페이징) | **이식** | 조위·풍속·기온 필드 추가. `0.000` 결측 처리 위치는 I-2에서 확인 |
| | `$SRC_IDW/stage1_verify.py` (dtRecent 응답 검증) | 참고 | 스키마 3종 검증 항목 |
| | `$SRC_IDW/stage2_collect.py` `parse_resp()` | 참고 | data.go.kr `dtRecent` 계열(최상위 `header` 포함). 해석 자체는 `common-core`의 `classifier` |
| | `$SRC_IDW/stage2_collect.py` `_save_raw()` | **사용 금지** | 수정 전에는 200,000자 절단. 형식도 확정본과 다름 |
| | `$SRC_API/check_tide_wtemp.py` `call()` | **사용 금지** | URL 문자열에 키를 직접 조립 (Encoding/Decoding 혼용 위험) |
| | `$SRC_API/check_tide_wtemp.py` | **사용 금지** | 폐기된 `surveyWaterTemp` 대상 |

- 이식 전에 `$SRC_IDW`의 `stage1_verify.py`·`stage2_collect.py`가 **B 수정본**인지 확인한다 — 파일 수정 시각과 절단 코드(`[:100000]`·`[:200_000]`)가 없는지로(6.2절). 아니면 멈추고 보고한다

---

## ⑤ 함정

- **경도 필드 이름이 `lot`다.** 오타가 아니다. `lon`·`lng`로 바꿔 찾으면 좌표가 빈다
- **`0.000`은 결측이다**(수온·염분·pH). 값 0으로 저장하지도, 행을 버리지도 않는다 — `value = NULL`, `missing_reason = 'ZERO_SENTINEL'`
- **마지막 페이지의 마지막 시각 그룹이 잘리면 "관측소 동시 무응답"처럼 보인다.** 수령 건수가 `totalCount`에 닿을 때까지 받는다
- **응답 스키마가 세 가지다** — `response.header` / `OpenAPI_ServiceResponse.cmmMsgHeader` / 최상위 `header`. 판별은 `common-core`가 하지만, 어댑터가 한 계열만 가정하면 나머지 둘에서 조용히 빈 결과가 된다
- **값 멈춤은 신선도와 다르다.** `stale_threshold`(새 값이 **안 들어오는** 시간)를 N분으로 가져다 쓰지 않는다. 값 멈춤은 새 값이 들어오는데 **같은 값**인 것이다
- **잔잔한 시기에는 정상 관측소도 같은 값이 이어진다.** 그래서 값 멈춤은 판정이 아니라 플래그다
- **`DT_0049`·`DT_0092`는 90일 전 기간 수온·염분이 전부 `0.000`이다.** 수집을 멈추거나 목록에서 빼지 않는다 — `STATION_INACTIVE`로 드러나야 한다
- **`DT_0061` 염분은 최장 518분 연속 결측이 있었다.** 결측 구간을 그대로 저장한다. 이것을 정상으로 볼지는 미결이다(11절)
- **F11은 원문 재생이 아니다.** 2차 수집 당시 원문이 200,000자에서 잘려 저장돼, F11은 가공 CSV와의 "가공 결과 대조"다

---

## ⑥ 검사와 기대값

| # | 입력 | 통과 기준 |
| --- | --- | --- |
| F11 | `fixtures/derived/` — `$SRC_IDW` `dtRecent` 90일 가공 CSV | `DT_0049`·`DT_0092` 전 기간 `STATION_INACTIVE` / `DT_0061` 염분 최장 연속 결측 **518분** |

| # | 규칙 (절) | 입력 | 통과 기준 |
| --- | --- | --- | --- |
| Q5 | 값 멈춤 감지 (4.1) | 같은 값이 `tide.flatline_minutes` 직전까지 / 직후까지 이어짐 | 앞은 플래그 없음, 뒤는 `STALE_SUSPECT` |

- **F11은 CI 게이트 밖이다**(대용량 가공 CSV). S3에서 **로컬 수동 실행**으로 통과를 확인하고, S12에서 다시 돌려 `docs/reports/`에 기록한다(7.1절). 입력은 `fixtures/derived/`의 경로 참조와 해시다 — 원본은 `$SRC_IDW/output/observations.csv`(저장소 밖)
- Q5는 `tide.flatline_minutes`에 **상대적으로**(직전 / 직후) 짠다. 값을 채우지 않는다
- 관련 검사(다른 skill 소유): Q1(R3)·Q2(R4) — `common-core` / 7.3b `값 멈춤`·`커버리지 밖` 전달 — `evaluation` / Q7(IDW 입력 필터) — `interpolation`

픽스처 출처 (A.7절): F11은 `$SRC_IDW/output/`의 `observations.csv`(dtRecent 90일, 약 280MB) — 원문이 아니라 가공 CSV다. 저장소에는 경로 참조와 해시만 둔다. 이 CSV는 **IDW 보간 입력 전용**이라 `water_temp`·`salinity` 두 지표만 있다 — `tide_level`·`wind_speed`·`air_temp`는 없다(6.2절)

F11 `DT_0061` 기대값(7.1절, 개정 11): 염분 **정상값(비0·비결측) 사이 최장 간격 > `stale_threshold_hours.salinity_tide`** — 임계 상대. 확인된 구간 2026-07-05 518분, 2026-08-01~08-04 2,881분

---

## ⑦ 주인이 아닌 사실 — 참조만

| 사실 | 주인 |
| --- | --- |
| 상태 이름표, 필드 의미, `_utc` 규칙 | `CLAUDE.md` 6절 |
| 호출층(재시도 `05` 1회), 응답 스키마 판별, 결과 코드 → 상태, 원문 저장 형식, 수령 건수 대조, 품질 규칙 구현, `adapter_health` | `common-core` |
| `exclude_flatline` 적용, 사용 관측소, IDW | `interpolation` |
| 신선도 임계, 축 상태 기록 (`값 멈춤`·`커버리지 밖`) | `evaluation` |
| 양식장별 최근접 활성 관측소 선택 | `grading` |

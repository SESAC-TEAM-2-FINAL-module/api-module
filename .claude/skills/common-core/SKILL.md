---
name: common-core
description: "src/api_module/common/(repository 제외)과 수집·가공 공통 골격(collector/main.py, processor/main.py, processor/quality/, processor/completeness/)을 만들거나 고칠 때 쓴다 (지시서 I-1). 호출층, 응답 해석, 완전성 검사, 원문 저장, 단계 간 알림 큐, 좌표 변환·검증, 양식장 좌표 읽기, 설정 로딩과 기동 시 검사, 품질 규칙 R0~R7, adapter_health 기록, 운영 지표. 원천별 어댑터·DB 접근 계층·IDW·등급·침묵 판정 작업에는 쓰지 않는다."
---

# common-core

모든 이미지가 함께 쓰는 공통 코드와, 원천 어댑터를 부르는 수집·가공 진입점을 만든다. 공용 용어(상태 이름, 필드 의미, 설정 3종, `_utc` 규칙)는 `CLAUDE.md` 6절에 있다 — 여기서 다시 정의하지 않는다. 괄호 속 "N절"은 계획서의 절이다.

---

## ① 범위

| 경로 | 이 skill이 만드는 것 |
| --- | --- |
| `common/config/` | `.env` 로딩(API 키·요청주소·DB 연결 문자열 — 값은 출력하지 않는다), 판정 정의(`config/definitions.yaml`, 이미지 안) 로딩, 운영 조정(ConfigMap) 로딩과 스키마 검사, API 정의 로딩 |
| `common/http/` | 공통 호출층 (③-1) |
| `common/classifier/` | 형식 판별, 스키마 계열, 결과 코드 → 상태 (③-3) |
| `common/raw_store/` | 객체 저장소 인터페이스 — collector가 쓰고 processor가 읽는다. collector는 **메타만** 읽을 수 있다(어장환경 게시 감시가 직전 감시 원문의 건수와 비교 — 2.1절) (③-5) |
| `common/queue/` | 큐 인터페이스 + NATS·인메모리 구현, 단계 간 알림 스키마 검사 (③-6) |
| `common/geo/` | 도분초 변환, 좌표 폐구간 검증, 거리 계산 (③-7) |
| `common/farm_sites/` | 양식장 좌표 읽기 · 폐구간 검증 호출 (③-8) |
| `common/contract_check/` | 기동 시 검사 — 테이블 존재·형태, 입력 단계 계약 버전, 운영 조정 스키마 (③-9) |
| `common/metrics/` | 운영 지표 (③-13) |
| `collector/main.py` | 수집 진입점 — 워크로드 명령마다 원천 어댑터를 부른다 (③-12) |
| `processor/main.py` | 가공 진입점 — `process`·`reprocess` (③-12) |
| `processor/quality/` | 품질 규칙 R0~R7 (③-10) |
| `processor/completeness/` | 완전성 검사 — `totalCount`·분할 합산·필터 수용 (③-4) |
| `contracts/inputs/farm_sites.md` | 양식장 좌표 입력 계약 (③-8) |
| `contracts/queue/` | 단계 간 알림 메시지 스키마 (③-6) |

**만들지 않는 것**

- `common/repository/` → `repository` skill. 이 skill의 코드는 DB 접근 계층의 **인터페이스**만 부른다. 구현은 I-6(S7)이며, S2~S6은 정규화 결과(메모리)까지 검증한다(10절)
- 원천별 어댑터(`collector/adapters/*`, `processor/adapters/*`) → `tide`·`bulletin`·`line`·`fishery` skill. 진입점은 **어댑터 등록 방식**으로 만들고, 어댑터는 각 원천 지시서(I-2~I-5)가 등록한다
- `interpolation/`·`grading/`·`evaluation/`의 `main.py` → 각 단계 skill
- `contracts/config/operational.schema.json` **파일 작성**은 I-10이다. 이 skill은 그 스키마로 검사하는 **코드**(③-9)를 만든다

---

## ② 원천 절 (계획서)

1.6 · 2.0.6(로딩·스키마·기동 시 검사) · 2.2 · 2.3 · 3절 · 4.6 · 4.9(`adapter_health` 갱신 규칙) · 6.1 · 6.3(`common/`·`processor/completeness/`·`processor/quality/` 행) · 9절

---

## ③ 사실

### ③-1 호출층 (3.1절)

| 규칙 | 근거 |
| --- | --- |
| 키는 **Decoding 키를 `params=`로.** URL 문자열 조립과 섞지 않는다 | Encoding/Decoding 혼용 시 깨짐 |
| 키 파라미터 **대소문자는 서비스 명세 그대로** (`serviceKey` / `ServiceKey`) | 같은 기관 안에서도 다름 |
| **값이 빈 선택 파라미터는 보내지 않는다** | `param=`이 필터로 해석되는 위험 |
| 형식 파라미터명도 명세 그대로 (`type` / `_type` / `resultType` / `dataType`) | 서비스마다 다름 |
| 타임아웃: 연결 10초, 읽기 **60초** | 30초에서 실제 타임아웃 발생 |
| 리다이렉트 따라가고 **최종 URL 기록** | NIFS `/OpenAPI_json` → `/api/OpenAPI_json` |
| `05`는 2초 후 **재시도 1회**, 재시도 사실 기록 | v1.5 12절 |
| **실패 시 다른 기간·파라미터로 자동 대체 금지** | 1주차 검증 스크립트가 작년 창으로 조용히 폴백하던 결함 |
| 인코딩 **UTF-8 고정** | `apparent_encoding` 오판 |

### ③-2 API 정의는 설정으로 (6.1절)

**API 정의를 코드가 아니라 설정으로** — 요청주소, 키 변수명, 키 파라미터명, 형식 파라미터명, 페이징 여부를 API마다 설정 파일에 둔다. 서비스마다 제각각이던 것(대소문자, `_type`/`resultType`)을 코드 분기 없이 흡수한다.

- 원천별 실제 값(요청주소·파라미터명·키 변수명)은 각 원천 skill에 있다. 요청주소는 **포털·명세의 값을 그대로** `.env`에 두고 경로를 조립하지 않는다 — 서비스 URL과 오퍼레이션이 분리 표기돼 400·`12`를 받은 사례가 있다(1.1절)

### ③-3 응답 해석 (3.2절)

**형식 판별은 요청이 아니라 실제 내용으로** — 앞쪽 공백·BOM 제외 첫 글자 `{`/`[` → JSON, `<` → XML, 그 외 `PARSE_FAILURE`

**스키마 계열** — 순서대로 시도

| 계열 | 루트 | 결과 코드 | item | `totalCount` |
| --- | --- | --- | --- | --- |
| data.go.kr 정상 | `response` | `header.resultCode` | `body.items.item` | `body.totalCount` |
| data.go.kr 에러 | `OpenAPI_ServiceResponse` | `cmmMsgHeader.returnReasonCode` | — | — |
| 헤더 최상위 | `header` + `body` | `header.resultCode` | `body.item` / `body.items.item` | `body.totalCount` |
| NIFS | `header` + `body` | `header.resultCode` | `body.item` | **없음** |
| (예비) 공단 JSON | 오퍼레이션명 | `header.code` | 루트 직속 `item` | 루트 직속 |

- item이 1개면 단일 객체로 온다 → **항상 리스트로**
- XML은 `bytes`로 파싱 (`encoding` 선언 + `str` 입력 시 ParseError). **null 값이 닫는 태그만 나오는 malformed 사례** → 표준 파서 실패 시 `PARSE_FAILURE`, 복구 파서 금지(확정 4종은 JSON이라 해당 없음)

**결과 코드 → 상태**: 표는 `CLAUDE.md` 6절(계획서 3.2절)이다. 그 표의 이름을 코드·계약·픽스처에 그대로 쓴다.

- **앞자리 0 정규화(`"0"` = `"00"`)는 값이 비어 있지 않고 숫자로만 된 경우에만.** 빈 문자열을 `"0"`으로 바꾼 사고가 있었다
- **HTTP 상태코드·`resultMsg` 문자열로 판정하지 않는다** (`NORMAL SERVIE` 오타 실재)
- **`totalCount > 0`인데 item 0개면 `PARSE_FAILURE`**

### ③-4 완전성 검사 (3.3절)

| API 유형 | 검사 |
| --- | --- |
| `totalCount` 있음 (`dtRecent`) | 수령 건수 = `totalCount`. 다르면 `INCOMPLETE` |
| `totalCount` 없음 (NIFS) | **주기적 분할 합산** — 주 1회, 같은 창을 월 분할로 받아 합이 같은지. **비교 범위를 먼저 일치시킨다** (범위가 달라 "절단 확정"이 거짓으로 나온 사례) |
| 필터 파라미터가 있는 API | 반환 행이 **요청 창 안인지** 확인. 창 밖 행이 섞이면 `FILTER_IGNORED` (공단 서비스가 모르는 파라미터를 무시하고 전 이력을 반환한 사례) |

- 분류: `INCOMPLETE` → 파싱 실패와 같은 분류 *(제안)* / `FILTER_IGNORED` → 필터 무시 (v1.5 4.5절 v1.4 추가)

- **분할 합산은 비교 전에 두 결과의 범위를 먼저 맞춘다.** 범위가 다르면 절단·`INCOMPLETE`로 판정하지 않고 운영 이벤트 `COMPARISON_RANGE_MISMATCH` + 검사 무효로 둔다(N12). 범위를 맞춘 뒤에도 합이 모자라면 `INCOMPLETE`(N13)
- 분할 수집 원문은 `collector-completeness`(주 1회, `tag = completeness`)가 만든다(2.1절). 원천별 분할 수집 코드는 각 원천 skill 몫이고, **합산 비교는 여기** `processor/completeness/`가 한다

### ③-5 원문 저장 (2.3절)

**형식은 v1.5 12.1절 확정본을 따르되, 아래 두 가지를 더한다** (확정본과 다른 점을 숨기지 않는다)

```json
{"url": "<키 마스킹>", "params": {"…": "…", "<키 파라미터>": "***"},
 "http_status": 200, "final_url": "<리다이렉트 후, 키 마스킹>",
 "fetched_at": "<ISO UTC>", "body": "<resp.text 그대로>",
 "error": null}
```

| 확정본과의 차이 | 이유 |
| --- | --- |
| `error` 필드를 항상 둔다 (정상이면 `null`) | 확정본은 실패 시 "`body` 대신 예외 종류·메시지"라고만 적었다. 키를 고정해 두 경우를 같은 형태로 읽는다 |
| `fetched_at`을 UTC로 명시 | 확정본은 `<ISO>`. 시각 규칙(5.2절)과 맞춘다 |

- **키 마스킹은 `url`·`params`·`final_url` 세 곳 모두.** 키 파라미터명은 API마다 다르다 — NIFS `key`, data.go.kr `serviceKey`, 공단 일부 `ServiceKey`. NIFS는 키가 쿼리에 있어 **리다이렉트 후 `final_url`에도 남는다.** B v2 원문은 `key=***`로 마스킹돼 있음을 확인했다(A·C 원문은 미확인 — 첨부 A.7 키 검사 스크립트)
- `fetched_at`은 v1.5 확정 형식의 필드명이라 `_utc` 접미 규칙(5.2절)의 **예외**다. DB 색인 행은 `fetched_at_utc`로 쓴다
- 연결 실패·타임아웃은 `body` 대신 `error: {type, message}`
- 저장 직후 `body`를 사전 읽기해 결과 코드가 읽히는지 **확인만** 하고, 결과는 메타에 기록한다 (판정은 processor — 2.1절 사전 읽기 범위)
- **본문은 DB에 넣지 않는다.** 객체 저장소(S3/GCS, 로컬은 MinIO 또는 디스크)에 두고 DB에는 색인 행만 둔다 — 근거는 5.2절 (MySQL `TEXT` 64KB 한계). 저장 위치 최종 결정은 v1.5 12.1절 미결
- 키: `raw/{api}/{yyyy}/{mm}/{dd}/{epoch_ms}_{tag}.json`. **`:` 등 OS 금지 문자 금지**

### ③-6 단계 간 알림 (2.2절)

| 주제 | 발행 | 소비 | 본문 |
| --- | --- | --- | --- |
| `raw.fetched` | collector | processor | `raw_id`, `api`, `tag`, `fetched_at_utc` |
| `obs.loaded` | processor | interpolation(조위 수온만), **grading(모든 축)** | `load_id`, `api`, `source`, `station_ids`, `observed_from_utc`, `observed_to_utc`, `row_count` |
| `interp.done` | interpolation | grading | `run_id`, `load_id`, `farm_count`, `metric`, `error_p95`, `stations_used` |
| `grade.done` | grading | evaluation | `grade_run_id`, `axis`, `farm_ids` |
| `result.updated` | evaluation | (선택) 웹 서비스 캐시 무효화 | `farm_ids`, `axes`, `updated_at_utc` |

- `obs.loaded`의 `source`는 **수집 원천**(`tide`·`bulletin`·`line`·`fishery`)이다. 이 문서의 **축**(양식장 계기판 단위 — 수온·염분·물때 …, `grade.done`의 `axis`)과 다르다
- 모든 알림에 **`schema`(계약 버전)**를 싣는다. 받는 쪽은 자기가 따르는 버전과 다르면 처리하지 않고 운영 이벤트로 남긴다
- **같은 알림이 두 번 와도 결과가 같아야 한다**(멱등). `load_id`·`run_id`로 중복을 거른다
- 단계 간 알림이 없으면 다음 **처리 단계**는 돌지 않는다. **주기 실행으로 처리를 대신하지 않는다** — 멈춘 단계가 드러나야 한다
- **예외는 둘**이다. 어느 쪽도 앞 단계를 대신 돌리지 않는다
  - `evaluation-sweep` — 알림이 끊긴 것 자체를 **침묵 판정**한다. 알림으로만 도는 구조에서는 "알림이 오지 않음"을 알아챌 단계가 따로 있어야 하기 때문이다
  - `interpolation-error` — 자기 산출물(오늘의 오차)만 하루 1회 만든다. 추정값(`interp.done`)을 대신 만들지 않으므로 추정이 멈추면 여전히 드러난다 *(제안 — 11절)*

- 큐 구현(NATS / SQS)은 미결이다 — **`queue` 인터페이스 하나로 감싸고** 로컬 개발은 인메모리 구현을 쓴다
- 메시지 스키마는 `contracts/queue/`에 두고 현재 버전은 `queue-v1`이다(7.7절 `contracts`)

### ③-7 좌표 (1.5·6.1·7.7절)

- 도분초 문자열의 구분자는 `°`(U+00B0) `´`(U+00B4) `˝`(U+02DD)다
- 좌표 검증은 **폐구간**이다 — 위도 33.0 정점이 실재한다. 범위 값은 판정 정의 `geo.lat_range`·`geo.lng_range`(`config/definitions.yaml`, 현재 `[33.0, 39.0]`·`[124.0, 132.0]`)에서 읽고 코드에 박지 않는다
- `common/geo/`는 v1.5 계획서와 이 계획서 첫 판에 없던 모듈이다. 도분초 변환·좌표 검증이 어댑터 세 곳(line·fishery·tide)과 양식장 좌표 검증에 흩어져 있었고, 좌표 검증 개구간 결함(위도 33.0 누락)이 한 곳에서 나와 전부에 번졌기 때문에 한 곳으로 모은다.

### ③-8 양식장 좌표 (1.6절)

| 항목 | 사양 |
| --- | --- |
| 소유 | 웹 서비스. 이 모듈은 **읽기만** 한다 |
| 필요한 열 | `farm_id`, `lat`, `lng`, `active`, `updated_at_utc` |
| 읽는 코드 | **공용 `common/farm_sites/`** — `interpolation`(IDW), `grading`(최근접 관측소·정점 선택, 적조 해역 대응), `evaluation-sweep`(모든 양식장·축 점검)이 함께 쓴다. 단계 전용 코드끼리 import하지 않으므로 공용에 둔다 |
| 읽는 시점 | 각 단계가 실행될 때마다 — `interpolation`은 조위관측소 적재 완료 알림 시(약 10분), `grading`은 `obs.loaded`·`interp.done`마다, `evaluation-sweep`은 주기마다 |
| 계약 | `contracts/inputs/farm_sites.md` — 열 이름·타입·좌표계(WGS84 십진도)·삭제 표현 |
| 새 양식장 | 등록 즉시 계산하지 않는다. **다음 조위관측소 적재 때**(최대 약 10분 뒤) 처음 추정값을 받는다 |
| 좌표 검증 | 이 모듈의 `common/geo/` 폐구간 검증을 통과하지 못한 양식장은 계산할 수 없으므로 전 축 `provenance = NONE`, `none_reason = INVALID_COORDS`(4.8절) |

### ③-9 설정 로딩 · 기동 시 검사 (2.0.6·2.0.3·2.1절)

- **판정 정의**는 이미지 안의 `config/definitions.yaml`에서 읽는다
- **운영 조정**은 ConfigMap에서 읽는다. 로컬에서는 `OPERATIONAL_CONFIG_PATH`가 가리키는 파일이다 *(제안 — 환경변수 이름)*. 운영 조정 키: `tide.flatline_minutes`, `stale_threshold_hours.*`(**`chlorophyll` 제외**), `evaluation.interpolation_stale_minutes`·`grading_stale_minutes`. 초기값은 `config/operational.initial.yaml`이지만 **기동 시 대체값으로 쓰지 않는다**
- 스키마 검사 — `contracts/config/operational.schema.json`: 키 집합 고정(누락·모르는 키는 실패 — 오타 방어), 타입·단위, `<미결>` 같은 자리 표시 거부, 스키마 버전(`operational-v1`) 일치. 하한은 **실측 근거가 있는 키만** 둔다 — `dtRecent` 축은 최장 갱신 간격 15.4분(v1.5 4.3절) 미만 거부 *(제안)*

- ConfigMap이 없거나 스키마와 다르면 **멈추고 보고**한다. `operational.initial.yaml`이나 코드 기본값으로 **조용히 대체하지 않는다**
- 통과하면 **설정 해시**를 `ops_events`(`OPERATIONAL_CONFIG_LOADED`)와 지표 `operational_config_info`에 기록한다. 게이트를 거치지 않은 변경도 운영 탭에서 보인다
- 값은 **기동 시 한 번 읽는다.** 실행 중 다시 읽지 않는다 — 어느 판정이 어느 설정으로 났는지 추적할 수 있게 한다. ConfigMap 변경의 반영은 롤아웃(재시작)이며 방식은 인프라가 구성한다

- **테이블 검사**: 이 모듈이 기대하는 테이블이 없거나 정의와 다르면 기동 시 멈추고 차이를 보고한다. 스스로 만들지 않는다(2.0.3절)
- **계약 버전 검사**: 각 이미지는 자기가 따르는 계약 버전(단계 간 알림·결과 테이블·운영 조정)을 갖고, 기동할 때 맞지 않으면 멈추고 보고한다. 옛 형식을 새 형식으로 조용히 읽지 않는다(2.1절)

### ③-10 품질 규칙 R0~R7 (4.6절)

v1.5 7.3절 규칙 중 이 모듈이 구현하는 것. R6(QC 플래그)은 폐기 — 정선 QC 필드가 전건 `2`라 정보가 없다.

| 규칙 | 적용 원천 | 조건 | 판정 |
| --- | --- | --- | --- |
| **R7** 파싱 실패 (최우선) | 전부 | 알려진 응답 스키마 어디에도 맞지 않음, 결과 코드를 못 찾음·빈 값 (3.2절) | `PARSE_FAILURE` — 원문 보관, 검토 대상. "데이터 없음"으로 축약하지 않는다 |
| **R0** 결측 | tide·line·fishery | 수온·염분·pH가 `0.000` / 수온·염분·DO가 모두 빈 문자열인 레코드 | 결측(`MISSING`) — 관측 건수·커버리지에서 제외, 행은 저장 |
| **R1** 생물부착 의심 | line·fishery | 염분 < 31.0 psu (정상 32~33). **하구 예외**: 섬진강하구 등 하구 정점은 적용하지 않는다 | `SENSOR_QUALITY` |
| **R2** 클로로필 급변 | fishery | 클로로필 > 10.0 이고 직전 대비 증가 > 5.0. **직전 = 같은 정점(`FISHERY` + `LOCATION_POINT`)·같은 층의 바로 이전 조사** | `SENSOR_QUALITY` (해조류 간섭 의심) |
| **R3** 물리 범위 | 전부 | 수온 < 0 또는 > 35 ℃ | `SENSOR_QUALITY` |
| **R4** 급변 | tide | 수온 1시간 변화 절댓값 > 5.0 ℃. **태풍 특보 중에는 면제** | `SENSOR_QUALITY` |
| **R5** 침묵 | 전부 | 마지막 관측 이후 경과 > 축별 임계(4.9절 표). **적조는 예외 — 마지막 속보가 아니라 마지막 성공 호출 이후 경과**로 본다. 속보가 없는 것은 정상이고 호출 실패만 장애다(v1.5 7.3절 "이벤트성 — 호출 실패만 장애"). 클로로필은 임계 없이 게시 감시(4.5절) | `STALE` |

- `SENSOR_QUALITY` 관측값은 IDW 입력에서 빠진다(4.7절 "사용 관측소") *(R1 하구 예외의 정점 목록과 태풍 특보 입력 원천은 구현 시 확인 — 11절)*

- 규칙의 **기준값은 판정 정의 `quality.*`**(`config/definitions.yaml`)에서 읽는다 — `r1_salinity_min`·`r2_chlorophyll`·`r3_water_temp_range`·`r4_water_temp_delta_1h`. 위 표의 숫자는 현재 값이며 코드에 박지 않는다(7.7절)
- 적용 원천(`scope`)이 규칙마다 다르다 — `dtRecent` 염분에는 R1을 적용하지 않는다

### ③-11 `adapter_health` 기록 (4.9절)

- **`adapter_health` 갱신 규칙** (v1.5 4.5절 "헬스체크" 열) — `processor`가 원문 해석 결과로 기록한다
  - **성공** — `OK`·`OK_EMPTY`·`NO_DATA`: `last_success_utc` 갱신, `consecutive_failures` 초기화
  - **실패** — `HTTP_ERROR`·`NET_ERROR`(진짜 장애): `last_failure_utc` 갱신, `consecutive_failures` 증가
  - **별도** — `TIMEOUT_05`: 재시도로 복구되면 `retry_recovered`만 올리고 실패로 세지 않는다. 재시도 후에도 `05`면 실패와 같게 센다 *(제안)*
  - **어느 쪽도 아님** — `SUSPENDED`(무관), `PARSE_FAILURE`(검토 큐), `BAD_REQUEST`(우리 버그): 성공 시각을 갱신하지 않는다. v1.5 4.5절에 없는 `NO_SERVICE`·`KEY_ERROR`·`QUOTA`·`INCOMPLETE`·`FILTER_IGNORED`도 같게 둔다 *(제안)*. 그래서 파싱 실패가 이어지면 적조 축은 신선도 임계를 넘어 `STALE`이 된다 — 조용히 정상으로 남지 않는다

### ③-12 진입점 (2.1·6.1절)

- **`collector/main.py`** — 워크로드 명령(`collector-tide`·`collector-bulletin`·`collector-line`·`collector-fishery-watch`·`collector-fishery-backfill`·`collector-completeness`)마다 등록된 원천 어댑터를 부른다. **판정하지 않는다** — 원문과 요청 메타데이터만 남기고 `raw.fetched`를 발행한다. 수집 범위를 정하는 사전 읽기(결과 코드 존재, `totalCount`, 어장환경 올해 창 건수 — 직전 감시 원문의 메타 건수와 비교해 전량 수집 여부)만 허용하고, 그 결과를 상태 판정·적재에 쓰지 않는다
- **`processor/main.py`** — `process`: `raw.fetched` 소비 → 원문 읽기 → `classifier` → 원천 어댑터의 해석·정규화 → `completeness` → `quality` → 적재(DB 접근 계층 인터페이스) → `adapter_health` 갱신 → `obs.loaded`. `reprocess`: 원문 ID 범위를 다시 처리한다(파서 수정 후). 재처리할 때마다 `ingest_runs`에 행을 추가한다 — 고유 (`raw_id`, `parser_version`)이므로 같은 파서로 같은 원문을 다시 처리하면(중복 알림) 행이 늘지 않는다(5.3절)
- 단계 전용 코드끼리 import하지 않는다 — 진입점이 원천 어댑터를 부르는 것은 같은 이미지 안의 등록이다

### ③-13 운영 지표 (9절)

| 지표 | 라벨 |
| --- | --- |
| `collector_calls_total` | `api`, `status` |
| `collector_retry_total` | `api` |
| `collector_duration_seconds` | `api` |
| `raw_bytes_total` | `api` |
| `processor_parse_failure_total` | `api`, `parser_version` |
| `observation_latest_age_seconds` | `station_id`, `metric` |
| `observation_missing_ratio` | `station_id`, `metric` |
| `publication_check_total_count` | `axis`, `year` |
| `completeness_mismatch_total` | `api` |
| `pipeline_event_lag_seconds` | `topic` |
| `interpolation_run_duration_seconds` | — |
| `interpolation_error_p95` | `metric`, `station_set_key` |
| `interpolation_stations_used` | `farm_id` |
| `evaluation_state_total` | `axis`, `state` |
| `operational_config_info` | `image`, `hash`, `schema` |

- 사용자 화면에는 보내지 않는다 — 운영용이다

---

## ④ 이식 출처와 사용 금지 (6.3절)

검증 폴더는 별칭으로만 부르고 **읽기만** 한다. 이식할 때마다 `docs/SOURCES.md`에 `새 경로 | 출처 파일::함수 | 출처 파일 SHA-256 | 바꾼 점`을 남긴다.

| 새 경로 | 검증 코드 위치 | 처리 | 이식 시 반드시 바꿀 것 |
| --- | --- | --- | --- |
| `common/http/` | `$SRC_IDW/src/collector.py` `_request_with_retry()` | 참고 | 재시도는 `05`에만 1회. 실패 시 다른 창으로 대체하는 경로가 없어야 함 |
| | `$SRC_API/reverify_nifs.py` 호출층 | 참고 | 함수명 미확인 — I-1에서 확인 후 `docs/SOURCES.md`에 기록 |
| | `$SRC_API/check_tide_wtemp.py` `call()` | **사용 금지** | URL 문자열에 키를 직접 조립 (Encoding/Decoding 혼용 위험) |
| `common/raw_store/` | `$SRC_IDW/src/collector.py` `save_raw_response()` (B 수정본) | 참고 | 저장 대상을 로컬 파일 → 객체 저장소 인터페이스로 |
| | `$SRC_IDW/stage2_collect.py` `_save_raw()` | **사용 금지** | 수정 전에는 200,000자 절단. 형식도 확정본과 다름 |
| `common/classifier/` | `$SRC_C/probe.py` `ParsedResponse`, `_parse_json()`, `_classify()` 및 XML 파서 (수정사항 4 적용본) | **이식** | 빈 결과 코드 → `PARSE_FAILURE`, `totalCount>0`·item 0 → `PARSE_FAILURE`가 들어 있는지 확인. **없으면 이식 중단하고 보고** |
| | `$SRC_IDW/src/collector.py` `_parse_nifs()` | 참고 | NIFS `header`+`body` 계열 처리. 결과 코드 누락 시 동작 확인 |
| | `$SRC_IDW/stage2_collect.py` `parse_resp()` | 참고 | data.go.kr `dtRecent` 계열(최상위 `header` 포함) |
| | `$SRC_API/check_tide_wtemp.py` `parse()`, `CODE_MEANING` | 참고 | `OpenAPI_ServiceResponse` 에러 계열 분기와 코드 의미표 |
| `processor/completeness/` | `$SRC_IDW/stage2_collect.py` `_fetch_all_pages()`의 건수 대조부 | 참고 | 수령 건수 = `totalCount` 판정은 processor가 원문으로 다시 |
| | `$SRC_API/reverify_nifs.py` F2 분할 합산 | 참고 | **비교 범위 불일치 결함이 있던 로직.** 범위 일치 검사를 먼저 넣을 것 |
| | `$SRC_C/probe.py` 필터 수용 검사 | 참고 | 반환 행이 창 안인지 + `totalCount`가 전체 이력과 같은지 |
| `common/geo/` | `$SRC_API/verify_nifs_api.py` `DMS_RE`, `dms_to_decimal()` | **이식** | 특수 구분자 `°`·`´`·`˝` 처리 정규식 |
| | `$SRC_IDW/src/normalizer.py` `validate_coords_closed()` (B 수정본) | **이식** | 폐구간 |
| | `$SRC_IDW/src/normalizer.py` `validate_coords()`, `$SRC_IDW/src/config.py` `LAT_RANGE` | **사용 금지** | 개구간 — 위도 33.0 누락 |
| `processor/quality/` | — | 신규 | 기준은 ③-10 표(4.6절). 검증 코드 없음 |
| `common/queue/`, `common/metrics/`, `common/contract_check/`, `common/farm_sites/`, `collector/main.py`, `processor/main.py` | — | 신규 | |

- 이식 전에 `$SRC_IDW`의 `src/collector.py`·`stage1_verify.py`·`stage2_collect.py`가 **B 수정본**인지 확인한다 — 파일 수정 시각과 절단 코드(`[:100000]`·`[:200_000]`)가 없는지로(6.2절)
- 함수명이 "미확인"인 것은 추측으로 채우지 않는다 — 실제 파일에서 확인해 `docs/SOURCES.md`에 적는다

---

## ⑤ 함정

- **빈 결과 코드를 `"0"`으로 정규화해 정상 판정한 사고가 두 번 있었다.** 앞자리 0 정규화는 비어 있지 않은 숫자에만 한다. 결과 코드를 못 찾거나 비어 있으면 `PARSE_FAILURE`
- **HTTP 200이어도 장애일 수 있다.** `03`·`41`·`10`·`05`가 모두 200으로 온다. `resultMsg`도 믿지 않는다(`NORMAL SERVIE` 오타 실재)
- **형식은 요청 파라미터가 아니라 내용으로 판별한다** — `_type`을 안 보내 json 요청이 xml로 온 사례
- **공단 JSON은 루트가 오퍼레이션명**이고 결과 코드 키가 `header.code`, item·`totalCount`가 루트 직속이다. 모르는 파라미터를 에러 없이 무시하고 전 이력을 오래된 순으로 준다 → `00`이어도 필터 수용을 확인
- **같은 기관 안에서도 키 파라미터 대소문자가 다르다**(`ServiceKey`/`serviceKey`). 명세 그대로
- **빈 선택 파라미터를 보내면 `param=`으로 노출된다** — 보내지 않는다
- **XML은 `bytes`로 파싱한다** — `encoding` 선언 + `str` 입력은 ParseError. malformed 응답을 복구 파서로 살리지 않는다
- **원문을 파싱 결과로 재직렬화해 저장하면 `header`·쿼리 조건이 사라진다.** `body`는 `resp.text` 그대로. 자르지 않는다
- **키는 `final_url`에도 남는다**(NIFS는 쿼리에 키). 마스킹은 `url`·`params`·`final_url` 세 곳
- **파일명·객체 키에 `:`를 넣지 않는다** — Windows에서 잘린 사례
- **분할 합산은 범위부터 맞춘다** — 1년 창(9/24~)과 월 분할(10월~)을 그대로 비교해 "절단 확정"이 거짓으로 나온 사례(A 재검증 F2)
- **개구간 좌표 검증은 위도 33.0을 떨어뜨린다** — 남해 원문 523행 누락 사례
- **실패한 호출을 다른 기간·파라미터로 자동 대체하지 않는다** — 1주차 검증 스크립트가 작년 창으로 조용히 폴백했던 결함
- **거리 계산은 IDW 검증 코드와 같은 방식이어야 한다** — 다르면 `interpolation`의 F12 재현(P95 2.48)이 어긋난다. 방식은 `interpolation` skill의 이식 출처(`$SRC_IDW/src/idw.py`)에서 확인한다

---

## ⑥ 검사와 기대값

**음성 입력** (7.2절)

| # | 입력 | 기대 |
| --- | --- | --- |
| N1 | `{"foo": {"bar": 1}}` | `PARSE_FAILURE` |
| N2 | `{"response": {"header": {}, "body": {}}}` | `PARSE_FAILURE` (빈 결과 코드) |
| N3 | `resultCode: ""` | `PARSE_FAILURE` |
| N4 | `totalCount: 5`, item 0개 | `PARSE_FAILURE` |
| N5 | `OpenAPI_ServiceResponse` + `returnReasonCode: 05` | `TIMEOUT_05` (정상 스키마 파서가 `None`을 돌려주면 실패) |
| N6 | `resultCode: 12` | `NO_SERVICE`, 폐기 판정 없음 |
| N7 | 필터 창 2024년 요청, 1997년 행 반환 | `FILTER_IGNORED` |
| N12 | 분할 합산 — 단일 창(2025-09-24~)과 월 분할(2025-10~)처럼 **비교 범위가 다른** 두 결과 | 절단·`INCOMPLETE`로 판정하지 **않는다.** 운영 이벤트 `COMPARISON_RANGE_MISMATCH` + 검사 무효. A 재검증 F2 사고의 재현 방지 |
| N13 | 분할 합산 — 범위를 일치시킨 뒤에도 월 분할 합 < 단일 창 | `INCOMPLETE` + 운영 이벤트 |

**침묵 분류 계약 — 응답 해석 묶음** (7.3절)

| 묶음 | 분류 | 확인 단계 |
| --- | --- | --- |
| **7.3a 응답 해석** | 정상 / 정상적 침묵(`00`+0건) / 조건 불일치 / 일시 중단 / 타임아웃 / 요청 오류 / 파싱 실패 / 진짜 장애 / 필터 무시 / 빈 값 레코드 | S2 (`classifier`·`completeness`) — 빈 값 레코드는 S5 |

**판정 규칙 검사** (7.8절) — 이 skill 소유는 Q1~Q4·Q6 (Q5는 `tide`, Q7은 `interpolation`). 임계에 의존하는 것은 설정에 상대적으로 짠다

| # | 규칙 (절) | 입력 | 통과 기준 |
| --- | --- | --- | --- |
| Q1 | R3 물리 범위 (4.6) | 수온 −0.5 / 35.5 / 0.0 / 35.0 / 20.0 | 앞 둘만 `SENSOR_QUALITY`. 경계값 0.0·35.0은 정상 |
| Q2 | R4 급변 (4.6) | 1시간 변화 +5.5 ℃ / 같은 입력 + 태풍 특보 중 / +4.9 ℃ | 첫째만 `SENSOR_QUALITY`. 태풍 특보 입력은 합성 플래그로 준다(원천 미결 — 11절) |
| Q3 | R1 생물부착 (4.6) | 정선·어장환경 염분 30.9 / 하구 정점의 30.9 / `dtRecent` 염분 30.9 | 첫째만 `SENSOR_QUALITY`. 하구 예외 정점은 합성 목록으로 준다(목록 미결 — 11절). `dtRecent`에는 R1을 적용하지 않는다 |
| Q4 | R2 클로로필 급변 (4.6) | 10.5 & 직전 대비 +5.5 / 10.5 & +4.0 / 9.5 & +6.0 | 첫째만 `SENSOR_QUALITY` |
| Q6 | `adapter_health` 갱신 (4.9) | 순서대로 `OK` → `NET_ERROR` → `NET_ERROR` → `PARSE_FAILURE` → `OK_EMPTY`, 별도로 `05` 후 재시도 성공 | `last_success_utc`는 1·5번째에만 갱신, `consecutive_failures`는 0→1→2→2→0 (파싱 실패는 세지 않음). 재시도 복구는 `retry_recovered`만 1 증가 |

**기동 시 검사** (7.6절) — 이 skill 소유는 B6·B8. B3·B4는 이 skill의 코드가 만드는 동작이지만 I-10에서 돈다

| # | 검사 | 통과 기준 |
| --- | --- | --- |
| B3 | `grading`이 알림 계약 `queue-v2`로 발행, `evaluation`은 `queue-v1` | `evaluation`이 **처리하지 않고** 운영 이벤트를 남김. 결과 테이블 변경 0건 |
| B4 | 결과 테이블 계약이 DB와 다른 상태로 `evaluation` 기동 | 기동 멈춤 + 차이 보고 |
| B6 | 운영 조정 ConfigMap 없음 / 키 누락 / 모르는 키 / `<미결>` 자리 표시 / 스키마 버전 불일치로 `processor`·`evaluation` 기동 | 각각 **기동 멈춤 + 차이 보고.** `operational.initial.yaml`이나 기본값으로 떠오르면 실패 |
| B8 | 기동 성공 | `ops_events`에 `OPERATIONAL_CONFIG_LOADED`와 설정 해시 1건 |

---

## ⑦ 주인이 아닌 사실 — 참조만

| 사실 | 주인 |
| --- | --- |
| 상태 이름표, 결과 테이블 필드 의미, 설정 3종, `_utc` 규칙 | `CLAUDE.md` 6절 |
| DB 접근 계층 구현, 방언 분기, 테이블 모델 | `repository` |
| 원천별 요청주소·파라미터·해석·정규화, 분할 수집 코드 | `tide`·`bulletin`·`line`·`fishery` |
| 값 멈춤 감지 규칙(`STALE_SUSPECT`, 4.1절)과 그 검사 Q5 | `tide` |
| 운영 조정 판정 재생(`evaluation gate`), 신선도 임계 판정 | `evaluation` |
| `none_reason` 값 목록 | `grading` |
| 거리 계산 방식의 출처 | `interpolation` |

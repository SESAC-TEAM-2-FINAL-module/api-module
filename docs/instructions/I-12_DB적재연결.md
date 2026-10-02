# I-12 — collector·processor DB 적재 연결 (S7 보완)

작성 2026-10-01 · 근거 `docs/reports/review_20261001_rev10.md` "권장 순서 3 — 남은 문제 1~4"

---

## 0. 머리말

| 항목 | 내용 |
| --- | --- |
| 번호 | **I-12** |
| 대상 단계 | **S7 보완** — 10절 "S3~S6은 정규화 결과(메모리)까지 검증한다. **DB 적재는 S7에서 붙이고**, 7.4 DB 검사로 같은 픽스처를 다시 확인한다". A.6의 I-6 산출물에는 이 연결이 빠져 있었다(`common/repository/`·DDL만). 그 결과 운영 코드에서 테이블 쓰기 호출처가 0이다 |
| 선행 | I-1~I-11, 2026-10-01 코드 수정(A1·A3~A6·A8 — 미커밋분 포함) |
| 적용 수정사항 | 없음 |
| 공공 API 호출 | **금지** |
| 읽을 skill | `common-core`(③-5 원문 저장, ③-6 단계 간 알림, ③-9 기동 시 검사, ③-11 `adapter_health`) · `repository`(테이블 키 = upsert 멱등 키, 타입 규칙, 기동 시 검사). 행 형식은 각 원천 skill(`tide`·`bulletin`·`line`·`fishery`)의 ③절만 확인한다 |
| 계획서 근거 | 2.1(역할), 2.2(알림), 2.3(원문 저장), 2.0.3(기동 시 테이블 검사), 4.3(`unmapped_locations`), 4.5(`publication_checks`), 4.9(`adapter_health` 갱신 규칙), 5.3(테이블), 7.4(DB 검사), 7.8 Q6 |

### 0.1 전달 전 조건 — 계획서 개정 12

계획서 개정 12(2026-10-01)가 A.6 목록에 I-12 행을, 10절 S7에 I-12를 넣었고, 0.2 결정 D1~D6을 2.1·2.2·2.3·4.9·5.3·6.1절에 반영했다. skill은 같은 작업에서 `common-core`·`repository`·`evaluation`·`fishery`를 갱신했다(`CLAUDE.md`는 해당 없음). ~~개정 12가 커밋된 뒤에 실행한다 — 확인 게이트에서 커밋 해시를 적는다.~~ **일시 중단**(2026-10-01 사용자 지시) — 커밋은 작업 공유용 initial commit만 있고 이후 커밋은 보류한다. 확인 게이트는 커밋 대신 **작업 트리의 계획서 개정 12 문구**로 확인한다.

### 0.2 실행 전 결정 — **확정 (2026-10-01 사용자 허가 — 전부 권고안)**

계획서와 v1.5(12.1절 C안·13절 데이터 모델 스케치) 어디에도 값이 없던 것이다. **확정안: D1-B · D2-A · D3-A · D4-A · D5-A · D6 응답 상태.** 실행자는 이 안으로만 구현한다. 아래 표의 다른 안은 기록으로만 남긴다.

| # | 결정할 것 | 안 | 권고 · 근거 |
| --- | --- | --- | --- |
| **D1** | `raw_index` 행을 누가 쓰고, `raw.fetched`의 `raw_id`가 무엇인가. 현재 코드는 `raw_store`의 객체 키(문자열)를 `raw_id`로 쓰고, 5.3절은 `ingest_runs.raw_id`·관측 테이블 `raw_id`를 `raw_index.id`(BigInteger)로 둔다 | **A** collector가 `insert_raw_index()` → `raw.fetched.raw_id = str(raw_index.id)` / **B** processor가 원문 메타로 `insert_raw_index()`(고유 `storage_key`라 멱등) → 받은 id를 적재에 씀. `raw.fetched.raw_id`는 객체 키 그대로 | **B 권고** — collector 매니페스트 6종에 `DATABASE_URL`이 없다(`handoff/k8s/collector-*.yaml`). A는 인계 매니페스트 변경(인프라 요청)이 필요하다. B는 계약 `queue-v1`(`raw_id: string`)과 현재 코드를 그대로 둔다. 단 `precheck_code`(collector 사전 읽기 결과)는 원문 메타에 있어야 한다 |
| **D2** | `raw_index.api`·`adapter_health.adapter`의 값. collector·raw 키는 api_id(`dtRecent`…), evaluation은 수집 원천(`tide`…)으로 찾는다(`evaluation/_state.py` `AXIS_ADAPTER`, `sql.py` `get_latest_ingest_result_by_adapter`) — **지금은 둘이 만나지 않는다** | **A** `raw_index.api` = api_id, `adapter_health.adapter` = 수집 원천, evaluation 조회가 원천→api_id로 대응 / **B** 둘 다 수집 원천 | **A 권고** — 2.2절이 `api`(api_id)와 `source`(수집 원천)를 나눠 쓰고, 5.3 `stations.source_api` CHECK가 수집 원천이다. 한 원천에 api_id·tag가 여럿(`femoSeaList` 감시·백필·완전성)이라 원천 단위 헬스가 맞다 |
| **D3** | 어장환경 R1·R2 `SENSOR_QUALITY`를 저장할 곳. 5.3 `survey_observations`에 `flags` 열이 없다(`observations`·`line_observations`에는 있다) | **A** `survey_observations.flags`(JSON, nullable) 추가 / **B** 저장하지 않음(어장환경 품질 판정은 메모리에서만) / **C** v1.5 13절 `observation_quality` 테이블 | **A 권고** — 다른 관측 테이블과 같은 형태. B는 grading 클로로필이 `SENSOR_QUALITY` 값을 거르지 못한다. C는 제작계획서가 이미 `flags` 열 방식으로 옮겼다 |
| **D4** | `adapter_health.retry_recovered` 타입. `tables.py`는 Boolean, 계획서 7.8 Q6은 "1 증가", v1.5 12절은 "복구 건은 … 별도 카운터" | **A** Integer(횟수) / **B** Boolean 유지(최근 복구 여부) | **A 권고** — 두 원천이 모두 횟수. `processor/_health.py`는 이미 정수로 센다 |
| **D5** | `stations`(관측소 마스터 — grading 최근접·interpolation 좌표가 읽음)를 누가 채우는가. 운영 코드에 쓰는 곳이 없고, 계획서에 주체가 없다 | **A** processor가 원문의 좌표로 upsert(조위 `obsCode`·위경도, 정선·어장환경 정점 좌표) / **B** 시드 파일(`fixtures/derived/stations.csv` 형식)로 적재 | **A 권고** — 원문마다 좌표가 있고(조위 경도 필드 `lot`, 어장환경 도분초), 정점이 바뀌어도 따라간다. `active`는 `STATION_INACTIVE`로 갱신 |
| **D6** | `ingest_runs.status` 값 | 응답 상태(3.2절, `PARSE_FAILURE`·`OK_EMPTY` 등) / 그 밖의 값 | 응답 상태 권고 — evaluation이 `result_code`·`status`로 3번 묶음을 판정한다(4.9절) |

D3·D4는 테이블 정의(`tables.py`·DDL 제안) 변경이다. **운영 DB에는 아직 적용된 스키마가 없으므로**(2.0.3절 — DB 소유 측 미정) 마이그레이션이 아니라 **정의 제안의 수정**이다. 그래도 5.3절이 바뀌므로 개정 12에 들어가야 한다.

---

## 1. 작업

경로는 `src/api_module/` 기준.

### 1.1 원문 색인 (D1)

- (확정 D1-B) `processor/_load.py`가 원문 메타로 `raw_index` 행을 만든다: `api`(D2), `tag`, `storage_key`(= 객체 키), `fetched_at_utc`, `http_status`, `body_sha256`, `body_bytes`, `precheck_code`. 받은 `id`를 이 원문의 모든 적재 행 `raw_id`로 쓴다
- 어느 쪽이든 원문 본문은 DB에 넣지 않는다(2.3절)

### 1.2 processor 적재 — `processor/_load.py` (신설)

`processor/main.py` `_process_one()`의 주석 처리된 적재 줄을 이 모듈 호출로 바꾼다. 순서: 해석 → 정규화 → 완전성 → 품질 → **적재(한 트랜잭션)** → `obs.loaded`. 적재가 실패하면 알림을 내지 않는다.

| api_id | 테이블 | 메모 |
| --- | --- | --- |
| `dtRecent` | `observations` | 행 = (station, 시각, metric). `flags` 그대로 |
| `sooList` | `line_observations` | `depth_m`·`cast_id`·`cast_rule_version`·`group_type`. 내부 키(`_is_blank_record` 등)는 넣지 않는다 |
| `femoSeaList` | `survey_observations` | `flags`는 D3 결과에 따름 |
| `femoSeaList`(감시) | `publication_checks` | 4.5절. PK `raw_id` |
| `redtideList` | `bulletins`·`bulletin_details`·`bulletin_detail_areas`, `unmapped_locations` | `tests/db/test_counts.py`의 `_write_bulletin_rows()`를 이 모듈로 옮기고 테스트는 운영 코드를 부른다. `unmapped_locations`는 같은 키면 횟수·마지막 시각만 갱신(4.3절) — stderr 로깅을 DB 적재로 전환(4.3절 *(제안)*) |
| 공통 | `ingest_runs` | `raw_id`, `parser_version`, `status`(D6), `result_code`, `total_count`, `item_count`, `format`, `format_mismatch`, `processed_at_utc`. 고유 (`raw_id`, `parser_version`) |
| 공통 | `stations` | D5 — 원문 좌표로 upsert. 조위는 경도 필드 `lot`(1.2절)을 원문에서 읽는다. **`docs/SOURCES.md` 17행**("`lot` 경도 필드는 stations.csv에서 읽으므로 어댑터 불필요")은 이 결정과 반대이므로 같은 작업에서 고친다 |
| 공통 | `ops_events` | `CAST_RULE_ASSUMPTION_BROKEN`(정선), `OPERATIONAL_CONFIG_LOADED`(기동 — 설정 해시, 2.0.6절) |

- 행을 테이블 열로만 거른다(열 이름은 `tables.py`가 기준). 거르다가 **값이 있는 열이 버려지면** 운영 이벤트로 남긴다 — 조용히 버리지 않는다
- 시각은 초 단위 UTC naive(`repository` skill 타입 규칙)
- `0.000`·빈 값 행도 적재한다(결측으로, 12절)

### 1.3 `adapter_health` (4.9절, D2·D4)

- 적재와 같은 트랜잭션에서 `processor/_health.py` `next_adapter_health()`로 다음 행을 만들어 upsert. 직전 행은 `get_adapter_health()`로 읽는다
- 재시도 여부는 원문 메타의 `_retried`(`common/http/_client.py`가 기록)
- 키는 D2 결과

### 1.4 기동 시 검사 (2.0.3절)

- `processor.main.startup()`이 repository를 만들고 `check_schema()`를 부른다. 테이블이 없거나 정의와 다르면 멈추고 차이를 보고한다(스스로 만들지 않는다)

### 1.5 evaluation 조회 (D2)

- (확정 D2-A) `get_latest_ingest_result_by_adapter()`가 수집 원천 → api_id 대응으로 `raw_index.api`를 찾게 고친다. 대응표는 한 곳(`common/`)에 둔다 — processor의 `_SOURCE_OF_API`와 `processor/quality/_rules.py`의 대응표를 그 하나로 합친다(단계 전용 코드끼리 가져다 쓰지 않는다, 12절)

### 1.6 테이블 정의 (확정 D3·D4)

- `common/repository/tables.py`와 `contracts/tables/schema_pg.sql`·`schema_my.sql` 생성본을 같이 고친다. 생성본은 손으로 고치지 않고 생성 함수로 다시 만든다
- 마이그레이션은 만들지 않는다

---

## 2. 통과 기준

### 2.0 픽스처 검증 — 구현 전 관문

- `fixtures/raw/`의 F1~F10 원문이 `fixtures/MANIFEST.csv` 해시와 같다. 다르면 멈춘다
- **판별력 점검**: 2.1의 신설 검사를 **현재 코드(적재 미연결)에서 먼저 돌려 실패하는 것**을 확인하고 보고서에 남긴다. 실패하지 않으면 검사가 무효다 — 멈추고 보고한다

### 2.1 검사

| # | 검사 | 판정 기준 | 전제 · 비교 범위 |
| --- | --- | --- | --- |
| 7.4 필수 | DB에 쓰는 검사 전체 — F1~F10을 **processor 경로로**(`raw_store` 로컬 디스크 → `processor.process()` → 고른 DB) 적재 | 테이블별 건수 = `ci/gate/expected.yaml` `counts` | 기존 `tests/db/test_counts.py`는 어댑터 → repository를 직접 불렀다. 이번에는 진입점을 통과해야 한다 |
| L1 | 멱등 — 같은 `raw.fetched`를 두 번 처리 | 관측 테이블 행 수 동일, `ingest_runs` 1행, `raw_index` 1행 | 2.2절 "같은 알림이 두 번 와도 결과가 같아야 한다" |
| L2 | 재처리 — `parser_version`을 바꿔 `reprocess` | `ingest_runs` +1행, 관측 행 수 동일(같은 키로 upsert) | 5.3절 `ingest_runs` 고유 키 |
| L3 | Q6 DB판 — 7.8 Q6 순서를 원문으로 넣어 처리 | `adapter_health` 행이 Q6 기대값과 같다 | `retry_recovered`는 D4 타입으로 |
| L4 | 적재 실패 시 알림 없음 — repository가 예외를 내게 한 뒤 처리 | `obs.loaded` 0건, 부분 적재 0행 | 한 트랜잭션 |
| L5 | 기동 시 테이블 검사 — 테이블 하나를 뺀 DB로 `startup()` | 멈추고 빠진 테이블 이름 보고 | 7.4 필수 "기동 시 검사" |
| L6 | 파이프라인 연결 — `dtRecent` 픽스처 → processor → `obs.loaded` → interpolation → `interp.done` → grading → `grade.done` → evaluation | `farm_readings`·`axis_status`에 합성 양식장 행이 생긴다. 수온 행 `derivation = COMPUTED`·`alertable = false`(N11) | `farm_sites`는 테스트 컨테이너에만 합성으로 만든다(웹 소유 — 운영 스키마 아님, 2.0.3절). 큐는 `MemoryQueue` |
| L7 | evaluation 조회 대응 (D2) | `get_latest_ingest_result_by_adapter("tide")`가 L6에서 적재한 `ingest_runs` 행을 찾는다 | — |
| 회귀 | 기존 전체 | `pytest` 전부 통과(현재 364 passed / 13 skipped), 게이트 통과, `ci/scan_keys.py` 0건 | — |

- 7.4 선택 검사(`TEST_DATABASE_URL_ALT`)는 있을 때만 돌린다

---

## 3. 순서 · 중단 조건 · 확인 게이트

1. **확인 게이트** — ~~0.1 개정 12가 커밋됐는지 확인(해시 기록)~~ **일시 중단**(커밋 보류 — 0.1). 작업 트리의 계획서 머리말에 개정 12가 있는지 확인. 계획서 5.3절의 `survey_observations.flags`·`retry_recovered` 정수·`raw_index` 작성 주체 문구가 이 지시서 0.2 확정안과 같은지 대조. 다르면 멈춘다
2. 2.0 픽스처 검증 → 판별력 점검(현재 코드에서 L1~L7 실패 확인)
3. 1.6(D3·D4) → 1.1 → 1.2 → 1.3 → 1.4 → 1.5 순서. 각 단계 뒤 회귀를 돌린다
4. L1~L7, 7.4 필수 실행

**중단 조건**

- 건수가 `expected.yaml`과 다르다 → **어느 쪽도 고치지 않고** 멈춰 차이(단계·건수)를 보고
- 어댑터 행에 테이블에 없는 값이 있는데 버릴지 정해지지 않았다 → 멈춤
- 정해지지 않은 결정(D1~D6)이 구현에 필요해졌다 → 그 항목에서 멈춤
- 공공 API 호출이 필요해 보인다 → 멈춤(금지)

---

## 4. 산출물

| 경로 | 구분 |
| --- | --- |
| `processor/_load.py` | 신설 |
| `processor/main.py` | 적재·기동 시 검사 연결 |
| `common/`의 원천 ↔ api_id 대응표 (위치는 `common-core` skill 구조에 맞춤) | 신설 · 기존 두 대응표 통합 |
| `common/repository/sql.py`(`get_latest_ingest_result_by_adapter` 등) | 수정 |
| `common/repository/tables.py`, `contracts/tables/schema_pg.sql`·`schema_my.sql` | D3(`survey_observations.flags`)·D4(`retry_recovered` Integer) |
| `tests/db/test_processor_load.py`(L1~L5, 7.4 processor 경로), `tests/db/test_pipeline_chain.py`(L6·L7) | 신설 |
| `tests/db/test_counts.py` | `_write_bulletin_rows` 이관에 맞춰 수정 |
| `docs/SOURCES.md` | 17행 `lot` 기록 정정 (D5) |
| `docs/reports/I-12_result.md` | 보고서 |

- 기존 파일을 고치기 전후로 크기·수정 시각을 보고서 0절에 적는다

---

## 5. 보고 양식

계획서 A.5 보고 양식을 따른다. 실행 시각 / 호출 수(0) / 적용 수정사항(없음) / **참조한 skill**(~~그 커밋~~ **일시 중단** — 커밋 보류 중이므로 "작업 트리, HEAD `59e263a` + 미커밋"으로 적는다). 4절 "계획서 반영 후보"에는 다음을 반드시 적는다.

- D1~D6이 실제 구현에서 맞았는지(다른 절과 충돌이 있었는지)
- 열 필터로 버려진 값이 있었는지
- L6에서 드러난 다른 단계의 연결 결함(있으면 고치지 말고 기록)
- R2·R4 직전 값의 DB 조회(계획서 4.6·11절, 개정 13)는 **이 지시서 범위가 아니다** — 후속 지시서에 필요한 읽기 메서드 형태만 제안한다

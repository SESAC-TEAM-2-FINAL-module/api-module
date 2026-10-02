# I-12 결과

실행 시각 2026-10-01 · 호출 수 **0**(공공 API 호출 없음) · 적용 수정사항 없음
참조한 skill: `common-core`, `repository` — 작업 트리 기준(HEAD `59e263a` + 미커밋. 커밋 확인 게이트는 사용자 지시로 **일시 중단**, 지시서 0.1)
지시서: `docs/instructions/I-12_DB적재연결.md` · 결정 D1-B · D2-A · D3-A · D4-A · D5-A · D6(응답 상태)

---

## 0. 실행 전 확인

| 항목 | 결과 |
| --- | --- |
| 로컬 배치(2.0.7절) | `CLAUDE.md`·skill·계획서·`.env`·`.env.sources` 있음(내용 미열람) |
| 확인 게이트 | 커밋 해시 대신 작업 트리 확인(일시 중단). 계획서 머리말에 개정 12·13 있음. 5.3절 `survey_observations.flags`·`retry_recovered` 정수·`raw_index` processor 작성 문구가 지시서 0.2 확정안과 같음 |
| 2.0 픽스처 검증 | `fixtures/MANIFEST.csv` 28행 중 저장소 안 27개 SHA-256 **일치**, 1개는 저장소 밖 참조(`$SRC_IDW/output/observations.csv`)라 대상 아님 |
| 판별력 점검 | 적재를 끊은 상태(`processor.main.load` 무력화 — I-12 이전과 같음)에서 신설 DB 검사 14개 중 **13개 실패**, 1개(L5 기동 시 테이블 검사)는 적재와 별개 기능이라 통과. 처음 돌렸을 때 검토 큐 검사가 빈 집합 = 빈 집합으로 통과해 **"비어 있지 않음" 조건을 추가**한 뒤 실패 확인 |
| 기존 파일 보호 | 실행 전 크기·시각을 따로 기록하지 않았다 — 변경은 `git diff`로 대조 가능(HEAD 기준). 덮어쓴 파일 없음, DDL 생성본 2개는 생성 함수로 다시 만듦 |

## 1. 판정표

| 검사 | 결과 | 비고 |
| --- | --- | --- |
| 7.4 필수 — 어장환경 2023·2024·2025를 processor 경로로 (`stored` 1008·1020·1022) | **실패 → 중단 조건, 보고** | 적재 1000·1012·1014. 원문에 **완전 중복 레코드 8건**(연도마다, 모두 `임원` 어장)이 있어 PK(정점·조사일·층·항목)로 합쳐진다. 기준·코드 어느 쪽도 고치지 않음 — `xfail(strict)`로 표시(2절) |
| 〃 — 중복을 뺀 원문 레코드 전량 적재 | 통과 | 연도마다 distinct 레코드 × 6행 = 적재 행 수 — 적재 단계에서 빠지는 행 없음 |
| 〃 — 백필 원문(`femoSeaList-backfill`) | 실패(위와 같은 원인) → `xfail` | 백필 원문이 같은 해석으로 적재됨은 확인(이전에는 등록된 어댑터가 없어 버려졌다 — 2절) |
| 〃 — 어장환경 2026 감시(`publication_check_rows` 1, `OK_EMPTY`) | 통과 | `target_year`는 tag `watch_2026`에서 |
| 〃 — 적조 R1(`stored_bulletins` 51, `details` 50, `item2_missing_unknown` 1) | 통과 | |
| 〃 — 적조 R3(`outer` 15, `not_graded` 10, `detail_area_parts` 20) | 통과 | |
| 〃 — 검토 큐 = 해역 미대응 지점 집합 | 통과 | R1 4개·R3 15개 키 |
| 〃 — 정선 v2(행 ÷ 3 = `raw` − `coord_excluded` = 9,416) | 통과 | 수심 없는 행으로 건너뛴 행 0 |
| L1 중복 알림 멱등 | 통과 | 관측·`ingest_runs`·`raw_index`·검토 큐 횟수·`adapter_health` 모두 그대로 |
| L2 재처리(`parser_version` 변경) | 통과 | `ingest_runs` +1, 관측 행 수 같음, `adapter_health` 다시 세지 않음 |
| L3 Q6 DB판 | 통과 | `consecutive_failures` 0→1→2→2→0, 성공 시각 1·5번째만, 키 `tide`(D2), 재시도 후 성공 `retry_recovered` 1(D4), `ingest_runs.status` 응답 상태(D6) |
| L4 적재 실패 시 알림 없음 | 통과 | 예외 주입 시 `obs.loaded` 0건, 5개 테이블 0행(한 트랜잭션) |
| L5 기동 시 테이블 검사 | 통과 | `adapter_health`를 뺀 DB → 멈추고 이름 보고 |
| L6 단계 연결(수온 경로) | 통과 | dtRecent 원문 → processor → interpolation(`interp.done`) → grading(수온 `farm_readings`, `COMPUTED`·`alertable=false`·값 저장) → evaluation(`axis_status`, `result.updated`) |
| L6 — grading `obs.loaded` 경로의 `grade.done` 계약 | **실패 → 기록(다른 단계 결함, 고치지 않음)** | `xfail(strict)` — 2절 |
| L7 원천 → api_id 대응 조회 | 통과 | `get_latest_ingest_result_by_adapter("tide")`가 dtRecent 처리 기록을 찾음 |
| 회귀 | 통과 | `pytest` **387 passed / 13 skipped / 5 xfailed**(이전 370 / 13 / 0), 게이트(`--warn-pending`) 통과 — 경고 `quality.r1_estuary_stations` 1건, `ci/scan_keys.py` 0건 |
| 7.4 선택(두 DB 비교) | 실행 안 함 | `TEST_DATABASE_URL_ALT` 없음. MySQL 분기(`dialect.py` 분할 업서트 포함)는 실행 검증 안 됨 |

## 2. 예상과 달랐던 결과

| API 특성 | 우리 코드·명세 결함 |
| --- | --- |
| **`femoSeaList` 원문에 완전 중복 레코드** — 2023·2024·2025 각 8건, 모든 필드 동일, 전부 `임원` 어장. `expected.yaml`의 `stored = raw`(1008 등)는 원문 항목 수라 PK 적재 결과와 다르다 | **PostgreSQL 바인드 매개변수 한도(65,535)** — 정선 1년 원문(약 2.8만 행 × 11열)을 한 문장으로 보내 실패. `dialect.py` `upsert()`를 6만 매개변수 단위로 나눠 보내게 고침 |
| | **grading `handle_obs_loaded`의 `grade.done`** — `axis = "obs.loaded"` 고정, `schema`·`topic` 없음(계약 `queue-v1` 위반). evaluation이 `axis_status` CHECK에 걸린다. **고치지 않고 기록**(L6 `xfail`) |
| | **grading·interpolation 실행 진입점** — `EnvConfig`에 없는 `env.database_url`을 읽는다(`database_url_var`만 있음). `python -m grading.main` 등으로 기동하면 실패할 것. 고치지 않고 기록 |
| | **evaluation의 `farm_sites.area_id`** — evaluation이 `area_id`로 커버리지·계절을 보지만 `get_farm_sites()` SQL이 이 열을 고르지 않는다. 커버리지 밖·계절 밖 판정이 운영에서 일어나지 않는다(I-9 보고 "남은 한계"와 같은 사실). 고치지 않고 기록 |
| | **등록된 어댑터 없는 원문** — `femoSeaList-backfill`(백필)은 처리되지 않고 버려졌다 → 같은 해석 어댑터로 대응(`_ADAPTER_ALIAS`). `*-completeness`(분할 합산)는 여전히 받을 곳이 없다 — 3.3절 비교가 운영에서 돌지 않음 |
| | **collector** — ① tide 다중 페이지를 합쳐 재구성한 본문으로 저장(2.3절 "페이지별 저장" *(제안)*과 다름) ② fishery 감시 `raw.fetched`에 계약 밖 키(`target_year`·`prev_total_count`·`total_count`) ③ 직전 감시 건수 읽기가 stub(`None`) ④ `05` 재시도가 결과 코드 `05`가 아니라 HTTP 타임아웃 재시도 ⑤ `precheck_code`를 메타에 남기지 않음 |
| | **적조 세부 행의 `min_watertemp`·`max_watertemp`** — 어댑터가 만들지만 5.3절 `bulletin_details`에 열이 없다. R1+R3에서 61행씩 값이 있다 → 조용히 버리지 않고 `ops_events.LOAD_COLUMNS_DROPPED`로 기록 |
| | **검토 큐 `OUT_OF_SCOPE`** — 판별 규칙이 없어 전부 `PARSE_FAILED`. 별칭 시드 `산양읍 장군봉 내만`이 있는데 분리 후 키 `장군봉 내만`은 미매핑으로 나온다(정규화·분리 결과와 별칭 키가 어긋남) |
| | DDL 생성본 재생성 시 `provenance` CHECK에 `BASELINE`이 함께 들어갔다 — 2026-09-30 `tables.py` 수정(V-1) 뒤 생성본을 다시 만들지 않았던 것 |

## 3. 새로 발견한 함정

- **한 문장 대량 INSERT는 매개변수 한도에 걸린다.** 정선 1년 원문이 실제로 넘는다. 분할은 `dialect.py`에서만 한다
- **빈 집합 비교는 판별력이 없다.** "적재된 X = 기대 X"가 둘 다 비어도 통과한다 — 집합이 비어 있지 않음을 함께 단언해야 한다(검토 큐 검사에서 실제로 발생)
- **원문 완전 중복** — 항목 수와 PK 적재 수가 다를 수 있다. 원문 건수 기준(`raw`)과 적재 기준(`stored`)을 구분해야 한다

## 4. 계획서 반영 후보

**결정 D1~D6 검증** — 구현에서 다른 절과 충돌 없음. 다만 D1(processor가 `raw_index` 작성)은 `precheck_code`를 collector가 메타에 남겨야 완성된다(2절 collector ⑤).

**구현한 *(제안)*·해석**

| 항목 | 내용 |
| --- | --- |
| HTTP 타임아웃 → `NET_ERROR` | 원문 메타 `error.type = TIMEOUT`(호출 타임아웃)은 결과 코드 `05`(`TIMEOUT_05`)와 다르므로 연결 실패로 본다 — 3.2절에 명시 검토 |
| 재시도 후 성공 → `retry_recovered` +1 | v1.5 12절 "복구 건은 실패로 세지 않되 별도 카운터". 4.9절은 `TIMEOUT_05` 복구만 적었다 |
| 완전성 결과를 응답 상태로 | 해석이 `OK`이고 완전성이 `INCOMPLETE`·`FILTER_IGNORED`면 `ingest_runs.status`를 그 값으로(D6 해석) |
| 재처리 시 헬스·검토 큐 횟수 미갱신 | 같은 원문의 재처리(파서 버전 변경)는 새 호출이 아니므로 다시 세지 않는다 |
| 검토 큐 `kind` | 전부 `PARSE_FAILED` — `OUT_OF_SCOPE` 판별 규칙 필요(4.3절) |

**계획서 결정이 필요한 것**

| 항목 | 제안 |
| --- | --- |
| 어장환경 원문 완전 중복 | `expected.yaml` `femo_*`에 `stored`(PK 적재 수 1000·1012·1014)와 `raw`(1008·1020·1022)를 구분해 둘지, 또는 중복을 운영 이벤트로 남길지 — 7.7절 counts·4.5절 |
| `bulletin_details` 수온 열 | `min_watertemp`·`max_watertemp`를 5.3절에 넣을지, 어댑터에서 만들지 않을지 |
| R2·R4 직전 값 DB 조회(개정 13 후속) | 읽기 메서드 두 개를 제안: `get_observations_in_window(station_id, metric, from_utc, to_utc)`(R4 — `observations`), `get_previous_survey(station_id, layer, metric, before)`(R2 — `survey_observations`). 둘 다 `transaction()` 안에서 부를 수 있다(이번에 `SqlRepository.transaction()` 추가) |
| 다른 단계 결함 | grading `grade.done`, grading·interpolation `env.database_url`, evaluation `farm_sites.area_id`, `*-completeness` 소비자, collector ①~⑤ — 각 원천·단계 지시서의 수정사항 대상 |

---

## 추기 — 계획서 개정 14 후 재실행 (2026-10-01)

- 사용자 결정: 원문 완전 중복은 합치는 것이 맞다(값·출력에 영향 없음). 대시보드 시간축을 위해 **어장환경 조사 시각을 키로**(B안) — `TIME_H`·`TIME_I`는 KST 확정
- 기준 문서 `femo_*`에 `loaded`(DB 적재 1000·1012·1014) 추가 — `raw`·`stored`(정규화 1008·1020·1022)는 그대로. 7.4 어장환경 검사가 `loaded`로 **통과**(xfail 해제)
- 픽스처 집계: 같은 정점·같은 날 다른 시각 조사 0건, 같은 키·다른 값 0건, 시각 결측 0건
- 결과 테이블 계약 `tables-v2` — DO·클로로필 `source_ref` = `station_id@observed_at_utc`, 클로로필 `farm_readings.observed_at_utc`에 조사 시각(전에는 비어 있었다)
- 재실행: `pytest` **401 passed / 13 skipped / 1 xfailed**(grading `grade.done` 결함 기록 1건), 게이트 통과, `scan_keys` 0건

---

## 추기 — L6 결함 수정 (2026-10-01)

| 결함 | 수정 |
| --- | --- |
| grading `obs.loaded` 경로 `grade.done` — `axis = "obs.loaded"` 고정, `schema`·`topic` 없음 | 갱신한 축마다 `grade.done` 하나(`_publish_grade_done`), 두 경로 모두 `queue-v1 grade_done` 계약 필드. L6 `xfail` 해제 — 계약 스키마 검증 통과, evaluation이 수온·염분·물때·풍속·기온 등 축마다 `axis_status`를 쓴다 |
| grading·interpolation 진입점 `env.database_url`(없는 속성)·수집용 URL 요구 | `common.config.database_url()` — `DATABASE_URL`만 읽고 없으면 멈춘다. processor도 같은 함수 |
| 진입점 ↔ 인계 매니페스트 명령 불일치 | evaluation: 명령 없음·`evaluate`(컨슈머), `sweep`(1회), `gate`. interpolation: `error`(매니페스트) = `interpolation-error`. processor: 명령 없음 = `raw.fetched` 컨슈머. 매니페스트는 고치지 않았다(인계물) |

재실행: `pytest` **412 passed / 13 skipped / 0 xfailed**, 게이트 통과, `scan_keys` 0건.

**남은 것 (고치지 않음 — 계획서·인프라 결정 필요)**

- evaluation의 `farm_sites.area_id` — 계획서 1.6·5.3절 `farm_sites` 계약 열(`farm_id`·`lat`·`lng`·`active`·`updated_at_utc`)에 `area_id`가 없다. 커버리지 밖·계절 밖 판정의 입력이 계약에 없는 것 — 계약에 넣을지, 모듈이 좌표 → `areas`로 해역을 정할지 결정 필요
- processor `reprocess` — 매니페스트는 `--raw-id-from`·`--raw-id-to`(범위), 코드는 `reprocess <api> <raw_id…>`(목록). 범위 지정 방식(키 범위 / `raw_index.id` 범위)이 계획서에 없다
- 모든 컨슈머가 `MemoryQueue` — 큐 구현(NATS / SQS)이 v1.5 미결이라 운영 컨슈머는 실제로 메시지를 받지 않는다
- `*-completeness` 소비자 없음, collector 5건(2절) — 그대로

## 추기 — 남은 것의 처리 (2026-10-01)

| 위 "남은 것" | 처리 |
| --- | --- |
| evaluation의 `farm_sites.area_id` | 계획서 개정 15 — 모듈이 반경 안 최근접 중심으로 해역을 정해 `farm_areas`로 기록 |
| processor `reprocess` 범위 | 개정 15 — `raw_index.id` 범위(`--raw-id-from`·`--raw-id-to`) |
| `MemoryQueue` | 미결 유지(개정 15) — 인프라 리전 동작 시험 후 큐를 붙인다 |
| `*-completeness` 소비자 없음 | 개정 17·보완 — 분할 원문은 `raw.fetched`를 내지 않고 검사기(`processor.main completeness-check`)가 `completeness.collected`를 받아 원문 저장소에서 직접 읽는다. `PENDING_APIS`는 비었다 |
| collector 5건 | 진입점·실패 원문 보관은 개정 16에서 수정. 남은 4건은 대기 |

최종: `pytest` **461 passed / 13 skipped**, 게이트 통과, `scan_keys` 0건. 상세는 `revision_data.md` 개정 15~17.


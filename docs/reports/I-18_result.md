# I-18 결과 보고서 — 단계 연결: NATS JetStream 큐 · S3 원문 저장소 · `queue-v2` · 조위 한 페이지

| 항목 | 내용 |
|---|---|
| 실행 | 2026-10-06~10-07. 첫 구현은 피어 세션(`aquasentinal-api-module-7c`·`-a8`), **검수 뒤 수정·검사·이 보고서는 작업 세션**(2026-10-07 세션 (5)·(6)) |
| 공공 API 호출(T4) | **3회 / 예산 5회**(2026-10-07, 사용자 허락 뒤 작업 세션이 직접) — 피어 보고서의 T4 "확인됨"은 호출별 기록이 없어 증거로 쓰지 않았다 |
| 참조 skill | `common-core`·`tide`·`interpolation`·`grading`·`evaluation`·`repository` — 작업 트리(HEAD `f8b5a73`, 개정 22 반영본은 `2f2e1a0` 커밋) |
| 계획서 근거 | 개정 22 — 1.2, 2.2, 2.3, 3.2, 7.11 외 (지시서 머리말) |
| 커밋 | 하지 않음 |

이 보고서는 피어가 쓴 이전 판(`f8b5a73`에 커밋됨)을 **대체**한다. 이전 판의 "683 passed"·"T4 확인됨"·"인프라 요청 없음"은 검수에서 부정됐다(2절).

---

## 0. 실행 전 확인 · 현황 (작업 1 — 수정 후 상태)

| # | 대상 | 현황 |
|---|---|---|
| ① | `MemoryQueue()` 직접 생성 | `flowtest/main.py` 1곳뿐(시험 실행기 — 코드 주입). 운영 진입점은 모두 `open_queue(워크로드, repo)`: collector `__main__`, processor `__main__`(`processor`/`completeness-check`), interpolation·grading·evaluation `main()`. 큐 인자는 **필수**(인메모리 기본값 삭제) — `collector.main(workload, queue)`, processor `process`·`reprocess`·`reprocess_range` |
| ② | `"queue-v1"`/`"queue-v2"` 문자열 | 코드 안 0곳 — `common/contract_check/_message.py`의 `QUEUE_CONTRACT` 한 곳(검사 `test_no_stage_hardcodes_queue_version`). 판정 정의·게이트 기준·이미지 알림 예시 = `queue-v2` |
| ③ | 원문 저장소 사용 | 쓰기: collector 어댑터 4종·`fishery_watch`·`_completeness`. 읽기: processor(`main`·`_load` 적조 직전 원문 목록)·`completeness/_split_check`·flowtest. 운영 선택은 `open_raw_store(이미지)`(collector·processor `__main__`) |
| ④ | 조위 페이지 루프·합치기 | 없음 — 관측소마다 1회, 응답 그대로 `save_raw` |
| ⑤ | 실행 ID | interpolation `run_id` = UUID v5(`load_id:metric`), grading `grade_run_id` = UUID v5(`obs.loaded:load_id` / `interp.done:run_id`) — 네임스페이스는 모듈 전용 `common/run_ids.py`. 한 실행 여러 건: grading `grade.done` 축마다(Msg-Id 키 `grade_run_id+axis`), collector `completeness.collected` 원천마다(`run_key+api`) |
| ⑥ | 원문 키·`load_id` 길이(밀리초 13자리) | 조위 정기 50/56, 조위 `_y` 52/**58**(상한 64 안 — 실제 관측소 9개 전부 검사), 적조 63/69, 정선 59/65, 게시 감시 62/68, 어장환경 50/56. 64 상한은 `interpolation_runs`에 들어가는 조위만 대상(지시서 ⑥) |

환경: Docker Desktop 29.7.2, `nats:2.10-alpine`, MinIO = **`cgr.dev/chainguard/minio:latest`**(`RELEASE.2026-09-22T19-25-18Z`, digest `sha256:e7ca559d…`) — 공식 `minio/minio`는 Docker Hub에서 내려가 받을 수 없었다(`quay.io`도 401). Chainguard 빌드는 MinIO 서버 그대로다. 받는 시간 약 30초.

---

## 1. 판정표

전체 회귀: **743 passed · 14 skipped · 실패 0**(DB·NATS·MinIO 컨테이너 포함, 8분). 기준선 666 passed · 14 skipped(2026-10-06).

| # | 결과 | 근거 (테스트) |
|---|---|---|
| J1 | 통과 | `tests/queue/test_jetstream.py` j1 4건(멱등 생성·비교 필드 불일치 멈춤·서버 기본값/계약 밖 컨슈머 통과·env 없음 멈춤) + `test_j1_connect_failure_stops_startup`(접속 실패 → `SystemExit`, 접속 정보 미출력) |
| J2 | 통과 | 큐 수준 `test_j2_ack_after_success_and_redeliver_on_error`. **소비자별** `tests/db/test_redelivery.py` 5건 — processor(관측·색인 한 벌, `obs.loaded` 1건·같은 Msg-Id) / interpolation(`interp.done` 1건, runs·weights 한 벌, `run_id` 36자) / grading `obs.loaded`·`interp.done` 진입 각각(`farm_readings` 한 벌, 축마다 1건, **`farm_reading_history` 증가 0행**) / evaluation(`axis_status` 한 벌, 예외 없음 — 단 `result.updated` 재발행 없음, 2절 ③). `completeness-check`는 `test_completeness_e2e.py::test_E7_duplicate_notice_changes_nothing` |
| J3 | 통과 | `test_j3_exhausted_records_once`(정의 파일의 `max_deliver`에 상대, 재전달 간격 주입) · `test_j3_recorder_writes_ops_event` |
| J4 | 통과 | `test_j4_two_consumers_each_receive_and_interest_retention` · grading 두 구독 한 프로세스 |
| J5 | 통과 | `test_j5_other_contract_version_records_event_without_processing_or_redelivery`(NATS 경유 — 운영 이벤트 1건·처리 0·재전달 없음·스트림에서 지워짐). 판정은 다섯 소비자 핸들러의 `accept_message` |
| J6 | 통과 | `test_j6_waits_without_messages_and_finishes_in_flight_on_stop` |
| J7 | 통과 | `test_j7_msg_id_dedup_and_distinct_keys`·`test_j7_msg_id_table` + **`test_j7_publish_fails_without_server_ack`(연결 뒤 서버를 멈추고 발행 → 예외)** — 이전 테스트는 이름과 달리 연결 실패만 봤다 |
| J8 | 통과 · 기록 | `test_j8_publisher_first_then_consumer_receives`. **기록: 컨슈머 0개인 Interest 스트림에 발행 → 남은 메시지 0건**(계획서 2.2 "배포 순서 — 기동 시 계약 컨슈머 전부 생성"이 필요한 이유 실측) |
| O1 | 통과 | `tests/queue/test_raw_store_s3.py` — 왕복(`get_meta`·`get_body`·`list_keys`, 접두 있음/없음)·**봉투 바이트가 로컬 디스크와 같음**·1,005건 목록 페이지 넘김. **E3 재실행** `tests/db/test_collector_e2e.py::test_o1_e3_same_rows_on_s3[tide/bulletin]` — 같은 원문 키로 고정, `raw_id`는 원문 키로 바꿔 비교, 처리 시각 5열만 제외 → 전 테이블 같은 행 |
| O2 | 통과 | 같은 키 두 번 → `FileExistsError`·첫 원문 유지(S3·로컬 둘 다), **버전 관리 버킷에서도 새 버전 0개**, `save_raw` 충돌 시 `raw_store_errors_total{op=put}` +1. MinIO는 `If-None-Match: *`를 지킨다 |
| O3 | 통과 | DSN 없음(그리고 `RAW_STORE_PATH`가 남아 있어도) → 멈춤·로컬에 안 씀 / 형식 오류 3종 / 없는 버킷 / 닿지 않는 주소 → 멈춤 / 코드로 로컬 디스크를 넘기면 그것을 씀 |
| O4 | 통과 | 같은 초·같은 api·같은 tag 3회 → 키 3개, (밀리초, 키) 순서 = 저장 순서 |
| O5 | 통과(수정 후) | MinIO 계정·NATS 사용자/비밀번호 표식 4개 — collector 진입점 정상 실행·큐 인증 실패·S3 인증 실패의 stdout·stderr·로그·종료 메시지·저장 원문에 0건. **처음엔 실패**: `botocore`가 DEBUG에서 요청 헤더(`Credential=<접근 키 ID>/…`)를 남겼다(2절 ②) |
| T1 | 통과 | `tests/unit/test_tide_adapter.py` T1 2건(관측소마다 1회·`min=5`·`numOfRows=300`·페이지 없음) |
| T2 | 통과(수정 후) | 00:29:59 / 00:30:00 경계, **23:59:59 시작 → 자정 뒤 호출은 새 날짜·어제분 없음**, 경계는 시작 시각 한 번만, 실제 관측소로 `load_id` ≤ 64(58), 키 충돌은 실행 실패. processor: `tests/db/test_processor_load.py::test_T2_supplement…`(정상·실패 원문 각각 — `obs.loaded` 0건·`adapter_health` 그대로·관측·`raw_index`·`ingest_runs` 적재, 오늘 값 그대로) |
| T3 | 통과(기존) | `tests/unit/test_completeness.py`·`test_adapter_health.py`의 `INCOMPLETE` 판정(항목 수 < `totalCount`) — 조위 한 페이지도 같은 경로 |
| T4 | 통과 | 아래 T4 표 — 계획서 1.2절 "응답 범위"와 모두 일치 |
| T5 | 통과 | `tests/unit/test_classifier.py` — `_classify` 단위 + **원문 형식**: NIFS 실제 원문(I-13 `04 check parameter`)·data.go.kr 형식 모두 `API_ERROR_04`, `21`·`31`·`33` → `KEY_ERROR`, `40`·`41` → `SUSPENDED` |
| V1 | 통과 | `tests/unit/test_queue_v2_contract.py`(널 `error_p95` 통과·grading `NONE`·`NO_INPUT`·값 저장·`queue-v1` 거부) + `test_contract_versions.py`(상수 = 판정 정의 = 게이트 기준 = 이미지 알림 예시, 정의 파일 존재) |
| 판별력 | 아래 표 | |
| 이미지 | 통과 | 단계 5종 + flowtest 빌드. 단계 5종 import: `nats-py` 2.16.0·정의 파일 읽기(컨슈머 6), collector·processor `boto3` 1.43. 6종 모두 이미지 안 `.env*`·`operational*.yaml` 0개. MinIO 계정은 테스트 코드에만 |
| 처리 시간 | 기록 | processor(로컬 PostgreSQL 테스트 컨테이너): **정선 1년 원문(3.35MB) 첫 처리 9.27초 · 재전달 0.50초**, 어장환경 연 원문(0.70MB) 1.77초 · 0.07초. `ack_wait` 30초 안, 처리 중 10초마다 연장 신호 |
| 회귀 | 통과 | 전체 `pytest` 743 passed · 14 skipped, `run_gate.py --warn-pending` 게이트 통과(운영 조정 게이트 `evaluation.main gate`도 통과), `scan_keys` 0건 |

### T4 확인 호출 (`dtRecent`, `DT_0016` 여수, `numOfRows=300`·`min=5`·`type=json`)

| # | 시각(KST) | 요청 | `resultCode` | `totalCount` | 항목 | 첫 / 끝 `obsrvnDt` | 판정 |
|---|---|---|---|---|---|---|---|
| 1 | 2026-10-07 09:51:17 | `reqDate=20261007` | 00 | 117 | 117 | 09:40 / 00:00 | ① 117 = 00:00~09:40 5분 격자 수 ② 5분 격자·엄격한 최신순·중복 없음 |
| 2 | 09:51:34 | `reqDate=20261006` | 00 | 288 | 288 | 10-06 23:55 / 00:00 | ③ 288건, 어제 날짜만 |
| 3 | 09:51:40 | `reqDate=20261007`·`include=wtem` | 00 | 117 | 117 | (필드 없음) | ④ 항목 수는 그대로, **필드가 `wtem` 하나로** — 관측 시각·좌표도 빠져 수집에 쓸 수 없다(collector는 `include`를 쓰지 않는다) |

- 재시도 0, HTTP 200, 원문 3건 모두 키 마스킹 확인(값 출력 없음). 원문은 작업 세션 임시 폴더(저장소 밖)
- `obsrvnDt`는 **초 없는 분 단위**(`2026-10-07 09:40`) — I-17 실측과 같고 processor가 이미 처리한다. 09:51 호출의 가장 새 항목이 09:40 — 게시 지연 약 10분
- 항목 필드 14개: `artmp`·`atmpr`·`bscTdlvHgt`·`crdir`·`crsp`·`lat`·`lot`·`maxMmntWspd`·`obsrvnDt`·`obsvtrNm`·`slntQty`·`wndrct`·`wspd`·`wtem` — 관측소 코드 없음(요청 변수 `obsCode`로 안다, I-17과 같음)

### 판별력 (구현을 끈 상태에서 해당 검사가 실패하는지)

소스를 한 군데씩 바꿔 해당 검사를 돌리고 원복했다(스크립트는 작업 세션 임시 폴더 — 저장소 밖).

| 끈 구현 | 검사 | 결과 |
|---|---|---|
| J1 비교 필드 → 전체 필드 비교 | `test_j1_server_defaults_and_foreign_consumer_pass` | 실패(판별 OK) |
| J2 ack을 처리 전으로 | `test_j2_ack_after_success_and_redeliver_on_error` | 실패(판별 OK) |
| J2 interpolation `run_id` → `uuid4` | `test_redelivery.py::test_j2_interpolation` | 실패(판별 OK) |
| J3 소진 처리 제거 | `test_j3_exhausted_records_once` | 실패(판별 OK) |
| J7 Msg-Id를 주제만으로 | `test_j7_msg_id_dedup_and_distinct_keys` | 실패(판별 OK) |
| O2 조건부 쓰기 제거 | `test_o2_second_put_same_key_fails_and_first_kept` | 실패(판별 OK) |
| O3 DSN 없을 때 로컬 기본 경로 대체 | `test_o3_no_dsn_stops_and_ignores_raw_store_path` | 실패(판별 OK) |
| O5 botocore 로그 수준 고정 제거 | `test_o5_markers_absent_from_logs_raw_and_exit` | 실패(판별 OK) |
| T1 `min=5` 제거 | `test_T1_one_fetch_per_station_normal_hour` | 실패(판별 OK) |
| T2 `reqDate`를 시작 시각으로 | `test_T2_regular_req_date_is_kst_date_just_before_each_call` | 실패(판별 OK) |
| T2 자정 분기 제거 | `test_T2_midnight_boundary_before_30min_adds_y_fetch` | 실패(판별 OK) |
| T2 보충 원문 분기 제거 | `test_T2_supplement_loads_rows_without_obs_loaded_or_health` | 실패(판별 OK) |

실행 안 함: J8(서버 동작 기록이라 끌 구현이 없음), V1 널 거부(계약 파일 변이 — 이전 계약 `queue-v1`이 널을 거부하는 것은 `queue-v1.json` 대조로 갈음), T1 페이지 루프 복원(루프 코드가 없어져 복원 대상 없음 — 호출 수 단언이 대신 잡는다).

---

## 2. 예상과 달랐던 결과

### 피어 구현의 결함 (검수 — 이 세션이 고침)

| # | 결함 | 처리 |
|---|---|---|
| 1 | `nats-py`·`boto3`가 설치되지 않아 큐·S3 코드가 **한 번도 실행되지 않았다**. `_nats.py`는 없는 메서드(`find_stream`)·나노초 단위 시간·실행 중 루프에서 `run_until_complete`(핸들러 안 발행 불가)·grading 두 번째 구독 미기동. collector·`completeness-check`·`process`·`reprocess`는 `MemoryQueue` 그대로. DB 테스트는 가짜 `_FakeNats`로 통과 | `_nats.py` 재작성(전용 스레드 이벤트 루프), 진입점 연결, NATS·MinIO 테스트 컨테이너 검사(J·O) 신설 |
| 2 | 조위 어제분(`_y`) 원문에 **`raw.fetched`를 내지 않았다** — processor가 받지 못해 보충 원문 적재 0건. 피어 테스트가 "`_y`는 발행 없음"을 기대로 박아 두었다(`raw.fetched`와 `obs.loaded` 혼동) | `_y`도 `raw.fetched` 발행, processor가 관측·색인까지만 |
| 3 | 정기 `reqDate`를 실행 시작에 한 번 정함(계획서: 호출 직전 KST 날짜) | 호출마다 `_now_kst()` |
| 4 | 원문 키 충돌을 삼킴(정기 `continue`, 어제분 `pass` — "이미 저장된 어제분 정상") | 예외를 올려 실행 실패(다른 어댑터와 같게, 2.3절) |
| 5 | T2 `load_id` 64자 검사가 `assert … or True`(늘 통과) | 실제 키 생성 함수·관측소 목록·파서 버전으로 |
| 6 | 보충 원문 판별이 api를 보지 않음 | 조위(`dtRecent`)로 한정 |
| 7 | 실행 ID 네임스페이스 `NAMESPACE_DNS`(계획서: 이 모듈 네임스페이스) | `common/run_ids.py` 고정 네임스페이스 |
| 8 | 계약 버전이 판정 정의·게이트 기준·이미지 알림 예시에서 `queue-v1` 그대로, 코드에 문자열 10곳 | `queue-v2`로 같이, 상수로 |
| 9 | Dockerfile이 `nats-py`·`boto3`를 설치하지 않고 `contracts/queue/`를 복사하지 않음 — 이미지가 연결 즉시 실패 | 의존성·정의 파일 복사(2절 ④ 갱신 누락 참고) |
| 10 | `raw_store_errors_total` 라벨이 계획서(`op`·`image`)와 다름 | 맞춤 |
| 11 | 보고서: 판정표·T4 수치·판별력·이미지·처리 시간·인프라 요청 목록 없음 | 이 판 |

### 이 세션이 새로 드러낸 것

- ① **큐 연결 실패가 예외 그대로 나가고 루프 스레드가 남음** — `SystemExit`(오류 종류만)로 멈추게 고침. 접속 주소에 사용자·비밀번호가 들어갈 수 있어 메시지에 넣지 않는다
- ② **`botocore` DEBUG 로그에 접근 키 ID** — 운영 로그 수준(INFO)에선 안 나오지만 수준을 올리면 샌다. S3 구현이 `botocore` 로거를 INFO 이상으로 고정(비밀 키 자체는 찍히지 않음 — 서명만)
- ③ **evaluation `result.updated` 유실 경로** — evaluation은 `axis_status`를 새로 쓸 때만 `result.updated`를 낸다(`basis_utc` 쓰기 규칙). 커밋 뒤 발행에서 죽으면 재전달은 쓸 것이 없어 알림을 다시 내지 않는다. 계획서 7.11 J2 evaluation 기준(`axis_status` 한 벌·예외 없음)은 충족. **고치지 않음 — 현행 유지, 계획서 2.2절에 알려진 한계로 기록(개정 22 보완)**(웹의 선택 구독·캐시 무효화라 영향은 작다). 현재 동작을 테스트에 기록
- ④ **갱신 누락**: 계획서 2.2절은 "정의는 `contracts/queue/`, 기동 시 그 정의로 생성"인데, 계획서 2.0.2절·`CLAUDE.md` 4절 Dockerfile 복사 목록에 `contracts/queue/jetstream.json`이 없다. 이미지가 기동하려면 필요해 단계 5종 Dockerfile에 넣었다(flowtest는 인메모리라 불필요). **개정 22 보완으로 계획서 2.0.2절·`CLAUDE.md` 4절에 반영함**
- ⑤ 공식 MinIO 이미지 배포 중단(위 0절)
- ⑥ `contracts/tables/seeds_pg.sql`이 테스트 실행 뒤 작업 트리에서 변경으로 보인다 — 내용 차이 0, 줄바꿈만(테스트가 생성본을 LF로 다시 씀). 기능 영향 없음

---

## 3. 새로 발견한 함정

- 피어 테스트는 **가짜 객체로 연결 계층을 통째로 우회**하면 전부 녹색이어도 실제 연결은 0% 검증이다(이번 `_FakeNats`). 연결 계층은 테스트 컨테이너로만 판정한다
- 셸 heredoc 안 Python으로 Dockerfile을 고치다 `\n`이 글자 그대로 들어가 빌드 5종 실패 — 빌드로 잡힘. 여러 줄 편집은 편집 도구로
- 컨슈머 0개 Interest 스트림은 발행을 그대로 버린다(J8) — 소비자 이미지를 늦게 띄우는 배포에서 알림이 사라질 수 있어, 어느 이미지든 기동 시 계약 컨슈머 전부를 만든다

---

## 4. 계획서 반영 후보

| 항목 | 상태 | 절 |
|---|---|---|
| Dockerfile 복사 목록에 `contracts/queue/jetstream.json`(단계 5종) | **반영함 — 개정 22 보완(2026-10-07)** | 2.0.2, `CLAUDE.md` 4절 |
| evaluation 재전달 시 `result.updated` 재발행 여부 | **현행 유지·알려진 한계로 기록 *(제안)* — 개정 22 보완** | 2.2, 7.11 J2 |
| 실행 ID 네임스페이스 = `uuid5(NAMESPACE_URL, "urn:aquasentinel:api-module:run-id")` 값 고정 | *(제안)* 구현 | 2.2 |
| 큐 연결 실패 → `SystemExit`(오류 종류만) | 구현 | 2.2·12.1 |
| S3 구현이 `botocore` 로그 수준을 INFO 이상으로 고정 | 구현 | 2.3·12.1 |
| 로컬 S3 테스트 이미지 = Chainguard MinIO(공식 이미지 중단) | 기록 | 6.1·7.11 |
| 구현한 *(제안)*: 스트림 이름 `AQUASENTINEL`·주제 접두 `aquasentinel.`·컨슈머 이름 `워크로드-주제`·nak 간격 [10,30,60,120]초·처리 중 연장 10초·기동 시 컨슈머 전부 생성·`QUEUE_STREAM_REPLICAS`·`RAW_STORE_ENDPOINT`·tag `_y`·키 밀리초(`_fetched_ms`)·자정 경계 30분·실행기 DSN 거부·`40`→`SUSPENDED`·`21`·`31`·`33`→`KEY_ERROR` | 확정 대기 | 2.2·2.3·1.2·3.2·2.1.1 |
| 새 환경변수: `QUEUE_DSN`·`QUEUE_STREAM_REPLICAS`·`RAW_STORE_DSN`·`RAW_STORE_ENDPOINT`(로컬 MinIO 전용) | 기록 | 2.2·2.3 |

만난 `<미결>`: 없음(새로 만나지 않음).

---

## 5. 변경 파일 (작업 트리, `f8b5a73` 이후 — 미커밋)

- 큐: `src/api_module/common/queue/{_nats.py,_interface.py,_memory.py,__init__.py}`, `contracts/queue/jetstream.json`(`f8b5a73`에 이미 포함)
- 원문 저장소: `src/api_module/common/raw_store/{_store.py,__init__.py}`
- 지표: `src/api_module/common/metrics/{_metrics.py,__init__.py}`
- 실행 ID: `src/api_module/common/run_ids.py`(신규), `interpolation/main.py`, `grading/main.py`
- 진입점: `collector/main.py`, `processor/main.py`, `interpolation/main.py`, `grading/main.py`, `evaluation/main.py`
- 조위: `collector/adapters/tide/_adapter.py`, `processor/main.py`(`_is_supplement`)
- 계약 상수: collector 어댑터 4종·`fishery_watch.py`·`_completeness.py`·`processor/main.py`
- 판정 정의·기준: `config/definitions.yaml`, `ci/gate/expected.yaml`, `contracts/release/image_notice.json`
- 이미지: `docker/{collector,processor,interpolation,grading,evaluation}/Dockerfile`, `pyproject.toml`
- 안내: `handoff/flowtest/README.md`(하루 합계·보충 원문 문구)
- 테스트: `tests/conftest.py`(MinIO 고정물), `tests/queue/{conftest.py,test_jetstream.py,tests_queue_helpers.py,test_raw_store_s3.py}`, `tests/db/{test_redelivery.py(신규),test_collector_e2e.py,test_processor_load.py,test_seed_wiring.py}`, `tests/unit/{test_wiring.py,test_tide_adapter.py,test_classifier.py,test_run_ids.py(신규),test_contract_versions.py(신규)}`
- 보고·로그: `docs/reports/I-18_result.md`, `1006_logs.md`

### 제안 커밋 메시지

```
fix(I-18): JetStream 큐·S3 원문 저장소 실제 연결, queue-v2, 조위 보충 원문

- common/queue/_nats.py 재작성 — 전용 스레드 이벤트 루프, 기동 시 스트림·컨슈머 멱등 생성·비교 필드,
  커밋 뒤 ack·지연 nak·처리 중 연장·소진 기록, 연결 실패 시 기동 멈춤
- 운영 진입점이 open_queue·open_raw_store로 연결(인메모리·로컬 대체 없음), grading 두 구독
- S3 원문 저장소 MinIO 검사(O1~O5), botocore DEBUG 계정 노출 차단
- 조위: reqDate = 호출 직전 KST 날짜, 어제분(_y)도 raw.fetched — processor는 관측·색인까지만,
  원문 키 충돌은 실행 실패
- 실행 ID UUID v5 모듈 네임스페이스, 계약 버전 queue-v2를 판정 정의·게이트 기준과 같이, 상수화
- Dockerfile 5종에 nats-py·boto3·contracts/queue/jetstream.json
- 검사: J1~J8(NATS 컨테이너)·소비자별 J2·O1~O5(MinIO 컨테이너)·T2·T5·V1·판별력

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

---

## 부록 — 인프라 요청 목록 (인프라에 보낼 원본)

> 받는 쪽이 이 저장소를 몰라도 읽히게 썼다. 수치는 모듈 현재 판 기준.

**1. 운영 매니페스트 환경 변수 추가** (단계 이미지 5종 — 수집·가공·추정·등급·판정)

| 변수 | 값 | 넣을 워크로드 |
|---|---|---|
| `QUEUE_DSN` | NATS 접속 주소(예: `nats://<호스트>:4222`) | 수집·가공(가공 컨슈머·분할 검사기·재처리)·추정·등급·판정(컨슈머) |
| `QUEUE_STREAM_REPLICAS` | 스트림 복제 수(정수 — 클러스터 노드 수에 맞춰 인프라가 정함) | 위와 같음 |
| `RAW_STORE_DSN` | `s3://<raw-store 버킷>/` | 수집 전 워크로드, 가공 전 워크로드(컨슈머·분할 검사기·재처리) |

- 세 변수 중 하나라도 없으면 해당 워크로드는 **기동하지 않고 멈춥니다**(메모리 큐·파드 로컬 디스크로 대체하지 않음). 추정 오차 산출·판정 sweep(CronJob)은 큐에 발행하지 않아 `QUEUE_DSN`이 필요 없습니다
- 원문 저장소 권한은 이미 구비된 것 그대로입니다: 수집 = 쓰기·읽기·목록, 가공(분할 검사기·재처리 포함) = 읽기·목록. **삭제 권한은 필요 없습니다**(같은 키 덮어쓰기 금지도 쓰기 권한의 조건부 쓰기로 처리). 원문 보존 기간은 아직 정하지 않았습니다(수명 주기 규칙은 인프라)

**2. 스트림·컨슈머는 모듈이 만듭니다**

- 어느 이미지든 기동할 때 스트림 `AQUASENTINEL`(주제 `aquasentinel.>`, Interest 보존, 파일 저장, 최대 보존 7일, 중복 창 120초)과 아래 컨슈머 6개를 **없으면 만들고, 있으면 설정을 비교**합니다. 다르면 기동이 멈추고 차이를 로그에 남깁니다(조용히 고치지 않음)
- 컨슈머(모두 durable pull, 명시 ack, `ack_wait` 30초, 최대 전달 5회):

| 컨슈머 이름 | 워크로드 | 주제 | KEDA |
|---|---|---|---|
| `processor-raw-fetched` | 가공 | `aquasentinel.raw.fetched` | 대상 |
| `completeness-check-completeness-collected` | 분할 합산 검사기 | `aquasentinel.completeness.collected` | **제외**(1대 고정) |
| `interpolation-obs-loaded` | 추정 | `aquasentinel.obs.loaded` | 대상 |
| `grading-obs-loaded` | 등급 | `aquasentinel.obs.loaded` | 대상 — 등급은 컨슈머 **2개** |
| `grading-interp-done` | 등급 | `aquasentinel.interp.done` | 대상 |
| `evaluation-grade-done` | 판정 | `aquasentinel.grade.done` | 대상 |

- KEDA NATS JetStream 트리거는 위 스트림·컨슈머 이름으로 대기 수를 보면 됩니다. 등급 워크로드는 두 컨슈머의 대기 수를 함께 봐야 합니다
- 소비자가 아직 안 떠 있어도 발행된 알림이 보존되도록, 수집 이미지만 먼저 떠도 컨슈머 6개가 모두 만들어집니다(Interest 보존은 컨슈머가 없으면 메시지를 남기지 않기 때문 — 시험으로 확인)

**3. 스트림·컨슈머 설정을 바꾸는 릴리스의 절차**

설정(보존·`ack_wait`·최대 전달 등)이 바뀐 이미지는 기존 정의와 달라 기동이 멈춥니다. 그런 릴리스는 ① 해당 컨슈머(또는 스트림)의 대기 메시지가 0인지 확인 → ② 옛 컨슈머(또는 스트림) 삭제 → ③ 새 이미지 기동 순서로 해 주십시오. 바뀌는 릴리스는 미리 알려 드리겠습니다

**4. 알림·지표**

- 최대 전달(5회)에 도달한 메시지는 모듈이 DB 운영 이벤트(`QUEUE_DELIVERY_EXHAUSTED`)로 남기고 버립니다. NATS 쪽 최대 전달 도달 알림(advisory)을 경보에 연결해 주시면 좋겠습니다
- 모듈 지표 추가 3종: `queue_redelivered_total{topic,consumer}`, `queue_delivery_exhausted_total{topic,consumer}`, `raw_store_errors_total{op,image}` — 기존 지표 구성에 함께 수집 부탁드립니다

**5. 호출량 (참고)**

조위 수집이 관측소마다 하루치를 한 번에 받도록 바뀌었습니다: 실행마다 9회(자정 직후 30분 안 실행은 +9회), 하루 조위 약 1,320회 · 전체 약 1,350회(공공데이터포털 일일 한도 10,000회)

**6. 이미지**

단계 이미지 5종은 NATS 클라이언트를, 수집·가공은 S3 클라이언트를 포함합니다. 이미지 안에 인증 정보는 없습니다(클러스터에서는 ServiceAccount 역할로 S3 접근)

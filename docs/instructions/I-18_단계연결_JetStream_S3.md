# I-18 — 단계 연결: NATS JetStream 큐 · S3 원문 저장소 · `queue-v2` · 조위 한 페이지 (개정 22 구현)

작성 2026-10-06 · 근거 계획서 개정 22(작업 트리 — 커밋 전, 독립 검수 1·2차 반영)

---

## 0. 머리말

| 항목 | 내용 |
| --- | --- |
| 번호 | **I-18** |
| 대상 단계 | S15 (10절) |
| 선행 | I-1~I-17 + 2026-10-06 DDL 고유 인덱스 수정(작업 트리 기준) |
| 적용 수정사항 | 없음 |
| 공공 API 호출 | **허용 — 7.11 T4에서만.** `dtRecent` **5회 이내**(재시도 포함 전체 합), 관측소 하나(`DT_0016` 여수 권장 — 실효 관측소)로. **조위 구현(작업 7)보다 먼저** 한다. 다른 원천·다른 검사·다른 작업은 호출 금지. 예산을 넘겨야 끝나는 상황이면 그 자리에서 멈추고 보고한다 |
| 읽을 skill | **`common-core`**(③-5 원문 저장·S3 구성, ③-6 단계 간 알림·JetStream 구성, ③-12 진입점, 기동 시 검사) — **먼저 읽는다.** 이어서 `tide`(요청 규칙·자정 경계·보충 원문), `interpolation`·`grading`(`queue-v2`·실행 ID 결정화), `evaluation`(컨슈머 진입점), `repository`(기동 시 고유 키 검사 — 손대지 않지만 회귀 기준) |
| 계획서 근거 | **2.2(JetStream 구성·`queue-v2`)**, **2.3(S3 구성·키·덮어쓰기 금지·tag)**, **1.2(조위 요청·자정 경계·보충 원문)**, **7.11(J1~J8·O1~O5·T1~T5·V1 — 이 지시서의 통과 기준)**, 2.0.3, 2.0.4, 2.1, 2.1.1, 3.2, 3.3, 4.8, 5.4, 6.1, 7.4, 7.9, 7.10, 8, 9, 11, 12 |
| 커밋 | **하지 않는다** — `git add`·`commit`·`push` 금지. 확인 게이트는 **작업 트리의 계획서 문구**로 한다 |

### 0.1 배경 (짧게)

단계 이미지 5종은 지금 인메모리 큐·파드 로컬 디스크를 써서 **클러스터에서 서로 이어지지 않는다**(컨슈머는 수신 대기 없이 바로 끝난다 — 점검 C17). 큐는 NATS JetStream, 원문 본문은 S3 raw-store 버킷(색인은 메인 DB `raw_index`)으로 결정됐고, 인프라는 NATS 접속 주소와 버킷·IRSA 권한을 갖췄고 매니페스트를 자기 저장소로 옮겼다(2026-10-06 회신 — 인계됨). 같은 묶음으로 계약 `queue-v2`(점검 C4)와 조위 한 페이지(점검 C2 — 페이지를 합쳐 원문을 만들던 결함)를 고친다. 이 지시서는 **단계 사이를 잇는 구현**까지다 — 이미지 5종을 각자 띄워 원천에서 결과 테이블까지 확인하는 것은 다음 단계(로컬 조립 리허설)다.

### 0.2 지키는 것

- **단계 처리 로직은 바꾸지 않는다** — 바꾸는 것은 큐·원문 저장소 구현체, 컨슈머 진입점의 연결(구독 → 수신 루프), 실행 ID의 결정화(interpolation `run_id`·grading `grade_run_id` — 재전달 멱등, 계획서 2.2절), 조위 collector의 요청, processor의 보충 원문 분기(1.2절)와 원문 없음 → 예외(2.3절), `queue-v2` 발행·소비, 결과 코드 대응, 호출층의 `_fetched_ms`뿐이다. 그 밖에 단계 코드를 고쳐야만 되는 곳은 **멈추고 보고**한다
- **인메모리·로컬 디스크로 조용히 대체하지 않는다**(12절) — `QUEUE_DSN`·`QUEUE_STREAM_REPLICAS`·`RAW_STORE_DSN`이 없거나 연결이 안 되면 운영 진입점은 멈춘다. 인메모리·로컬 디스크는 테스트와 시험 실행기가 **코드에서 구현체를 넘길 때만** — 운영 진입점은 `RAW_STORE_PATH`를 읽지 않는다. 구현 선택·연결 확인은 진입점 `main()` 층에 두고 꺼낸 기동 시 검사 함수에 넣지 않는다(2.1.1절 — FT1 ② 비교 집합에서 뺀다)
- **처리(DB 커밋·다음 알림 발행)가 끝나기 전에 ack하지 않는다.** 원문을 덮어쓰지 않는다. 여러 응답을 합쳐 원문을 만들지 않는다(12절)
- 스트림·컨슈머 설정값은 계획서 2.2절 값 그대로(Interest, `max_age` 7일, `ack_wait` 30초, `max_deliver` 5). `Nats-Msg-Id`는 2.2절 그대로 **`{주제}:{키}`**, 키는 주제별 표(**한 실행이 같은 주제로 여러 건을 내므로 실행 ID만으로 만들지 않는다**). *(제안)* 표시 항목(스트림 이름·주제 접두·컨슈머 이름·재전달 간격·처리 중 연장·기동 시 모든 컨슈머 생성·`QUEUE_STREAM_REPLICAS`·tag `_y`·키 밀리초·자정 경계 30분·실행기 DSN 거부)은 구현하되 보고서 4절에 적는다
- **계약 버전은 판정 정의다** — `config/definitions.yaml`의 `contracts.queue`와 `ci/gate/expected.yaml`의 `contracts`를 **같이** 바꾼다(12절). 코드에 `"queue-v1"` 같은 문자열을 흩어 두지 않는다 — 계약 상수 하나(`common/contract_check`의 `QUEUE_CONTRACT`)를 쓴다
- **비밀을 출력하지 않는다** — 인증키·요청주소 값·DB 연결 문자열·MinIO 계정·NATS 자격 증명. 원문 키 검사는 `python ci/scan_keys.py`로만, 결과는 건수만. 테스트용 MinIO 계정은 테스트 코드가 만드는 일회용 값(표식 문자열)으로 하고 `.env`에 쓰지 않는다
- **운영 자원에 접속하지 않는다** — 운영·공유 시험 NATS, 실제 S3 버킷, 운영·공유 시험 DB 모두. 큐·원문 저장소 검사는 테스트 컨테이너(NATS JetStream 서버 이미지, MinIO 이미지)로 한다
- 테이블·시드·`farm_sites`·스키마를 만들거나 바꾸지 않는다(테스트 컨테이너 안의 생성본 적용은 기존 방식 그대로). 새 DB 표·열 길이 변경이 필요하면 멈추고 보고 — 이 지시서에는 필요 없다(소진 기록은 기존 `ops_events`, 키 길이는 tag로 맞춘다)
- **인계된 매니페스트(`handoff/k8s/`)와 `HANDOFF.md`는 고치지 않는다**(계획서 2.0.4·11절 — 인프라가 옮겨 갔다). 바꿀 것은 **인프라 요청 목록**으로 낸다(작업 11). 대시보드 인계 묶음(`handoff/dashboard-deliver/`)도 고치지 않는다
- 받는 사람이 있는 문서(인프라 요청 목록·`handoff/flowtest/README.md`)에는 이 저장소 내부 쟁점 번호(C2 등)·계획서 절 번호를 쓰지 않는다
- 파일 줄바꿈: `core.autocrlf=true`. 바이트를 비교하는 검사는 LF로 맞춰 비교한다

---

## 1. 작업

경로는 `src/api_module/` 기준.

1. **현황 파악(코드 변경 없음)** — 보고서 0절에 표로: ① `MemoryQueue()`를 직접 만드는 곳 전부(파일·줄 — collector·processor(`process`·`reprocess`·`completeness-check`·컨슈머)·interpolation·grading(구독 2주제)·evaluation·flowtest) ② `"queue-v1"` 문자열이 박힌 곳 전부 ③ 원문 저장소를 읽고 쓰는 곳(`save_raw`·`get_raw_meta`·`get_raw_body`·`list_raw_keys`)과 워크로드 ④ 조위 collector의 페이지 루프·합치기 위치 ⑤ 실행 ID를 만드는 곳(`uuid4` — interpolation `run_id`, grading `grade_run_id` 두 곳)과 한 실행이 같은 주제로 여러 건 내는 곳(grading `grade.done` 축마다, collector `completeness.collected` 원천마다) ⑥ 원천별로 가장 긴 원문 키와 그 `load_id` 길이(참고 — 상한 검사 대상은 `interpolation_runs`에 들어가는 조위 정기·`_y`뿐이다. 적조·정선·게시 감시가 64자를 넘는 것은 지금 문제가 아니고, 그 tag를 줄이지 않는다 — 적조 직전 원문 판별이 tag 형식에 기댄다). 이 표가 작업 3~10의 대상 목록이다
2. **T4 확인 호출**(머리말 허용 — 작업 7 전에) — 7.11 T4 ①~④. 호출마다 시각(KST)·요청 변수(키 제외)·`resultCode`·`totalCount`·항목 수·첫/끝 `obsrvnDt`를 보고서에 적는다. 계획서 1.2절 "응답 범위"와 다르면(예: `totalCount`가 5분 격자 수가 아님, `reqDate`=어제가 안 됨) **여기서 멈추고 보고**한다 — 작업 7을 하지 않는다. 받은 원문은 저장소 밖 임시 경로에(경로 별칭만 보고), 키 마스킹 여부 확인(값 출력 없음)
3. **큐 — `common/queue/`**
   - 인터페이스: 기존 `publish(Message)`·`subscribe(topic, handler)`를 유지하고, 수신 루프(`run()` 등 — 이름은 관례대로)를 더한다. 핸들러 시그니처(`Message` 하나)는 그대로
   - **JetStream 구현**: `nats-py`. 동기 단계 코드를 위해 구현 안에서 이벤트 루프를 감싼다. 2.2절 표대로 — 기동 시 스트림·**계약의 컨슈머 전부** 멱등 생성(정의 파일의 **비교 필드만** 비교, 다르면 `SystemExit`로 차이 보고, 서버 기본값·계약에 없는 컨슈머는 무시), 복제 수는 `QUEUE_STREAM_REPLICAS`(없으면 멈춤), 발행은 서버 확인 필수·`Nats-Msg-Id` = `{주제}:{키}`, 스트림 주제 설정은 와일드카드 `aquasentinel.>` 하나, 처리 성공 뒤 ack·예외면 **전달 횟수에 따른 지연 nak**(컨슈머 `backoff` 쓰지 않음, 간격 주입 가능), 오래 걸리는 처리의 연장 신호, 마지막 전달(`num_delivered == max_deliver`) 실패 시 `ops_events` `QUEUE_DELIVERY_EXHAUSTED` 기록 후 `term`, 계약 버전이 다른 메시지는 운영 이벤트 + `term`, SIGTERM이면 처리 중 메시지를 마치고 종료. 지표 `queue_redelivered_total`·`queue_delivery_exhausted_total`(9절)
   - **스트림·컨슈머 정의 파일** — `contracts/queue/`(예: `jetstream.json` — 스트림 이름·주제·보존·`max_age`·컨슈머 목록과 `ack_wait`·`max_deliver`·재전달 간격·**비교 필드 목록**). 코드는 이 파일을 읽는다(값을 코드에 따로 박지 않는다)
   - `ops_events` 쓰기는 기존 DB 접근 계층 메서드로(새 표 없음)
4. **원문 저장소 — `common/raw_store/` · 호출층**
   - **S3 구현**: `RAW_STORE_DSN = s3://<버킷>[/<접두>]`, 기본 자격 증명 체인(클러스터 IRSA), 로컬 MinIO는 `RAW_STORE_ENDPOINT` *(제안)*. 기동 시 버킷 접근 1회 확인 — 실패면 멈춤. `put`은 **조건부 쓰기**(`If-None-Match` — MinIO 테스트 컨테이너에서 동작하는지 확인하고, 안 되면 멈추고 보고), `get_meta`·`get_body`는 객체 하나를 받아 해석, `list_keys`는 페이지 단위로 끝까지. 오류 지표 `raw_store_errors_total`
   - **선택 규칙**: DSN 있음 → S3 / DSN 없음 → **운영 진입점 멈춤**. 로컬 디스크는 테스트·실행기가 코드에서 구현체를 넘길 때만 — 운영 진입점은 `RAW_STORE_PATH`를 읽지 않고, 지금의 기본 경로(`raw_data`) 대체를 없앤다. 키가 없으면 두 구현 모두 `None`. 테스트가 기본 경로에 기대고 있으면 테스트 쪽에서 명시하도록 고친다(검사를 약하게 하지 않는다)
   - **로컬 디스크 구현도 덮어쓰기 금지**(같은 키가 있으면 실패)
   - **키 `epoch_ms`** = 호출층이 원문 메타 `_fetched_ms`(호출 시각, `fetched_at`과 같은 순간의 밀리초)로 남긴 값 *(제안)*. `fetched_at`·날짜 폴더 규칙은 그대로. 적조 직전 원문 대조(3.3절)의 키 순서가 그대로 성립하는지 기존 N15·N16으로 확인
   - 원문 봉투 직렬화는 로컬 디스크 구현과 같은 바이트(O1)
5. **컨슈머 진입점·발행 연결** — 1의 표 ①의 운영 진입점마다(`main()` 층에서): `QUEUE_DSN`으로 큐를 만들고, 기존 구독(핸들러)을 그대로 등록한 뒤 **수신 루프**로 들어간다(processor `raw.fetched`, `completeness-check` `completeness.collected`, interpolation `obs.loaded`, grading `obs.loaded`·`interp.done`, evaluation `grade.done`). collector·`interpolation-error`·`evaluation-sweep`·`reprocess`(발행만 하는 진입점)는 같은 큐 구현으로 발행만. 기존 기동 시 검사 순서는 바꾸지 않고, 큐·원문 저장소 연결 확인은 **다른 읽기 전용 검사가 모두 통과한 뒤**, 쓰기가 있는 기동 절차보다 앞에 둔다
6. **실행 ID 결정화 · `queue-v2`**
   - interpolation `run_id`를 입력(`load_id`+`metric`)에서, grading `grade_run_id`를 입력 주제+입력 키(`obs.loaded`면 `load_id`, `interp.done`이면 `run_id`)에서 **UUID v5로 결정적으로** 만든다 *(제안)* — 64자 안(`run_id`는 `VARCHAR(64)`·수온 `source_ref`). 재전달 시 같은 행·같은 다음 알림(J2)
   - `contracts/queue/queue-v2.json`(`interp.done.error_p95`: 숫자 또는 null — 그 밖은 `queue-v1`과 같음). `queue-v1.json`은 남긴다(기록). `QUEUE_CONTRACT` = `queue-v2`, 박힌 문자열은 상수로. `config/definitions.yaml` `contracts.queue`·`ci/gate/expected.yaml` `contracts`·`contracts/release/image_notice.json` 예시를 같이
   - interpolation은 오늘의 오차가 없으면 **널**을 싣는다(값을 지어내지 않는다). grading은 널이면 수온 행 `provenance = NONE`·`none_reason = NO_INPUT`·`lower`·`upper` 없음·값 저장(현재 `grade_water_temp` 동작 — 바꾸지 않는다)
7. **조위 — collector·processor** (작업 2가 계획서대로 확인된 뒤)
   - collector `adapters/tide/`: 관측소마다 **1회** — `reqDate` = **호출 직전의 KST 날짜**(`YYYYMMDD` — 실행 시작 시각이 아니다), `min=5`, `numOfRows=300`, `type`은 기존대로. **페이지 루프와 합치기(합성 JSON) 삭제** — 응답 결과를 그대로 `save_raw`. 실행 시작 시각(KST)을 한 번 정해 그 값이 `[00:00, 00:30)`이면 관측소마다 `reqDate` = KST 어제 1회 더(tag `{관측소}_y`). 시작 시각은 테스트에서 고정할 수 있게
   - processor: **tag가 `_y`로 끝나면 보충 원문** — 관측·`raw_index`·`ingest_runs`·`stations`까지 적재하고 **`obs.loaded`를 내지 않고 `adapter_health`를 갱신하지 않는다**(1.2절). 관측소는 tag가 아니라 요청 변수 `obsCode`로 안다(현재 코드도 그렇다 — 다르면 보고). `raw.fetched`가 가리킨 원문이 없으면(지금은 출력만 하고 끝난다) **예외**를 낸다 — 재전달·소진으로 드러나게(2.3절)
8. **결과 코드 대응 — `common/classifier/`** — 3.2절 표대로 `21`·`31`·`33` → `KEY_ERROR`, `40` → `SUSPENDED` *(제안)*. `04`는 그대로 `API_ERROR_04`
9. **시험 실행기 — `flowtest/`** — 인메모리 큐·로컬 디스크를 **명시적으로** 넘긴다. `QUEUE_DSN`·`RAW_STORE_DSN`이 설정돼 있으면 실행 전 점검에서 멈춘다 *(제안)*(이름만 보고, 값 출력 없음). FT1의 ② 비교 집합에서 큐·원문 저장소 선택·연결 확인을 뺀다(2.1.1절). FT1~FT6 회귀 없음
10. **의존성·이미지** — `pyproject.toml`: 공통에 `nats-py`, `collector`·`processor`(와 `flowtest`)에 S3 클라이언트. 이미지 6종(단계 5종 + `flowtest`) 빌드 확인(`docker build -f docker/<이미지>/Dockerfile .`)과 import 확인. **푸시하지 않는다**
11. **인프라 요청 목록 · 사용 안내**
    - **인프라 요청 목록**(보고서 부록 — 이 세션이 인프라에 보낼 원본, 받는 사람 기준으로 내부 번호 없이): 운영 매니페스트에 `QUEUE_DSN`·`QUEUE_STREAM_REPLICAS`·`RAW_STORE_DSN`(`s3://<버킷>/` 형식) 추가, 워크로드별 원문 저장소 권한 재확인(collector 쓰기·읽기·목록, processor 역할 공유 — 이미 구비), KEDA NATS JetStream 트리거(스트림·**컨슈머 이름** 표 — grading은 2개, `completeness-check` 제외), 스트림·컨슈머는 모듈이 기동 시 만든다는 점과 **설정을 바꾸는 릴리스의 절차**(옛 스트림·컨슈머 삭제 → 새 이미지 기동), NATS 최대 전달 도달 알림·지표 구성, 조위 호출량(하루 조위 약 1,320건 · 전체 약 1,350건), 삭제 권한 불필요·보존 기간 미결
    - `handoff/flowtest/README.md`: 하루 호출량(조위 약 1,320건 · 전체 약 1,350건), 알려진 한계에서 조위 다중 페이지 항목 정리(이번 이미지부터 해소), 운영 큐·원문 저장소 접속 정보가 있으면 실행기가 멈춘다는 점
12. **테스트 — 아래 2절**

## 2. 통과 기준

계획서 7.11절 표가 기준이다. 아래는 이 지시서에서의 실행 조건과 덧붙임이다.

| # | 기대 |
| --- | --- |
| J1~J8 | 7.11절 그대로. NATS JetStream 서버를 테스트 컨테이너로(`-js` 옵션). J2는 **소비자마다** 커밋 성공 → 발행 실패 → 재전달 경로를 만들고 7.11절의 소비자별 기준으로 본다(grading `farm_reading_history` 1행 증가·evaluation `result.updated` 중복은 허용 — 건수를 보고). J3은 `max_deliver`를 정의 파일에서 읽고 재전달 간격을 줄여 주입한다. J8은 ① 계약 컨슈머가 이미 있을 때 발행 → 뒤에 뜬 소비자가 받음 ② (기록용) 컨슈머가 하나도 없는 Interest 스트림에 발행한 메시지가 남는지 — **결과를 보고서에 그대로 적는다** |
| O1~O5 | 7.11절 그대로. MinIO 테스트 컨테이너. O1의 E3 재실행은 `tide`·`bulletin` 두 경로(시각 고정 또는 `storage_key`·`raw_id` 비교 제외). O3는 "DSN 없음 → 운영 진입점 멈춤" 포함 |
| T1~T3 | 7.11절 그대로. 가짜 HTTP 호출층(7.9절 방식)으로 요청 변수·호출 수를 기록해 확인. T2는 실행 시작 시각을 KST 00:29:59 / 00:30:00(경계 직전·직후)으로 고정하고, 보충 원문의 `obs.loaded` 0건·`adapter_health` 변화 없음, 조위 정기·`_y` `load_id` 64자 이하, 23:59:59 시작 실행의 자정 뒤 호출이 `reqDate` = 새 날짜·보충 아님까지 |
| T4 | 작업 2 — 7.11절 ①~④ |
| T5 | 7.11절 그대로(결과 코드 대응) |
| V1 | 7.11절 그대로 |
| 기존 회귀 | 7.4(개정 22 항목 포함 — 생성본 스키마·고유 키), 7.9 E1~E7, 7.10 FT1~FT6, N1~N7·N15·N16, SD1~SD4, K1~K9 — 전부 통과. 기존 테스트를 약하게 해서 통과시키지 않는다 |
| 판별력 | J1(비교 필드)·J2·J3·J7·J8·O2·O3·T1·T2·V1은 해당 구현을 끈 상태(예: 전체 필드 비교, ack을 처리 전으로, `uuid4` 복원, 소진 처리 제거, Msg-Id를 실행 ID만으로, 조건부 쓰기 제거, 기본 경로 대체 복원, 페이지 루프 복원, 자정 분기·보충 원문 분기 제거, 널 거부)에서 한 번 실패를 확인하고 보고서에 적는다 |
| 이미지 | 6종 빌드·import 성공, 이미지 안에 `.env`·`operational*.yaml`·MinIO 계정 없음 |
| 회귀 | 전체 `pytest`(DB·컨테이너 포함), `PYTHONIOENCODING=utf-8 python ci/gate/run_gate.py --warn-pending` 통과, `python ci/scan_keys.py` 0건 |

기준선(2026-10-06, 작업 시작 전): 전체 `pytest` **666 passed · 14 skipped**(`IDW_OUTPUT_DIR` 미설정 시). Docker Desktop이 꺼져 있으면 컨테이너 테스트가 실패한다 — `C:\Users\USER\AppData\Local\Programs\DockerDesktop\Docker Desktop.exe` 실행 후 `docker info`. 컨테이너 이미지(NATS·MinIO)를 처음 받는 시간은 보고서에 적는다.

**처리 시간 측정**: processor가 정선 1년 원문(픽스처)·어장환경 원문을 처리하는 시간을 재서 보고한다(`ack_wait` 30초 판단 근거 — 2.2절).

## 3. 순서 · 중단 조건

- 순서: **확인 게이트 → 1 → 2(T4) →** 3·4(구현과 J·O 테스트) → 5 → 6(V1·J2) → 7(T1~T3) → 8(T5) → 9 → 10 → 11 → 회귀
- **확인 게이트**: 시작 전에 계획서 작업 트리에 2.2절 "JetStream 구성", 2.3절 "S3 구성", 1.2절 "요청 (개정 22)"·"자정 경계" 행, 7.11절(T5 포함)이 있는지 확인한다. 없으면 멈춘다
- **T4 결과가 1.2절과 다르면 멈추고 보고** — 그 뒤 작업을 하지 않는다(조위 설계가 그 가정 위에 있다)
- 계획서 2.2·2.3절이 정하지 않은 동작이 필요한 곳, 계획서·skill·코드가 다르게 읽히는 곳, 단계 처리 로직을 바꿔야만 되는 곳 → **멈추고 보고**(고르지 않는다)
- JetStream이 계획서 서술과 다르게 동작하면(J8 등) 구현을 그 동작에 맞춰 바꾸지 말고 **결과를 보고**한다 — 설계 판단은 이 세션이 한다
- T4에서 예산을 넘길 상황, `KEY_ERROR`·`QUOTA`가 나오는 상황 → 그 자리에서 멈추고 보고(다른 키·관측소·날짜로 바꿔 다시 부르지 않는다). 실제 호출에서 드러난 이상은 "기존 경고"로 넘기지 말고 보고서 2절에 적는다

## 4. 산출물

- `common/queue/`(JetStream 구현·수신 루프), `common/raw_store/`(S3 구현·덮어쓰기 금지·키 밀리초·선택 규칙), `common/http/`(`_fetched_ms`), 컨슈머·발행 진입점 연결, interpolation·grading(실행 ID 결정화·`queue-v2`), `collector/adapters/tide/`, processor(보충 원문), `common/classifier/`, `common/contract_check/`, `flowtest/`
- `contracts/queue/queue-v2.json`·스트림 정의 파일, `config/definitions.yaml`·`ci/gate/expected.yaml`(`contracts`), `contracts/release/image_notice.json`
- `pyproject.toml`, `handoff/flowtest/README.md`
- `tests/`(J·O·T1~T3·T5·V1·판별력 — T4는 수동 실행 기록)
- `docs/reports/I-18_result.md` — 계획서 A.5 양식: 실행 시각 / **호출 수(T4, 예산 대비)** / 참조한 skill과 상태("작업 트리, 개정 22 반영본") · 0 실행 전 확인(1번 현황 표 포함) · 1 판정표(위 2절 각 행: 통과/실패/검사 무효/실행 안 함) · 2 예상과 달랐던 결과(API 특성 / 우리 코드·명세 결함 — T4·J8 결과, 처리 시간 포함) · 3 새로 발견한 함정 · 4 계획서 반영 후보(구현한 *(제안)*, 새 환경변수·인자 이름, 만난 `<미결>`) · **부록: 인프라 요청 목록**(작업 11). 변경 파일 목록, 제안 커밋 메시지

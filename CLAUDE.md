# CLAUDE.md — api-module

이 파일은 `docs/plan/`의 **API 모듈 제작계획서**(이하 "계획서") 첨부 A.2에 따라 만든, **모든 작업에 항상 적용되는 규칙과 용어**다. 방법은 skill(`.claude/skills/`)에, 작업 단위는 지시서(`docs/instructions/`)에 있다.

- 괄호 속 "N절"은 **계획서의 절 번호**다. "v1.5 N절"은 통합계획서 v1.5의 절이다 — 판단에 필요한 사실은 계획서에 값으로 있다
- 이 파일은 **계획서 개정과 같은 커밋에서만** 고친다. 지시서 수정사항으로 고치지 않는다
- 값·임계·`<미결>` 목록·진행 상태는 여기에 없다 — 계획서 10·11절이 원천이다

---

## 1. 이 저장소와 우선순위

**이 저장소는 API 모듈만 담는다.** 공공 API 호출부터 **판정이 끝난 결과를 DB에 적재하기까지** — 원문 보관 → 해석 → 정규화 → 품질 판정 → 적재 → IDW 추정 → 출처 등급 → 침묵 판정 → 결과 테이블. **판정은 모듈, 표시는 대시보드**다: 무엇을·어떻게·언제 보이고 보낼지(배지, 문구, 노출, 발송 시점)는 웹 서비스가 정하고, 이 모듈은 요구사항을 대시보드 계약(5.5절)으로 넘긴다. 영역 판정과 무관하게 **계산할 수 있었던 값·오차·시각은 저장**한다. (0.1·0.2절)

**충돌할 때의 우선순위** (A.1)

1. **이 파일의 실행자 규칙과 금지 규칙**(아래 2·3번 항목)이 최우선이다. 지시서 머리말이 **명시적으로 해제한 것만** 예외다 — 현재 I-11·I-13·I-17·I-18의 공공 API 호출
2. 그 밖의 사실·방법은 **수정사항 > 지시서 > skill > 이 파일의 공용 용어** 순이다. 수정사항은 그 지시서 실행에만 적용되고 계획서를 바꾸지 않는다
3. 수정사항 밖에서 파일끼리, 또는 파일과 계획서가 다르면 **갱신 누락**이다. 어느 쪽도 고르지 말고 **멈춰 차이를 보고**한다

---

## 2. 실행자 규칙 (12.1절)

- **`<미결>`은 설정 키로만 두고 값을 넣지 않는다.** 기본값을 추정해 채우지 않는다. 임계에 의존하는 테스트는 **임계에 상대적으로**(임계 직전 / 직후) 짠다
- ***(제안)* 표시는 구현하되 확정으로 다루지 않는다.** 보고서 "계획서 반영 후보"에 그 항목을 적는다
- **결정하지 않는다** — 채택·폐기·임계값·표시 정책은 "제안만"
- **인증키 값과 DB 연결 문자열(비밀번호 포함)을 읽어 출력하지 않는다.** 명령·로그·보고서·커밋에 나오면 안 된다. 원문 키 검사는 **고정 스크립트 `ci/scan_keys.py`로만** 하고, 결과는 일치 건수만 보고한다
- **공공 API를 호출하지 않는다.** 이 금지는 **지시서 머리말의 명시적 선언으로만** 해제된다 (현재 I-11·I-13·I-17·I-18만). 실행자가 스스로 추론해 해제하지 않는다
- **판단에 필요한 사실은 계획서의 값으로 쓴다.** 계획서에 값이 없고 외부 문서(v1.5 등) 절 번호만 있으면, 추정하지 않고 멈춰 보고한다

---

## 3. 금지 규칙 (12절)

- collector에서 판정하지 않는다 — **수집 범위를 정하는 사전 읽기만** 허용한다(2.1절)
- 원문을 자르거나 재직렬화하지 않는다 — **여러 응답을 합쳐 원문을 만들지 않는다**(원문 하나 = 응답 하나, 2.3절)
- **원문을 덮어쓰지 않는다** — 같은 키가 있으면 쓰지 않고 실패로 드러낸다(2.3절)
- **큐 메시지를 처리(DB 커밋·다음 알림 발행)가 끝나기 전에 ack하지 않는다**(2.2절)
- 큐·원문 저장소 연결이 없거나 실패할 때 **인메모리 큐·로컬 디스크로 조용히 대체하지 않는다** — 멈추고 보고한다(2.2·2.3절)
- HTTP 상태코드·`resultMsg`로 판정하지 않는다
- 빈 결과 코드를 정상으로 정규화하지 않는다
- 실패한 호출을 다른 창·파라미터로 자동 대체하지 않는다
- `12`를 폐기로 판정하지 않는다
- 방언 분기를 `dialect.py` 밖에 쓰지 않는다
- DB `ENUM`, `JSONB` 연산자, 배열 타입을 쓰지 않는다
- 문자열 비교를 DB 콜레이션에 맡기지 않는다 — 정규화 키로 한다
- `0.000`·빈 값 레코드를 버리지 않는다 — 결측으로 저장한다
- **마이그레이션을 만들거나 운영 DB 스키마를 바꾸지 않는다** — 테이블이 없으면 멈추고 보고한다
- **운영 DB에 해역 시드를 쓰지 않는다** — 적용은 DB 소유 측, 이 모듈은 적용 SQL 생성본까지(4.3절)
- **인계한 매니페스트를 이 저장소에서 고쳐 배포하지 않는다** — 변경은 인프라에 요청한다
- CI는 **이미지 알림만** 보낸다 — manifest 레포의 파일을 커밋하거나 PR을 열지 않는다
- **판정 정의** 값을 바꾸면서 **게이트 기준 문서를 같이 고치지 않는 커밋**을 올리지 않는다 (게이트가 막는다). 운영 조정·워크로드 값은 기준 문서에 적지 않는다
- 단계 전용 코드(`collector/`·`processor/`·`interpolation/`·`grading/`·`evaluation/`)끼리 **서로 가져다 쓰지 않는다** — 공유할 것은 `common/`으로 옮긴다. 이 규칙이 깨지면 선택 빌드가 틀린다. 예외는 시험 실행기 `flowtest/`가 단계를 가져다 쓰는 것 하나 — 단계 코드는 `flowtest/`를 가져다 쓰지 않는다(2.1.1절)
- **시험 실행기 `flowtest`를 운영 워크로드로 쓰지 않는다** — 운영 인계 매니페스트(`handoff/k8s/`)·CI·이미지 알림에 넣지 않는다. 시험용 매니페스트는 `handoff/flowtest/k8s/`에만 둔다. 실행기 때문에 단계 코드의 **동작**을 바꾸지 않는다 — 허용은 기동 시 검사·구독 조합을 함수로 꺼내는 행위 보존 추출뿐이다(2.1.1절)
- 계약 버전이 다른 알림·테이블을 **조용히 읽지 않는다** — 멈추고 보고한다
- 계산값(`derivation = COMPUTED`)에 `alertable = true`를 주지 않는다
- 추정이 멈췄을 때 **최근접 관측값으로 대체하지 않는다** — `NONE`으로 둔다
- 단계 간 알림이 오지 않은 처리 단계를 **주기 실행으로 대신 돌리지 않는다.** 예외는 둘이고 어느 쪽도 앞 단계를 대신하지 않는다 — `evaluation-sweep`은 판정만, `interpolation-error`는 오늘의 오차만 만든다(2.2절)
- 양식장 좌표를 쓰거나 고치지 않는다 — 읽기만
- **사용자 알림**을 발송하지 않는다 — 발송은 웹 서비스(`alert-svc`)
- 원문·로그·픽스처에 **인증키를 남기지 않는다** — `url`·`params`·`final_url` 모두 마스킹(2.3절)
- 배지·화면 문구·노출 여부·발송 시점을 결과 테이블에 넣거나 정하지 않는다 — 대시보드 계약(5.5절)
- `provenance = NONE`이라는 이유로 계산된 값을 버리지 않는다 — 영역 판정과 값 저장은 별개다(4.8절)
- 워크로드 설정(CronJob 주기)을 게이트 기준 문서에 넣지 않는다 — 인계 후 인프라 소유(7.7절)
- 운영 조정 값을 이미지에 넣거나 게이트 기준 문서에 적지 않는다 — 스키마로만 본다(2.0.6절)
- 운영 조정 ConfigMap이 없거나 스키마와 다를 때 **기본값으로 대체해 기동하지 않는다** — 멈추고 보고한다
- 판정 정의(`chlorophyll: null` 등)를 운영 조정으로 옮기지 않는다 — 값의 의미가 인프라 변경으로 바뀌게 된다

---

## 4. 경로 규칙 (2.0.2절)

| 규칙 | 내용 |
| --- | --- |
| 절대경로 | 저장소 안에 쓰지 않는다. 저장소 밖 검증 폴더는 **별칭**(`$SRC_API`·`$SRC_IDW`·`$SRC_C`)으로만 부른다 (6.2절) |
| DB | **마이그레이션을 만들지 않는다.** 테이블 모델은 `common/repository/tables.py`, 정의 제안은 `contracts/tables/` |
| 인프라 | 매니페스트는 `handoff/`에 **초기본만.** 인계 후 원본은 인프라 저장소 |
| 픽스처 | **`fixtures/`에만.** 테스트는 여기를 참조한다 |
| 설정 | 세 종류로 나눈다 (2.0.6절). **판정 정의**는 `config/definitions.yaml` — 이미지에 포함, CI 게이트가 대조. **운영 조정**은 ConfigMap — 인계 후 인프라 소유, 초기값은 `config/operational.initial.yaml`. **워크로드 설정**(CronJob 주기 등)은 `handoff/HANDOFF.md`에 권장값으로만 |
| 계획서·지시서·보고 | `docs/plan/`, `docs/instructions/`, `docs/reports/` |
| 이미지 이름 | `api-module/collector`·`processor`·`interpolation`·`grading`·`evaluation` (2.1절). 시험 전용 `api-module/flowtest`(2.1.1절 — 운영 워크로드 아님) |
| Dockerfile | **`docker/<이미지>/Dockerfile`** — 이미지마다 하나. 공통 코드·`config/definitions.yaml`과 해당 단계 코드만 복사한다. **`evaluation`은 운영 조정 게이트용 합성 픽스처(`fixtures/synthetic/`)도** 복사한다(2.0.6절). **`processor`·`evaluation`은 운영 조정 스키마(`contracts/config/operational.schema.json` — 기동 시 검사용 계약, 값 아님)를, `processor`는 적조 해역 시드(`seeds/` — 별칭 정규화, 4.3절)도** 복사한다. 운영 조정 값은 이미지에 넣지 않는다. **`flowtest`는 예외로 단계 코드 5종과 `flowtest/`, 위 시드·스키마를 모두** 복사한다 — 운영 조정 값·인증키·DB 연결 문자열은 넣지 않는다(2.1.1절) |
| 의존성 | `pyproject.toml`의 **이미지별 선택 의존성**으로. 한 단계의 라이브러리 갱신이 다른 이미지에 번지지 않게 한다 |
| k8s 리소스 이름 | 2.1절 표 |
| 레지스트리 주소 | 코드·매니페스트에 쓰지 않는다. **CI 변수 `REGISTRY` 하나**로 둔다 — 현재 GitLab Container Registry, ECR 전환 가능. 예외: 시험 실행기 전달물(`handoff/flowtest/`)에는 시험 후 폐기할 시험 저장소 주소를 적는다(2.1.1절) |

---

## 5. 로컬 배치 확인 (2.0.7절)

작업을 시작하기 전에 아래가 있는지 확인한다. **없으면 멈추고 보고한다.** 파일 내용(특히 `.env`의 키 값)은 읽어 출력하지 않는다.

| 파일 | 구분 |
| --- | --- |
| `CLAUDE.md`, `.claude/skills/<이름>/SKILL.md`, `docs/plan/` 계획서 | 커밋됨 |
| `.env`(API 키·요청주소·DB 연결 문자열), `.env.sources` | 로컬에만 (커밋 금지) |
| 검증 폴더 `$SRC_API`·`$SRC_IDW`·`$SRC_C`, `$SRC_IDW/output/observations.csv` | 저장소 밖 로컬 경로 |
| 로컬 운영 조정 파일 (`OPERATIONAL_CONFIG_PATH`) | 로컬에만 — I-11에서 필요 |

도구: **Docker** (고른 DB의 테스트 컨테이너 — PostgreSQL 16 또는 MySQL 8.0, 이미지 빌드). DB 연결은 `.env.example`의 두 DB 양식 중 하나의 주석을 풀어 `.env`에 쓴다(계획서 5.4절)

---

## 6. 공용 용어

여러 skill이 같은 이름을 쓰므로 **여기에만 정의한다.** skill은 다시 정의하지 않고 이 절을 참조한다.

**저장소·알림** (2.0.2절)

| 규칙 | 내용 |
| --- | --- |
| 용어 — 저장소 | "저장소"는 Git 저장소, 원문을 두는 곳은 **객체 저장소**, DB에 쓰는 코드는 **DB 접근 계층**(`common/repository/`)으로 구분해 부른다 |
| 용어 — 알림 | **사용자 알림**(문자·푸시 — 웹 서비스가 발송, 이 모듈은 보내지 않음) / **단계 간 알림**(큐 메시지, 2.2절) / **이미지 알림**(manifest 레포로, 2.0.5절) 셋을 구분해 부른다. "알림"만 쓰지 않는다 |

**설정 세 종류** (2.0.6절)

| 구분 | 무엇 | 둘 곳 · 소유 | 지키는 것 |
| --- | --- | --- | --- |
| **판정 정의** | 값을 바꾸면 "그 값이 무엇을 뜻하는가"가 바뀌는 규칙 | `config/definitions.yaml`, 이미지에 포함 · 이 모듈 | CI 게이트(7.7절 ①·②) |
| **운영 조정** | 운영하며 맞출 임계 | ConfigMap · 인계 후 인프라 | 스키마 검사 + 판정 재생 + 기동 시 검사 |
| **워크로드** | CronJob 주기 | 매니페스트 · 인계 후 인프라 | 없음 — `HANDOFF.md` 권장값 |

어느 키가 어느 쪽인지는 2.0.6절 "키별 구분" 표가 기준이다.

**결과 코드 → 상태 이름** (3.2절) — 코드·계약·픽스처는 "이 모듈의 이름"을 쓴다

| 코드 | 상태 (이 모듈의 이름) | 분류 (v1.5 4.5절) | v1.5 7.3절 설정 이름 |
| --- | --- | --- | --- |
| `00` + 행 있음 | `OK` | 정상 | `OK` |
| `00` + 0행 | `OK_EMPTY` | 정상적 침묵 | — |
| `03` | `NO_DATA` | 조건 불일치 | `NO_MATCHING_DATA` |
| `41` (·`40` *(제안)*) | `SUSPENDED` | 관측 항목 일시 중단 (`40` 관측소 서비스 일시 중지 — 같은 분류) | `ITEM_UNAVAILABLE` |
| `05` | `TIMEOUT_05` (재시도 후) | 서버 타임아웃 | `SERVER_TIMEOUT` |
| `10` / `11` | `BAD_REQUEST` — **우리 버그** | 요청 오류 | `BAD_REQUEST` / `MISSING_PARAM` |
| `12` | `NO_SERVICE` — **폐기로 판정하지 않는다**, 경로 확인 | 요청 오류 *(제안)* | — |
| `20`·`22`·`30`·`32` (·`21`·`31`·`33` *(제안)*) | `KEY_ERROR` / `QUOTA`(`22`만) | 요청 오류 / 진짜 장애 *(제안)* | — |
| 그 외 코드 | `API_ERROR_<code>` | 진짜 장애 *(제안)* | — |
| **코드를 못 찾음 / 빈 값 / 공백** | **`PARSE_FAILURE`** | 파싱 실패 | `PARSE_FAILURE` |
| HTTP 오류·연결 실패 | `HTTP_ERROR` / `NET_ERROR` | 진짜 장애 | — |

- **코드의 뜻은 제공 기관마다 다르다** — `04`는 data.go.kr에서 HTTP 에러, NIFS에서 "check parameter"라 공통 대응이 없다(`API_ERROR_04`, 3.2절)

그 밖의 상태·플래그 이름: `INCOMPLETE`·`FILTER_IGNORED`(3.3절), `STATION_INACTIVE`·`STALE_SUSPECT`(4.1절), `MISSING`·`SENSOR_QUALITY`·`STALE`(4.6절)

**축 상태 값** (4.9절) — `axis_status.state`에 쓰는 값. 분류마다 상수 하나이고, 사유는 `reason`에 둔다. `provenance`의 `NONE`을 상태 자리에 쓰지 않는다. 응답 상태(3.2절)는 호출 한 번의 결과이고, 이것은 **축의 상태**다

| 분류 | `state` | 어디서 오는가 |
| --- | --- | --- |
| 정상 | `NORMAL` | 신선도 임계 안의 최신 값 |
| 정상적 침묵 | `NORMAL_SILENCE` | `OK_EMPTY`, 적조 속보 없음(호출은 성공) |
| 게시 대기 | `PUBLICATION_PENDING` | 게시 감시 0건 |
| 조건 불일치 | `NO_MATCH` | `NO_DATA`(`03`) |
| 관측 항목 일시 중단 | `ITEM_SUSPENDED` | `SUSPENDED`(`41`·`40` *(제안)*) |
| 커버리지 밖 | `OUT_OF_COVERAGE` | `axis_coverage` 선언, `STATION_INACTIVE` |
| 계절 밖 | `OUT_OF_SEASON` | `axis_coverage.season_months` — **계절 밖 판정의 유일한 원천** |
| 값 멈춤 — 확인 중 | `VALUE_FROZEN` | `STALE_SUSPECT` 플래그 |
| 확인 불가 | `STALE` | 신선도 임계 초과, 원인 미상(R5) |
| 서버 타임아웃 | `SERVER_TIMEOUT` | `TIMEOUT_05` |
| 요청 오류 | `REQUEST_ERROR` | `BAD_REQUEST`, `NO_SERVICE`, `KEY_ERROR` |
| 파싱 실패 | `PARSE_FAILURE` | `PARSE_FAILURE`, `INCOMPLETE` |
| 진짜 장애 | `OUTAGE` | `HTTP_ERROR`, `NET_ERROR`, `QUOTA` |
| 필터 무시 | `FILTER_IGNORED` | `FILTER_IGNORED` |
| 추정 지연 | `INTERPOLATION_STALE` | sweep 판정 |
| 산출 지연 | `GRADING_STALE` | sweep 판정 |
| 값 사용 불가 | `NOT_USABLE` | `farm_readings.provenance = NONE` — `reason`은 `none_reason`을 옮긴 것(`INVALID_COORDS`·`EXCLUDED_ZONE`·`SURFACE_RULE_UNDECIDED` 등) |

- 빈 값 레코드는 **행 단위 결측**이라 축 상태가 아니다. 축은 그 결과 `STALE`이나 `NOT_USABLE`로 드러난다
- 응답 상태 → 분류 대응 중 `NO_SERVICE`·`KEY_ERROR`·`QUOTA`·`INCOMPLETE`는 3.2·3.3절의 *(제안)* 대응을 따른다

겹치면 계획서 4.9절 "상태가 겹칠 때의 우선순위"를 따른다(주인 `evaluation`).

**시각** (5.2절) — 모든 시각은 **UTC `DATETIME`(naive)**으로 저장하고 이름에 **`_utc`**를 붙인다. KST 변환은 애플리케이션에서 한다. 예외: 원문 저장 형식의 `fetched_at`(v1.5 확정 형식) — DB 색인 행은 `fetched_at_utc`

**결과 테이블 필드의 의미** (5.5절)

| 필드 | 뜻 | 뜻하지 않는 것 |
| --- | --- | --- |
| `derivation` | 값의 유래 — `COMPUTED`(계산) / `MEASURED`(인근 실측) / `OFFICIAL`(기관 발표) / `SURVEY`(조사값) | — |
| `provenance` | 영역 판정 — 오차·방법 기준 등급. `NONE`은 **신뢰 기준 밖** | 배지. `NONE`이 "값 없음"을 뜻하지 않는다 |
| `none_reason` | `grading`이 기록한 `NONE` 사유 | 화면 표시용 사유가 아니다 — 표시는 `axis_status.reason` |
| `lower` · `upper` | 수온: `value` ∓ 오늘의 오차 P95 / 적조 위험도 지수(`red_tide_risk`): 입력의 불확실성(수온 오차 범위, 빠진 항목)이 만드는 지수 범위(4.10절) | 최솟값·최댓값이 아니다 |
| `source_ref` | 근거 원천 행의 키 — 수온 `run_id` / 인근 실측 `station_id` / DO·클로로필 `station_id@observed_at_utc`(조사·관측 시각, UTC ISO — 개정 14) / 적조 `cod_news#seq` | 사람이 읽는 설명이 아니다 |
| `validated_scope` | 계산값의 **검증 범위** — `STATION_SITES`는 관측소 위치에서만 교차검증했다는 뜻. 계산값(`COMPUTED`)에만 채운다 | 만 안쪽 양식장의 추정이 검증됐다는 뜻이 아니다 — **만 안쪽은 미검증** |
| `alertable` | **발송 자격** — 계산 시점의 정적 자격 | 지금 보내라는 뜻이 아니다. 신선도를 담지 않는다 — 발송 후보는 `axis_status`와 함께 본다(계획서 5.5절 W5) |
| `bulletins.grade` · `bulletin_details.grade` · `farm_readings.grade` | 적조 공식 4단계 `NONE`(예비특보 미만) / `PRE_ADVISORY` / `ADVISORY` / `WARNING`, 그리고 `NOT_GRADED`(비대상 종) · `UNKNOWN`(원인생물·밀도·세부 행 없음) | 여기의 `NONE`은 `provenance`의 `NONE`(신뢰 기준 밖)과 **다르다**. `farm_readings.grade`는 `grading`이 고른 현재값 행의 등급이다 — 대시보드가 다시 고르지 않는다 |
| `axis_status.state`·`reason` | 침묵 분류(4.9절 상태 값 17종)와 그 사유. 겹치면 4.9절 우선순위 | 화면 문구. `provenance`의 `NONE`과 다르다 — 값을 못 쓰는 경우는 `NOT_USABLE` |
| `farm_areas.area_id` | 모듈이 정한 양식장 해역 — 반경 안 해역 중 중심이 가장 가까운 하나(`rule`). 커버리지 밖·계절 밖 판정에 쓴 해역이다(개정 15) | 행정구역·어업권 구역이 아니다. 적조 속보 대응은 반경 안 해역을 모두 쓴다 — 이 열 하나로 적조 해역을 다시 고르지 않는다 |
| `risk_index_factors.contribution` · `ok` · `excluded_reason` | 적조 위험도 지수 항목의 기여도(= 가중치 × 점수, 제외 항목 0 — 네 행의 합 = 지수 `value`), 합산 사용 여부, 제외 사유 코드(`NO_INPUT`·`INPUT_NONE`·`SENSOR_QUALITY`·`RULE_UNDECIDED`) (4.10절, 개정 20) | 화면 문구가 아니다 |
| `risk_index_levels.level` · `level_at_lower` · `level_at_upper` · `level_straddle` | 지수 `value`·`lower`·`upper`의 단계 코드와 경계 걸침 — **모듈이 판정**한다(4.10절) | 적조 공식 등급(`grade`)이 아니다. 대시보드가 `value`를 잘라 단계를 다시 만들지 않는다 |
| `observed_at_utc` · `computed_at_utc` · `basis_utc` · `last_checked_utc` | 관측 시각 · 산출 시각 · 판정에 쓴 가장 새 입력의 시각 · 판정 시각 | — |

**축 키 이름** *(제안 — 11절)*: `water_temp`·`salinity`·`tide_level`·`wind_speed`·`air_temp`·`red_tide`·`dissolved_oxygen`·`chlorophyll`·`red_tide_risk`(개정 20 — 적조 위험도 지수, 파생 축)

---

## 7. 불변식 (4.8절)

- **`derivation = COMPUTED`인 행의 `alertable`은 언제나 `false`다** — 전 픽스처에서 N11로 검사한다
- **`provenance = NONE`이어도 계산할 수 있었던 `value`·`lower`·`upper`는 저장한다.** `NONE`은 "값 없음"이 아니라 "신뢰 기준 밖"이라는 영역 판정이다

---

## 8. 지시서·skill 쓰는 법 (A.5)

1. **지시서 머리말부터 읽는다** — 대상 단계, 선행 지시서, 적용 수정사항, 공공 API 호출 허용 여부, **읽을 skill**
2. **머리말에 적힌 skill을 먼저 읽는다.** 설명(description)이 맞아 보여도 지시서가 부르지 않은 skill에 기대지 않는다
3. 작업·통과 기준·산출물·보고 양식은 **지시서에 있다.** 1회성 작업(I-0 골격·픽스처 반입, I-10 빌드·CI, I-11 인계)의 방법도 지시서 본문에 있다
4. 보고서에는 **참조한 skill과 그 커밋**을 적는다. 구현한 *(제안)*과 만난 `<미결>`은 "계획서 반영 후보"에 적는다
5. skill과 이 파일은 **지시서 수정사항으로 고치지 않는다.** 계획서 결함이면 멈추고 보고한다 — 계획서 개정 후 같은 커밋에서 함께 갱신한다(A.8)

**skill 목록** (A.3): `common-core` · `repository` · `tide` · `bulletin` · `line` · `fishery` · `interpolation` · `grading` · `evaluation`

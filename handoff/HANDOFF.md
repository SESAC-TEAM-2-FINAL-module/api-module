# HANDOFF.md — 인프라 인계 내역 (계획서 2.0.4절)

작성 2026-09-30 · I-11 완료

---

## 1. 워크로드 목록과 역할

| 워크로드 (k8s 이름) | 이미지 | 실행 형태 | 시작 계기 | 역할 |
|---|---|---|---|---|
| `collector-tide` | `api-module/collector` | CronJob, 10분 | 시각 | dtRecent 9개소 → 원문 → `raw.fetched` |
| `collector-bulletin-season` | `api-module/collector` | CronJob, 1시간 | 시각 | redtideList 최근 30일 창 (시즌 5~10월). 날짜 필터가 조사일 기준이라 늦게 등록되는 속보(최대 14일 관측)를 덮도록 30일 — 계획서 1.3·2.1절(개정 18) |
| `collector-bulletin-offseason` | `api-module/collector` | CronJob, 6시간, 기본 중단 | 시각 | redtideList 최근 30일 창 (비시즌 11~4월, suspend 해제 필요) |
| `collector-line` | `api-module/collector` | CronJob, 1일 | 시각 | sooList 1년 창 |
| `collector-fishery-watch` | `api-module/collector` | CronJob, 주 1회 | 시각 | femoSeaList 건수 감시 → 변화 시 같은 실행에서 전량 수집 |
| `collector-fishery-backfill` | `api-module/collector` | Job, 수동 | 수동 | 과거 연도 보관 (연속 2개 연도 0건이면 정지) |
| `collector-completeness` | `api-module/collector` | CronJob, 주 1회 | 시각 | 정선·어장환경 완전성 수집 — 같은 실행에서 단일 창 1회 + 월 분할(적조는 제외 — processor의 직전 원문 대조로 본다, 계획서 3.3절 개정 18). 원천을 마치면 `completeness.collected` 알림. 분할 원문에는 `raw.fetched`를 내지 않는다(processor 큐 부하 없음). 비교 결과는 운영 기록 `completeness_checks`(계획서 3.3절) |
| `processor` | `api-module/processor` | Deployment, 큐 컨슈머 | `raw.fetched` | 해석·정규화·품질·적재 → `obs.loaded` |
| `reprocess` | `api-module/processor` | Job, 수동 | 수동 | 원문 ID 범위 재처리 (파서 수정 후) — `--raw-id-from N --raw-id-to M`, 원문 ID = `raw_index.id`(양끝 포함). 파서 버전을 올린 이미지로 돌린다 — 같은 버전이면 아무것도 쓰지 않는다 |
| `interpolation` | `api-module/interpolation` | Deployment, 큐 컨슈머 | `obs.loaded`(조위) | IDW 추정·오차 → `interp.done` |
| `interpolation-error` | `api-module/interpolation` | CronJob, 1일 | 시각 | 오늘의 오차만 산출 (추정값 대신 돌리지 않음) |
| `grading` | `api-module/grading` | Deployment, 큐 컨슈머 | `obs.loaded`(전 축) + `interp.done`(수온) | 출처 등급·alertable → `grade.done` |
| `evaluation` | `api-module/evaluation` | Deployment, 큐 컨슈머 | `grade.done` | 침묵 분류 종합 → 결과 테이블 → `result.updated` |
| `evaluation-sweep` | `api-module/evaluation` | CronJob, 10분 | 시각 | 신선도·단계 지연 점검만 (앞 단계 대신 돌리지 않음) |

---

## 2. 필요한 환경변수와 비밀 (키 이름만)

`handoff/k8s/secrets-template.yaml` 참고. 모든 민감한 값은 `api-module-secrets` Secret에.

| 변수명 | 용도 | 비고 |
|---|---|---|
| `DTRECENT_KEY` | data.go.kr 조위관측소 API 키 | 통합 인증키 1종 — 포털 발급 원문 그대로 입력 (미리 URL 인코딩하지 않는다, httpx가 처리) |
| `DTRECENT_URL` | 조위관측소 엔드포인트 | `.env.example` 값 그대로 사용 |
| `NIFS_KEY_BULLETIN` | NIFS 적조정보 키 | nifs.go.kr 자체 키 (data.go.kr 키 호환 안 됨) |
| `NIFS_KEY_LINE` | NIFS 정선해양관측 키 | 동일 |
| `NIFS_KEY_FISHERY_SEA` | NIFS 어장환경 키 | 동일 |
| `NIFS_URL` | NIFS 엔드포인트 | `https://www.nifs.go.kr/OpenAPI_json` (리다이렉트 경로 `/api/OpenAPI_json` 포함, httpx follow_redirects=True) |
| `DATABASE_URL` | DB 연결 문자열 | PostgreSQL 또는 MySQL (확정 전까지 양쪽 DDL 존재) |
| `QUEUE_DSN` | 큐 연결 | NATS 또는 SQS (v1.5 10.3(b) 미결 — common/queue/ 인터페이스) |
| `RAW_STORE_DSN` | 객체 저장소 연결 — **구현 전 자리** | S3/GCS/MinIO (v1.5 12.1절 미결). **현재 이미지는 로컬 디스크(`RAW_STORE_PATH`)만 구현돼 있고, `RAW_STORE_DSN`이 있으면 기동을 멈춘다**(로컬로 조용히 대체하지 않음). 객체 저장소 구현 이미지가 나오기 전에는 매니페스트 `env`(주석 처리됨)와 Secret `api-module-secrets`(`envFrom`으로 전부 주입) 어디에도 이 키를 넣지 않는다. 로컬 디스크는 파드 간에 공유되지 않으므로, 그 전까지 collector → processor 원문 전달은 같은 볼륨을 쓰는 시험 환경에서만 동작한다 |
| `OPERATIONAL_CONFIG_PATH` | 운영 조정 파일 경로 | ConfigMap 마운트 경로 (`/config/operational.yaml`) — processor·evaluation·evaluation-sweep |

---

## 3. 외부 egress 대상

| 대상 | 프로토콜 | 포트 | 용도 |
|---|---|---|---|
| `apis.data.go.kr` | HTTPS | 443 | 조위관측소 API (dtRecent) |
| `www.nifs.go.kr` | HTTPS | 443 | NIFS 3종 API |
| `www.nifs.go.kr` → `/api/OpenAPI_json` | HTTPS | 443 | NIFS 리다이렉트 경로 (동일 호스트) |
| DB 호스트 | TCP | 5432(PG) 또는 3306(MySQL) | DB 연결 |
| 큐 호스트 | TCP | 큐별 | 단계 간 알림 |
| 객체 저장소 | HTTPS | 443 | 원문 저장 |

---

## 4. 접속 요구

| 자원 | 권한 | 용도 |
|---|---|---|
| DB (`aquasentinel` 데이터베이스) | SELECT · INSERT · UPDATE | 모든 단계 |
| 객체 저장소 버킷 | GET · PUT | collector(PUT), processor(GET) |
| 큐 주제/큐 | PUBLISH + SUBSCRIBE | 단계별 |
| **양식장 좌표 테이블** | SELECT | interpolation · grading · evaluation-sweep — 읽기만, 이 모듈은 쓰지 않는다 |

---

## 5. 워크로드 설정 권장값과 근거

| 워크로드 | 권장 주기 | 근거 |
|---|---|---|
| `collector-tide` | 10분 | 계획서 1.1절 — 관측 갱신 간격 3.6~15.4분 |
| `collector-bulletin-season` | 1시간 (5~10월) | 계획서 1.1절 |
| `collector-bulletin-offseason` | 6시간 (11~4월) | 계획서 1.1절 |
| `collector-line` | 1일 | 계획서 1.1절 — 1년 창 1회 요청 |
| `collector-fishery-watch` | 주 1회 | 계획서 1.1절 — 게시 주기 추정 |
| `collector-completeness` | 주 1회 | 계획서 2.1절 |
| `evaluation-sweep` | 10분 | 계획서 2.1절 *(제안)* — water_temp 3h의 1/3 이내 |
| `interpolation-error` | 1일 | 계획서 2.1절 *(제안)* — 오늘의 오차 주기 |

**적조 시즌 주기 전환**: `axis_coverage.season_months` = `[5,6,7,8,9,10]` 기준.  
시즌 변경 시: `collector-bulletin-season` suspend=true ↔ false 교대 적용.  
**적조 수집은 동시에 하나만 돈다** — 시즌·비시즌 CronJob을 함께 켜지 않고, 손으로 띄운 Job(`kubectl create job --from=cronjob/…`)은 정기 실행과 겹치지 않게 한다. processor의 적조 직전 원문 대조가 "원문 저장소 키 순서 = 수집 순서"를 전제로 한다(계획서 3.3절 개정 18). 두 CronJob 모두 `concurrencyPolicy: Forbid`

---

## 6. 운영 조정 ConfigMap 소유·변경 절차·게이트 명령

### 소유
인계 후 인프라가 ConfigMap 값을 소유한다. 키를 추가·변경해야 하면 **이 모듈에 요청**한다 — 스키마(`contracts/config/operational.schema.json`) 버전 업 후 새 이미지 배포 필요.

### 변경 절차
1. manifest 레포에서 `api-module-operational` ConfigMap PR 작성
2. api-module 저장소에서 **운영 조정 게이트** 실행 (아래 명령)
3. 게이트 통과 확인 후 PR 반영
4. ArgoCD 동기화 → 각 이미지 롤아웃(재시작)으로 새 설정 반영

### 게이트 명령 (api-module 저장소 루트에서)
```bash
# 새 ConfigMap 파일 경로를 인수로 전달
PYTHONPATH=src/api_module python -m evaluation.main gate <path-to-new-configmap-data.yaml>

# 또는 run_gate.py로 전체 게이트 (operational.initial.yaml 기준)
python ci/gate/run_gate.py
```

### 반영 방식
값은 기동 시 1회 읽는다 — ConfigMap 변경의 반영은 롤아웃(재시작)이다.  
기동 성공 시 `ops_events`에 `OPERATIONAL_CONFIG_LOADED` + 설정 해시 기록.

### 현재 초기값 (contracts/config/operational.schema.json 스키마 버전: operational-v1)
`handoff/k8s/operational-configmap.yaml` 참고.

---

## 7. 기동 시 검사 항목

`processor`·`evaluation`·`evaluation-sweep`이 기동할 때 자동으로 수행(4번은 `grading`·`evaluation`·`evaluation-sweep`):

1. `OPERATIONAL_CONFIG_PATH` 파일 존재 확인
2. `contracts/config/operational.schema.json` 스키마 검사 (키 집합·타입·`<미결>` 거부·버전 일치)
3. 기대 DB 테이블 존재·컬럼 확인
4. **빈 해역 시드 검사** (개정 19): `grading` — `areas` 0행이면 멈춤. `evaluation`(`evaluate`·`sweep`) — `areas` 또는 `axis_coverage` 0행이면 멈춤. `gate`는 DB 없이 돌므로 제외.

실패 시: **멈추고 보고** — 기본값·초기값으로 조용히 대체하지 않는다.  
성공 시: `ops_events.OPERATIONAL_CONFIG_LOADED` + 설정 해시 기록.

---

## 7a. 추가 요청 — 해역 시드 운영 적재 (개정 19)

### 생성본 위치와 적용 방법

| 파일 | DB |
|---|---|
| `contracts/tables/seeds_pg.sql` | PostgreSQL |
| `contracts/tables/seeds_my.sql` | MySQL 8.0 |

DB 소유 측이 해당 생성본을 DB에 적용한다. 이 모듈은 운영 DB에 시드를 직접 쓰지 않는다 (계획서 12절 "운영 DB에 해역 시드를 쓰지 않는다").

### 변경 조항

시드(`seeds/*.yaml`)는 **모두의 협의 아래 파일을 고쳐 나눠 가진다** — 어느 쪽도 협의 없이 혼자 바꾸지 않는다. 파일을 고치면 api-module이 생성본을 다시 만들어 이미지와 함께 내고, DB 소유 측은 그 생성본을 DB에 적용한다. 생성본 머리의 시드 파일 해시로 같은 파일인지 확인할 수 있다.

재생성 명령 (api-module 저장소 루트에서 — api-module 쪽 작업):
```bash
PYTHONPATH=src/api_module python -c "from common.repository import generate_seed_sql_pg, generate_seed_sql_my; generate_seed_sql_pg(); generate_seed_sql_my()"
```

### 반영 순서

| 변경 종류 | 순서 |
|---|---|
| 추가·변경 | DB(시드 적용) → processor 롤아웃 |
| 삭제 | processor 롤아웃 → DB(시드 적용) |

이유: processor는 이미지 안의 별칭 파일로 속보 지점을 해역(`area_id`)에 대응시키고, grading은 DB의 `areas`에 있는 해역만 양식장에 대응시킨다(외래 키 없음). 순서를 거꾸로 하면 그 사이 별칭이 DB에 없는 해역을 가리키고, grading이 그 해역을 **조용히 건너뛴다**. 이미 적재된 대응은 재처리할 필요가 없다 — 롤아웃 뒤 다음 정기 적조 수집(30일 창)에서 새 별칭으로 덮인다. 그 전의 남은 불일치는 `seed-check` ③이 잡는다.

### seed-check 명령

서비스 시작 전과 시드 변경을 적용한 뒤 확인한다. `api-module/processor` 이미지로 돌린다(시드 파일이 들어 있다 — 수동 Job 등):
```bash
python -m processor.main seed-check        # 이미지 안 (PYTHONPATH 설정됨)
```
DB에 쓰지 않는다. 대조 항목: ① DB 세 표 = 이미지 시드 파일 ② 별칭·커버리지의 `area_id`가 `areas`에 있음 ③ 적조 현재값 유효 기간 안 속보 지점의 `area_id`가 `areas`에 있음.

필요한 환경변수: `DATABASE_URL` 만. `OPERATIONAL_CONFIG_PATH` 불필요 (startup() 없이 돈다).

종료 코드 0 = 일치, 1 = 불일치(차이 표준 출력).

### 배포 선행 조건

다음 순서를 지킨다:
1. DDL 적용 (테이블이 없으면 다음 단계 불가)
2. 시드 적용 (`seeds_pg.sql` 또는 `seeds_my.sql`)
3. `seed-check` 종료 0 확인
4. `grading`·`evaluation` 배포 — 빈 시드면 두 이미지 모두 기동하지 않는다

---

## 7b. 추가 요청 — 적조 위험도 지수 (개정 20)

### 새 테이블

| 테이블 | 역할 | 소유 이미지 |
|---|---|---|
| `risk_index_factors` | 지수 4개 인자별 기여도·제외 사유 | `grading` |
| `risk_index_levels` | 지수 단계 코드(`level`)와 경계 걸침 | `grading` |

두 테이블은 `tables-v3` DDL에 포함돼 있다 (`contracts/tables/schema_pg.sql` · `schema_my.sql`). 시드 없음, 별도 초기화 불필요.

### 기존 테이블 정의 변경 (열 변경 없음)

- **축 목록 제약(`axis` `CHECK`)에 `'red_tide_risk'` 추가** — `farm_readings`·`farm_reading_history`·`axis_status`·`axis_coverage` 4곳. 이미 만든 표는 제약을 바꿔야 한다(새 DDL을 그대로 적용하면 새 표만 생기고 기존 표의 제약은 그대로다)
- `none_reason` 새 값 `INSUFFICIENT_FACTORS`·`RULE_UNDECIDED` — 이 열에는 `CHECK`가 없어 DB 변경 없음
- 결과 테이블 계약 `tables-v2` → **`tables-v3`**

### 적용 순서

1. DB에 새 표 2개 생성 + 기존 표 4곳 `CHECK` 변경
2. 새 이미지 배포 — 기동 시 테이블 검사가 새 표를 요구한다(없으면 `processor`·`interpolation`·`grading`·`evaluation`이 기동하지 않는다). 제약을 바꾸기 전에 배포하면 지수 행 적재가 `CHECK` 위반으로 실패한다

### 파생 축 `red_tide_risk`

- `farm_readings.axis = 'red_tide_risk'`로 적재된다 — 기존 결과 테이블 확장
- `derivation = COMPUTED`, `alertable = false` (불변식)
- `provenance`: 산출 가능 상태 = `INTERPOLATED`, 신뢰 기준 밖 = `NONE` (가중치·규칙 미결 → `RULE_UNDECIDED`, 유효 인자 부족 → `INSUFFICIENT_FACTORS`)
- `axis_status.state`: `NORMAL` · `NOT_USABLE`(사유=`none_reason`) · `GRADING_STALE`(sweep 판정) — 커버리지·계절·신선도 상태 없음

### 판정 정의 미결 항목

`config/definitions.yaml`의 `risk_index.*` 키 10개가 현재 전부 `<미결>`이다 (계획서 4.10절 확정 후 개정).  
미결 상태에서도 `grading`은 정상 기동하고 `red_tide_risk`를 `NONE/RULE_UNDECIDED`로 적재한다.  
**값이 확정되면 `config/definitions.yaml`과 `ci/gate/expected.yaml`을 함께 갱신하고 이미지를 새로 배포한다.**

### 기동 시 검사 (K9)

`grading` 이미지 기동 시: `risk_index` 키 중 값이 있는 것만 검사 (가중치 합산 = 1, 점수 범위 [0,1], 단계 첫 min ≤ 0).  
미결 키는 검사에서 건너뛴다 — `<미결>` 상태의 기동을 막지 않는다.

---

## 8. 운영 지표 목록

`handoff/observability/metrics.yaml` 참고.  
지표는 `common/metrics/` 공용 계층에서 계측한다. 운영 탭(v1.5 1.3.3절 ①층)용이며 대시보드 결과 테이블과 다르다.

---

## 9. 이미지 목록과 이미지 알림 형식

### 이미지 목록

| 이미지 이름 | 레지스트리 경로 | Dockerfile |
|---|---|---|
| collector | `${REGISTRY}/api-module/collector` | `docker/collector/Dockerfile` |
| processor | `${REGISTRY}/api-module/processor` | `docker/processor/Dockerfile` |
| interpolation | `${REGISTRY}/api-module/interpolation` | `docker/interpolation/Dockerfile` |
| grading | `${REGISTRY}/api-module/grading` | `docker/grading/Dockerfile` |
| evaluation | `${REGISTRY}/api-module/evaluation` | `docker/evaluation/Dockerfile` |

`${REGISTRY}`: CI 변수 `REGISTRY` 하나로 관리 (현재 GitLab Container Registry, ECR 전환 시 변수만 교체).

### 이미지 알림 형식 (`contracts/release/image_notice.json`)

```json
{
  "image": "api-module/interpolation",
  "tag": "1.3.0",
  "digest": "sha256:…",
  "git_sha": "59e263a",
  "built_at_utc": "2026-09-30T00:00:00",
  "contracts_version": "tables-v2 / queue-v1 / operational-v1"
}
```

`contracts_version`으로 단계 간 계약 버전 불일치를 manifest 레포·인프라가 확인한다.

### 선택 빌드 (계획서 2.0.5절)

바뀐 경로에 해당하는 이미지만 빌드. `common/`이 바뀌면 5종 전부.  
경로 → 이미지 대응: `.gitlab-ci.yml` `rules: changes` 참고.

---

## 10. 미결 — 인계 후 결정 필요 항목

| 항목 | 처리 | 결정처 |
|---|---|---|
| `DTRECENT_KEY` 확인 | 포털에서 발급받은 원문(미리 URL 인코딩하지 않은 값)을 설정 확인 | 운영자 |
| DB 제품 확정 (PostgreSQL / MySQL) | 양쪽 DDL 존재, 확정 후 7.4절 선택 검사 | 팀 |
| 큐 구현 (NATS / SQS) | `common/queue/` 인터페이스 — 구현체 교체만 | v1.5 10.3(b) |
| 객체 저장소 위치 | `common/raw_store/` 인터페이스 | v1.5 12.1절 |
| `dissolved_oxygen` stale_threshold_hours | 현재 1224h (51일) 임시값 — 다년도 집계 후 재결정 | 팀 |
| 판정 정의 남은 미결 | 2026-09-30 채택 8종(`bulletin.current_window_days` 등)은 계획서 개정 11(2026-10-01)에 값으로 기록 — 해소. 남은 것: R1 하구 예외 정점 목록, R4 태풍 특보 자동 입력 원천(현재 운영 조정 `typhoon_active` 수동 토글), `interpolation.method` `B2` 승격 | 팀·v1.5 20절 |
| F11·F12·P9 수동 재실행 | `tests/replay/`·`tests/pipeline/` 구현·통과(2026-10-01, `IDW_OUTPUT_DIR` 설정 시). 릴리스 전 재실행 결과를 `docs/reports/`에 기록(계획서 7.1절) | 릴리스 전 |
| 이미지 알림 수신 방식 | 파이프라인 트리거 / 웹훅 — manifest 레포 설정 | 인프라 |
| 레지스트리 ECR 전환 | `REGISTRY` 변수·인증 단계만 교체 | 팀 |

## 추가 요청 — 운영 DB 테이블 `completeness_checks` (계획서 개정 17)

- 분할 합산 결과의 **운영 기록** 테이블(결과 테이블 계약 밖). 정의는 `contracts/tables/schema_pg.sql`·`schema_my.sql`(생성본), 의미는 계획서 3.3·5.3절
- **processor 이미지**(검사기 포함)가 기동 시 테이블 검사에서 이 표를 요구한다 — **DB 소유 측이 표를 먼저 만든 뒤** 새 processor 이미지를 배포한다. 개정 12~15의 정의 변경(아래)은 모든 이미지의 기동 검사에 걸리므로 DB 적용 → 모든 이미지 순서
- 함께 바뀐 정의: `survey_observations`(조사 시각 키, `flags`), `adapter_health.retry_recovered`(정수), `farm_areas`(신설) — 개정 12~15

## 추가 요청 — 워크로드 `completeness-check` (계획서 개정 17)

| 항목 | 값 |
|---|---|
| 이미지 | `api-module/processor` |
| 명령 | `["python", "-m", "processor.main", "completeness-check"]` |
| 형태 | Deployment, **1대, KEDA 대상 아님** — `completeness.collected` 컨슈머 |
| 환경 | processor와 같다 — `DATABASE_URL`, `OPERATIONAL_CONFIG_PATH`(기동 시 검사), 원문 저장소 읽기 권한 |
| 이유 | 분할 합산 판정을 원문 하나 처리(processor·KEDA)에서 떼어, 수집 완료 알림 뒤 한 번에 판정한다(계획서 3.3절) |
| 배포 전략 | `Recreate` 권장 — 두 대가 겹치면 결과 행은 같지만 운영 이벤트가 중복될 수 있다 |
| 큐 | 주제 `completeness.collected` 생성·구독 — 큐 구현은 미결(계획서 11절). **검사기를 먼저 배포한 뒤** 새 collector를 배포한다 |

- 이 저장소는 매니페스트를 고쳐 배포하지 않는다 — 위 사양으로 인프라가 추가한다
- `handoff/k8s/collector-completeness.yaml`의 설명 주석은 개정 17·18 설계로 갱신했다(인계 전, 2026-10-02) — 명령은 그대로다


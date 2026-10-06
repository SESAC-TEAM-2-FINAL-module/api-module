# I-17 시험 실행기 flowtest — 결과 보고서

> **5절(검수·수정, 2026-10-06 이 세션)이 1~4절보다 우선한다.** 1~4절은 피어 세션의 구현 보고(2차)다. FT7 1회차 결과(수온 추정 0건)는 5절에서 결함으로 판정·수정했다.

작업일: 2026-10-06  
지시서: `docs/instructions/I-17_시험실행기_flowtest.md`  
참조 skill: `common-core`  
기준 pytest: **656 passed · 14 skipped** (검수 후)

---

## 1. 실행 결과

### 검수 반영 수정 목록

| 항목 | 파일 | 내용 |
|---|---|---|
| M1 | `evaluation/main.py` | `startup_checks(repo)` 추출, `_repository()` 가 호출 |
| M1 | `processor/main.py` | `schema_checks(repo)` 추출, `startup()` 가 호출 |
| L2 | `grading/main.py` | `startup_checks(repo, defs=None) → dict` — 원래 순서 복원, defs 내부 로드·반환 |
| H5 | `flowtest/main.py` | `_wrap`, `_do_collect`, `_run_loop` 예외 로그 — `type(exc).__name__` 만 기록 |
| H2 | `flowtest/main.py` | 모든 주기 인수 기본값 제거, `_validate_loop_intervals` 추가 (loop 모드만) |
| H3 | `flowtest/main.py` | `_bulletin_interval(args)` 추가 — KST 5-10월 시즌, 나머지 시즌 밖 |
| L1 | `flowtest/main.py` | `_do_replay` 의 `"queue-v1"` → `QUEUE_CONTRACT` 상수 |
| M1 | `flowtest/main.py` | `_preflight` 가 `pm.schema_checks`, `ev.startup_checks` 를 호출 (복제 제거) |
| FT1 | `flowtest/main.py` | `_bind_handler` 추가, `_wrap` 이 `_stage_fn` 전파, `_setup_pipeline` 이 `_bind_handler` 사용 |
| M2 | `flowtest/main.py` | `_print_summary` 가 13개 결과·인덱스 테이블 행 수 출력 |
| FT7 | `flowtest/main.py` | `_do_collect` + `_run_loop` 에 `cm._load_adapters()` 추가 |
| L3 | `tests/` | DB 없는 FT1·FT6 → `tests/unit/test_flowtest_unit.py`, DB 테스트 FT2-FT5 → `tests/db/test_flowtest.py` |
| M3 | `handoff/flowtest/README.md` | DB 준비 순서, 하루 호출 수, 알려진 제약, 이미지 주소 플레이스홀더, 내부 절 번호 제거 |
| FT1③ | `processor/main.py` | 주석의 `flowtest` 문자열 제거 |

---

## 2. 통과 기준 결과

### FT1~FT7 + 추출·이미지

| 기준 | 결과 | 비고 |
|---|---|---|
| **FT1 ①** `_stage_fn is` 단계 함수 | ✅ 5개 테스트 통과 | `_bind_handler` + `_wrap` 전파 |
| **FT1 ②** 기동 검사 호출 집합 일치 | ✅ 5개 테스트 통과 | M1 추출 + preflight 소스 확인 |
| **FT1 ③** 단계 코드에 flowtest 미포함 | ✅ 통과 | AST/grep, processor 주석 수정 포함 |
| **FT2** 실제 DB + fake HTTP 전 파이프라인 | ✅ 2개 테스트 통과 | water_temp COMPUTED·alertable=False, 구독 제거 시 실패 |
| **FT3** 실행 전 점검 6가지 실패 조건 | ✅ 7개 테스트 통과 | 각 조건 SystemExit, 구별 포함 |
| **FT4** replay — HTTP 0, 동일 값 | ✅ 2개 테스트 통과 | 동일 raw_key 재발행, HTTP 호출 0 |
| **FT5** 예외 체인 — 나머지 완료 | ✅ 2개 테스트 통과 | interpolation 예외 → grading 완료, 요약 실패 수 포함 |
| **FT6** 비밀 유출 없음 (H5 포함) | ✅ 3개 테스트 통과 | _wrap·_do_collect 예외 경로, httpx 예외 경로 |
| **FT7** 실제 API 호출 | ✅ **실행 성공** | 아래 상세 |
| **추출** 기동 시 검사·seed_check | ✅ | evaluation·processor·grading·interpolation 4곳 추출 |
| **이미지** 빌드 | ✅ 빌드 성공 | `docker/flowtest/Dockerfile` |
| **전체 pytest** | ✅ **656 passed · 14 skipped** | 회귀 없음, +32개 신규 |
| **키 스캔** | ✅ 0건 | `ci/scan_keys.py` |

### FT7 상세 — 2026-10-06

| 항목 | 값 |
|---|---|
| 실행 모드 | `--mode collect --run once` |
| DB | testcontainer PostgreSQL 16 |
| 총 API 호출 수 | **12회** |
| dtRecent | 9회 (예산 ≤ 40) |
| redtideList | 1회 (예산 ≤ 5) |
| sooList | 1회 (예산 ≤ 10) |
| femoSeaList | 1회 (예산 ≤ 15) |
| 단계 실패 수 | 0 |
| raw_index | 12행 |
| ingest_runs | 12행 |
| farm_readings | 8행 |
| farm_reading_history | 96행 |
| farm_areas | 1행 |
| axis_status | 9행 |
| bulletins | 10행 |
| bulletin_details | 10행 |
| interpolation_runs | 0행 (obs.loaded 페이로드 불완전 — load_id 부재, 기존 WARNING) |
| 소요 시간 | 약 48초 |

**replay 검증**: 같은 raw_key 재발행 시 `value`·`provenance` 동일, HTTP 호출 0회 — FT4 테스트로 확인.

**URL 마스킹**: raw 원문 내 `serviceKey` / `key` 파라미터가 `***` 로 치환됨 — `common.http._client` 의 `_mask_key` 기능. 저장 원문 건수 = 12건.

---

## 3. 변경 파일 목록

```
수정
  src/api_module/evaluation/main.py    — startup_checks() 추출, _repository() 갱신
  src/api_module/processor/main.py     — schema_checks() 추출, startup() 갱신, 주석 수정
  src/api_module/grading/main.py       — startup_checks() 원래 순서 복원·defs 반환
  src/api_module/flowtest/main.py      — H2·H3·H5·L1·M1·M2·FT1 전면 반영
  handoff/flowtest/README.md           — M3 반영 (DB 순서, 호출 수, 제약, 플레이스홀더)
  tests/db/test_flowtest.py            — FT2·FT3·FT4·FT5 재작성

신규
  tests/unit/test_flowtest_unit.py     — FT1·FT6·H2·H3 단위 테스트
```

---

## 4. 계획서 반영 후보 (*(제안)* 구현)

해당 없음.

---

## 5. 만난 `<미결>` 항목

| 항목 | 영향 |
|---|---|
| `risk_index.*` 미결 항목 다수 | 게이트 경고로 통과 — flowtest 동작에 영향 없음 |

---

## 6. 비고

- `obs.loaded 페이로드 불완전 — load_id 없음` 경고는 기존 동작이다. tide 어댑터가 관측소별로 원문을 각각 발행하고 processor가 관측소 단위 obs.loaded를 내는데, 일부 페이로드에 `load_id` / `observed_to_utc` 가 없어 interpolation이 건너뛴다. 이 모듈의 변경 전후 동일하며 flowtest 코드와 무관하다.
- C2(조위 다중 페이지 재구성)는 수정하지 않았다.
- 단계 코드는 flowtest를 import하지 않는다 (FT1 ③ 통과).
- 이미지 주소(`<이미지 주소>`)는 인계 후 인프라가 채운다 (`handoff/flowtest/README.md`).


---

## 5. 검수·수정 (2026-10-06, 설계 세션 — 사용자 지시로 수정까지 직접)

### 5.1 실제 호출에서 드러난 결함 3건 (단계 코드 — 계획서 범위 안의 결함 수정)

FT7 1회차는 결과 테이블에 행이 생겼지만 **수온 추정 0건**(`interpolation_runs` 0), 인근 실측 축 전부 `NO_INPUT`이었다. 보관 원문 12건을 새 테스트 DB에 재생(호출 없음)해 원인을 찾았다.

| # | 결함 | 위치 | 원인 | 수정 | 근거 |
|---|---|---|---|---|---|
| R1 | 실제 `dtRecent` 응답을 `PARSE_FAILURE`로 판정(`resultCode 00`, `totalCount 651`인데 항목 0) | `common/classifier/_parser.py` 최상위 `header`+`body` 계열 | 이 계열에서 `body.item`만 읽음 — 실제 응답은 `body.items.item` | `body.item`이 없으면 `body.items.item` | 계획서 3.2절 표 "헤더 최상위 — `body.item` / `body.items.item`" |
| R2 | 관측 행 0, 관측소 마스터 0 | `processor/adapters/tide/_adapter.py` `interpret`·`stations` | 실제 응답 항목에 관측소 코드(`obsCode`)가 **없다** — 관측소당 한 번 호출하므로 요청 파라미터에만 있다. 코드는 항목의 코드만 보고 전부 건너뜀 | 항목에 코드가 없으면 그 원문의 요청 파라미터 `obsCode`. `stations(pr, raw_meta=None)`로 메타를 받고 `_load`가 넘긴다(line·fishery는 인자만 추가, 동작 불변). 이름은 `obsvtrNm`도 읽음 | 5.3절 `stations.id` = `tide:` + 관측소 코드 |
| R3 | DO 값이 있는데 `axis_status`가 `NOT_USABLE`(입력 없음)에 고정. sweep의 신선도 초과도 기존 `NORMAL`을 못 덮음 | `evaluation/_state.py` `determine_state` | `STALE`만 `basis_utc`로 **관측 시각**(적조는 마지막 성공 시각)을 쓰고 나머지 상태는 산출 시각 — 시계가 달라 STALE이 늘 "오래된 판정"으로 버려짐 | `STALE`의 `basis_utc`도 같은 입력 행의 `computed_at_utc` | 4.9절 쓰기 규칙 "같은 입력에 대한 sweep의 신선도 초과 판정은 기록된다"(P12) |

- **연쇄 효과**: collector도 같은 해석기로 다음 페이지를 정한다. R1 전에는 항목 0으로 읽혀 **첫 페이지에서 멈췄다**(1회차 원문 300/651건 `INCOMPLETE`). R1 뒤에는 관측소당 약 3페이지를 받아 **C2 합치기 경로를 실제로 탄다**(합친 원문도 첫 페이지의 요청 파라미터를 유지 — R2 수정이 그대로 동작). 반복 실행 시 조위 호출은 하루 약 3,900회(8절 "약 1,300"은 페이지를 넣지 않은 값)
- **테스트가 못 잡은 이유**: 합성 조위 원문(`tests/db/conftest.py` `tide_body`)이 `response` 래퍼 + 항목에 `obsCode`가 있는 형태 — 실제 응답과 다르다. 실수집 원문을 픽스처로 넣었다: `fixtures/raw/dtRecent_i17_DT_0014_1791252000000.json`(`MANIFEST.csv` 해시 등록, `scan_keys` 0건)

### 5.2 FT7 2회차 (머리말 허용 — 최대 2회 중 2회째, collector 호출 방식이 바뀌었으므로)

테스트 컨테이너 PostgreSQL 16, `collect`·`once`, 합성 양식장 1곳.

| 항목 | 값 |
|---|---|
| 호출 수 (예산) | `dtRecent` **27** (40) · `redtideList` **1** (5) · `sooList` **1** (10) · `femoSeaList` **1** (15) — 합 30 |
| 원문 마스킹 | 12건 모두 `serviceKey`·`key` = `***` |
| 조위 적재 | 9개소 모두 `OK` 683/683, `observations` 36,882행, `stations` 182 |
| 수온 추정 | `interp.done` 8, `interpolation_runs` 8 (첫 관측소 1개만 적재된 시점의 1건은 "사용 가능한 관측소 없음" — 순서상 정상) |
| 단계 실패 | 0 |

양식장 축별 결과:

| 축 | derivation · provenance | 값 | 상태 |
|---|---|---|---|
| 수온 | COMPUTED · NEAREST | 23.93 | NORMAL (alertable = false) |
| 기온 / 조위 / 풍속 | MEASURED · NEAREST | 18.9 / 133.0 / 3.2 | NORMAL |
| 염분 | MEASURED · NONE(`EXCLUDED_ZONE` — 하구 영향 `DT_0016`) | 31.6 (저장됨) | NOT_USABLE |
| DO | SURVEY · BASELINE | 5.32 (2025-11 조사) | STALE (임계 1224h) |
| 클로로필 | SURVEY · NONE(`NO_INPUT`) | — | NOT_USABLE (올해 게시 0건 `OK_EMPTY`) |
| 적조 | OFFICIAL | — | NORMAL_SILENCE |
| 적조 위험도 지수 | COMPUTED · NONE(`RULE_UNDECIDED`) | — | NOT_USABLE |

재생 확인: 1회차 원문 12건을 새 DB에 `replay` → HTTP 0, 수정 뒤 같은 축 결과(수온 23.78 NORMAL 등). 2회차 원문은 설계 세션 스크래치 폴더에 보관(저장소 밖).

### 5.3 테스트 보강

| 기준 | 내용 | 판별력 |
|---|---|---|
| FT1 ② | 소스 문자열 검사 → **스파이**: 각 단계 진입점(processor `startup`, interpolation·grading `main`, evaluation `_repository`)이 실제로 부른 기동 시 검사 집합 ⊆ 실행기 `_preflight`가 부른 집합, 차이는 `seed_check`뿐 | 실행기에서 `ev.startup_checks` 한 줄을 빼면 실패 확인 |
| FT3 | 점검 함수 단위 mock → **진입점** `flowtest.main.main(collect, once)`를 6경우(표 없음·시드 빔·운영 조정 없음·`farm_sites` 없음·활성 0·키 변수 없음)로 — 경우마다 **자기 점검의 메시지로** 멈춤, 모든 모듈 표 행 수 불변(`ops_events` 포함), HTTP 송신 0 | 깨뜨리지 않은 상태에서는 점검 통과 + `ops_events` 기록(행 없음이 우연이 아님) |
| FT4 | 같은 DB 재처리 → 모듈 표를 비운 DB에 `_do_replay`(키 접두 경로), 단계 시각 함수 고정, 관측 행·축별 `value`·`provenance`·`state` 동일, HTTP 0 | 재생 쪽 `grade.done` 구독을 빼면 실패 확인 |
| R1·R2 | 단위: `body.items.item` 해석, 요청 파라미터 `obsCode`, 항목 코드 우선, 실수집 픽스처 300항목 → 1,800행, `stations`. DB: 실수집 픽스처를 processor로 → 관측소 1·관측 1,800·`obs.loaded` 시각 | `_load`의 메타 전달을 되돌리면 DB 검사 실패 확인 |
| R3 | 같은 입력의 NORMAL 뒤 STALE이 기록됨, 먼저 쓰인 NOT_USABLE을 뒤의 STALE이 덮음 | 수정 전 식(관측 시각)으로는 첫 검사가 성립하지 않음 |

### 5.4 사용 안내 재작성 (`handoff/flowtest/README.md`)

받는 사람(대시보드·인프라) 기준으로 다시 썼다 — DB 준비 순서(DDL·시드 SQL·`farm_sites`), 환경변수 이름, 한 번/반복/재생 실행 명령, 호출량(조위 하루 약 3,900), 종료 요약 읽기, 멈춤 메시지별 확인, 알려진 한계. 내부 쟁점 번호·코드 이름·저장소 경로를 뺐다. 이전 판의 예시 요약은 결함 상태(수온 0)였다.

### 5.5 판정표 (최종)

| 기준 | 결과 |
|---|---|
| FT1 ①②③ | 통과 |
| FT2 | 통과 (합성 원문 — 실제 형태는 R1·R2 검사와 FT7이 본다) |
| FT3 | 통과 (6경우 + 판별력) |
| FT4 | 통과 (+ 판별력) |
| FT5 | 통과 |
| FT6 | 통과 (예외 메시지 미기록·httpx 경로) |
| FT7 | **통과** — 2회차(5.2) |
| 추출 | 통과 — processor `schema_checks`·`seed_check`, interpolation·grading·evaluation `startup_checks`. `main()`·`startup()`·`_repository()` 동작 동일, 7.4·E1~E7·K9·SD1~SD4 회귀 없음 |
| 이미지 | 통과 — 빌드, 컨테이너 import, DB 없음 → 종료 코드 1, 이미지 안 `operational*.yaml`·`.env` 없음 (609MB) |
| 회귀 | 전체 `pytest` **660 passed · 14 skipped**, 게이트 통과, `scan_keys` 0건 |

### 5.6 계획서 반영 후보 (제안만)

- 1.2절: 실제 `dtRecent` 응답은 최상위 `header`+`body`, 항목은 `body.items.item`, **항목에 관측소 코드 없음** — 관측소는 요청 파라미터 `obsCode`로 정한다
- 8절: 조위 호출량에 페이지 반영 — 관측소당 약 3페이지(`numOfRows` 300, 최근 약 680건), 하루 약 3,900회
- 4.9절: `basis_utc`는 상태와 무관하게 "판정에 쓴 입력 행(`farm_readings`)의 산출 시각"임을 명시(R3)
- 7.1·7.9절: 합성 조위 원문이 실제 형태와 다르다 — 실수집 픽스처를 재생 검사에 쓰도록
- C2(조위 여러 페이지 합치기)가 이제 실제로 타는 경로다 — 개정 22에서 처리할 때 우선순위를 높일 것
- 새 인자·환경변수: `--mode`·`--run`·`--replay-api`·`--replay-date`, `FT_*_INTERVAL_SEC` 7개

### 5.7 변경 파일 (이 세션 추가분)

`common/classifier/_parser.py`, `processor/adapters/tide/_adapter.py`, `processor/adapters/line/_adapter.py`·`fishery/_adapter.py`(인자만), `processor/_load.py`, `evaluation/_state.py`, `handoff/flowtest/README.md`, `fixtures/raw/dtRecent_i17_DT_0014_1791252000000.json`, `fixtures/MANIFEST.csv`, `tests/unit/test_tide_processor.py`·`test_evaluation.py`·`test_flowtest_unit.py`, `tests/db/test_flowtest.py`·`test_processor_load.py`

### 5.8 시험용 매니페스트 추가 (개정 21 보완, 2026-10-06 사용자 결정)

공유 DB가 클러스터 안이면 `docker run`으로는 닿지 않으므로 실행 방법을 하나 더 준다. `handoff/flowtest/k8s/`:
`secret-template.yaml`(전용 `flowtest-secrets`, 키 이름만 — 운영 Secret은 `RAW_STORE_DSN`·`QUEUE_DSN` 때문에 쓰지 않음) · `configmap-operational.yaml`(`operational.initial.yaml`과 같은 값 — 스키마 검사 통과 확인) · `job-once.yaml`(Job, `backoffLimit: 0`) · `deployment-loop.yaml`(Deployment 1대 `Recreate`, 주기 7개 권장값). CronJob으로 `once`를 주기 실행하지 않는다(원천별 주기가 무너진다). 검증은 오프라인(YAML 구조·ConfigMap 스키마) — `kubectl --dry-run`은 로컬에 설정된 클러스터에 접속하려 해서 쓰지 않았다(접속은 되지 않음). README 3절 추가.

제안 커밋 메시지: `feat(I-17): 시험 실행기 flowtest·이미지·사용 안내, 실수집으로 드러난 조위 해석·관측소 코드·STALE basis 결함 수정`

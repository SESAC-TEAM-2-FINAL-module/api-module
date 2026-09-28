---
name: evaluation
description: "침묵 판정과 결과 테이블 계약 — src/api_module/evaluation/(evaluate 컨슈머, sweep, gate 명령)과 contracts/tables/의 결과 테이블 의미 계약을 만들거나 고칠 때 쓴다 (지시서 I-9, gate는 I-10). grade.done을 받아 양식장 × 축의 axis_status(침묵 분류·사유)를 쓰고 result.updated를 발행, 주기 sweep으로 신선도·추정 지연·산출 지연 판정, basis_utc 쓰기 규칙, 게시 대기, 적조 신선도(마지막 성공 호출 기준), 운영 조정 판정 재생 게이트, 대시보드 계약 W1~W8 배포. farm_readings 산출(grading), adapter_health 기록(common-core), 배지·문구(대시보드) 작업에는 쓰지 않는다."
---

# evaluation

양식장 × 축마다 **"지금 이 값이 어떤 상태인가"**를 하나로 정해 `axis_status`에 쓴다. 조용한 것이 정상인지(정상적 침묵·게시 대기) 장애인지(확인 불가·타임아웃·파싱 실패) 구분하는 것이 이 서비스의 핵심 주장이다. 또 대시보드가 결과 테이블을 어떻게 읽어야 하는지(5.5절 계약)를 배포한다. 공용 용어는 `CLAUDE.md` 6절에 있다. 괄호 속 "N절"은 계획서의 절이다.

---

## ① 범위

| 이미지 | 워크로드 | 실행 | 계기 | 하는 일 |
| --- | --- | --- | --- | --- |
| `evaluation` | `evaluation` | Deployment, 큐 컨슈머 | `grade.done` | 침묵 분류 종합 → **결과 테이블** → `result.updated` |
| | `evaluation-sweep` | CronJob, 10분 | 시각 | **침묵 점검만** — 신선도·단계 지연을 판정해 `axis_status` 갱신. 앞 단계 처리는 하지 않는다 |

| 경로 | 이 skill이 만드는 것 |
| --- | --- |
| `evaluation/main.py` | 세 명령 — `evaluate`(큐 컨슈머), `sweep`(CronJob), `gate`(운영 조정 게이트, 2.0.6절) |
| `evaluation/` | 침묵 판정, `axis_status` 쓰기 규칙, 신선도 임계 적용, `result.updated` 발행 |
| `contracts/tables/` 결과 테이블 **의미 계약** | 5.5절(필드 의미 + W1~W8)을 같은 내용으로 배포한다. DDL 생성본은 `repository` 몫 |
| `fixtures/synthetic/` 게이트 픽스처 | 7.3b·P3·P6·P10·P15의 합성 입력 — 임계에 **상대적인** 시각으로 짠다. 이 이미지에 포함된다 |

**만들지 않는 것**

- `farm_readings` 값·등급·`none_reason` → `grading`. 이 skill은 읽어서 `axis_status.reason`으로 옮긴다
- `adapter_health`·`ingest_runs` 기록 → `common-core`(`processor`). 이 skill은 읽는다
- `publication_checks` 기록 → `fishery`. 이 skill은 읽어 **게시 대기**를 판정한다
- 운영 조정 **스키마 검사·기동 시 검사** → `common-core`. 이 skill의 `gate`는 그 위에 **판정 재생**을 더한다
- 배지·화면 문구·노출·발송 시점·"확인 불가" 한계값 → 대시보드(5.5절)
- sweep이 앞 단계를 대신 돌리는 것 — **sweep은 판정만** 한다(2.2절)

---

## ② 원천 절 (계획서)

2.0.6(운영 조정 게이트·키 구분) · 2.1(`evaluation`·`evaluation-sweep`) · 2.2(`grade.done`·`result.updated`) · 3.2(상태 이름·분류) · **4.9** · 5.3(결과 테이블) · **5.5** · 7.3 · 7.5 · 7.6(B7) · 9절

---

## ③ 사실

### ③-1 침묵 판정 (4.9절 전문)

양식장 × 축마다 **지금 이 값이 어떤 상태인지** 하나로 정해 결과 테이블에 쓴다. 규칙은 v1.5 4.5절 10분류 + v1.4 추가 3종 + 이 문서가 더한 셋(값 멈춤 — 확인 중 · 추정 지연 · 산출 지연)이다.

| 입력 | 쓰는 곳 |
| --- | --- |
| `adapter_health`, `ingest_runs` 상태 | 장애 / 요청 오류 / 파싱 실패 / 타임아웃 |
| 관측 신선도 (아래 신선도 임계표) | 정상 / 정상적 침묵 / 확인 불가 |
| 커버리지·계절 선언 (`axis_coverage`, 5.3절) | 커버리지 밖 / 계절 밖 |
| `publication_checks` | **게시 대기** |
| `STALE_SUSPECT` 플래그 | **값 멈춤 — 확인 중** |
| `interpolation_runs` 최신 시각 | **추정 지연** |
| `ingest_runs.processed_at_utc` 대비 `farm_readings.computed_at_utc` | **산출 지연** (`grading` 정지) |
| `farm_readings.none_reason` | 산출 불가·영역 `NONE` 사유 → `axis_status.reason`. 이 단계 자신의 판정 사유(추정 지연 등)가 있으면 그쪽이 우선 |

- **`adapter_health` 갱신 규칙** (v1.5 4.5절 "헬스체크" 열) — `processor`가 원문 해석 결과로 기록한다
  - **성공** — `OK`·`OK_EMPTY`·`NO_DATA`: `last_success_utc` 갱신, `consecutive_failures` 초기화
  - **실패** — `HTTP_ERROR`·`NET_ERROR`(진짜 장애): `last_failure_utc` 갱신, `consecutive_failures` 증가
  - **별도** — `TIMEOUT_05`: 재시도로 복구되면 `retry_recovered`만 올리고 실패로 세지 않는다. 재시도 후에도 `05`면 실패와 같게 센다 *(제안)*
  - **어느 쪽도 아님** — `SUSPENDED`(무관), `PARSE_FAILURE`(검토 큐), `BAD_REQUEST`(우리 버그): 성공 시각을 갱신하지 않는다. v1.5 4.5절에 없는 `NO_SERVICE`·`KEY_ERROR`·`QUOTA`·`INCOMPLETE`·`FILTER_IGNORED`도 같게 둔다 *(제안)*. 그래서 파싱 실패가 이어지면 적조 축은 신선도 임계를 넘어 `STALE`이 된다 — 조용히 정상으로 남지 않는다
- **두 경로로 돈다.** `grade.done`을 받으면 해당 양식장·축을 판정하고, `evaluation-sweep`은 주기마다 **모든 양식장·축의 신선도와 단계 지연**만 다시 본다. sweep은 값을 새로 만들지 않는다
- **추정 지연**: 수온 추정이 `evaluation.interpolation_stale_minutes`를 넘으면 수온 축은 `INTERPOLATION_STALE`. **최근접 관측값으로 대체하지 않는다** — v1.5 6.3절. 이 판정은 sweep이 한다 — 추정이 멈추면 `grade.done`도 오지 않기 때문이다
- **산출 지연**: 어느 축이든 새 관측이 적재됐는데(`ingest_runs.processed_at_utc`) 그 뒤 해당 축의 `farm_readings`가 `evaluation.grading_stale_minutes` 안에 갱신되지 않으면 그 축은 `GRADING_STALE`. 저빈도 축도 같은 규칙으로 잡힌다 — 기준이 "적재 이후 미갱신"이라 축별 주기와 무관하다. v1.5 14.3절 실험 8의 대상. 이 판정도 sweep이 한다
- **`axis_status` 쓰기 규칙**: `evaluation`과 `evaluation-sweep`이 같은 행을 쓴다. 판정마다 **판정 근거 시각**(`basis_utc` — 판정에 쓴 가장 새로운 입력의 시각)을 함께 쓴다. 기존 행보다 `basis_utc`가 **새로우면** 덮어쓰고, **같으면 `last_checked_utc`가 나중인 판정**이 덮어쓴다. `basis_utc`가 오래된 판정은 쓰지 않는다 — 늦게 도착한 옛 판정이 새 판정을 덮지 못하고, 같은 입력에 대한 sweep의 신선도 초과 판정은 기록된다(7.5절 P12)
- **`evaluation` 정지**: 이 모듈 안에서 판정할 단계가 없다. `axis_status.last_checked_utc`가 멈춘 것으로 드러나며, 이를 "확인 불가"로 볼 한계와 문구는 대시보드가 정한다(5.5절 W3)

**상태 값** — `axis_status.state`에 쓰는 값. 분류마다 상수 하나이고, 사유는 `reason`에 둔다. `provenance`의 `NONE`을 상태 자리에 쓰지 않는다. 응답 상태(3.2절)는 호출 한 번의 결과이고, 이것은 **축의 상태**다

| 분류 | `state` | 어디서 오는가 |
| --- | --- | --- |
| 정상 | `NORMAL` | 신선도 임계 안의 최신 값 |
| 정상적 침묵 | `NORMAL_SILENCE` | `OK_EMPTY`, 적조 속보 없음(호출은 성공) |
| 게시 대기 | `PUBLICATION_PENDING` | 게시 감시 0건 |
| 조건 불일치 | `NO_MATCH` | `NO_DATA`(`03`) |
| 관측 항목 일시 중단 | `ITEM_SUSPENDED` | `SUSPENDED`(`41`) |
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

**상태가 겹칠 때의 우선순위** — 위에서 먼저 맞는 것을 쓴다

| 순위 | 묶음 | `state` |
| --- | --- | --- |
| 1 | 원래 없는 곳 | `OUT_OF_COVERAGE` |
| 2 | 원래 없는 때 | `OUT_OF_SEASON` |
| 3 | 원천·호출 문제 | `OUTAGE`·`SERVER_TIMEOUT`·`PARSE_FAILURE`·`REQUEST_ERROR`·`FILTER_IGNORED`·`ITEM_SUSPENDED`·`NO_MATCH` |
| 4 | 모듈 단계 정지 | `GRADING_STALE` → `INTERPOLATION_STALE` |
| 5 | 값 판정 | `NOT_USABLE` |
| 6 | 원인 미상 오래됨 | `STALE` |
| 7 | 의심 | `VALUE_FROZEN` |
| 8 | 정상인 조용함 | `PUBLICATION_PENDING` → `NORMAL_SILENCE` |
| 9 | 정상 | `NORMAL` |

- **예상된 부재가 먼저**(1·2) — 원래 없는 곳·때의 호출 실패는 사용자에게 의미가 없다. 운영자는 `adapter_health`와 지표로 그대로 본다
- **증상보다 원인**(3 → 6) — "오래됨"은 대개 호출 실패의 결과다
- 3번 묶음 안은 순서가 필요 없다 — 한 호출의 결과는 하나라 서로 겹치지 않는다. 4번은 `grading`이 멈추면 수온까지 멈추므로 산출 지연이 먼저다

**신선도 임계** — 값이 정해지지 않은 것은 `<미결>`이다. 판정 정의는 CI 게이트(7.7절 ①)에, 운영 조정은 `operational.initial.yaml`과 스키마(2.0.6절)에 등록한다. **운영 조정의 `<미결>`은 인계 전에 모두 정해져야 한다** — 스키마가 자리 표시를 거부하므로 ConfigMap으로 기동할 수 없다

| 판정 대상 | 설정 키 | 구분 (2.0.6절) | 값 | 근거·상태 |
| --- | --- | --- | --- | --- |
| 수온 관측 (`dtRecent`) | `stale_threshold_hours.water_temp` | 운영 조정 | 3 | v1.5 7.3절 |
| 수온 **추정 지연** | `evaluation.interpolation_stale_minutes` | 운영 조정 | `<미결>` | 근거 없음 — 관측 임계(3h)를 그대로 쓸지 포함해 결정 필요 |
| 염분 (`dtRecent`) | `stale_threshold_hours.salinity_tide` | 운영 조정 | `<미결>` | v1.5 `salinity: 2160`은 정선관측 기준이라 쓰지 않는다. 518분 연속 결측 판정(v1.5 20절)과 연동 |
| 물때·풍속·기온 (`dtRecent`) | `stale_threshold_hours.tide_level` / `wind_speed` / `air_temp` | 운영 조정 | `<미결>` | v1.5 7.3절에 키 없음 |
| DO (정선) | `stale_threshold_hours.dissolved_oxygen` | 운영 조정 | `<미결>` | v1.5 값 2160(90일)을 그대로 쓰면 마지막 유효값이 2025-11일 경우 데모 내내 STALE — 클로로필과 같은 구조. 0m DO 날짜별 확인(4.8절) 후 결정 |
| 클로로필a | `stale_threshold_hours.chlorophyll` | **판정 정의** | `null` | 게시 감시로 판정 (4.5절, 충족계획서 1절) |
| 적조 | `stale_threshold_hours.red_tide_bulletin` | 운영 조정 | 72 | v1.5 7.3절. **기준 시각은 마지막 성공 호출**(`adapter_health.last_success_utc`)이지 마지막 속보가 아니다. 적조 현재값의 유효 기간(`bulletin.current_window_days`, 4.8절)과는 다른 개념이다 |
| **산출 지연** (`grading`) | `evaluation.grading_stale_minutes` | 운영 조정 | `<미결>` | 이 문서 신설 |

- 출력: `axis_status`(5.3절) → `result.updated`

### ③-2 알림 (2.2절)

| 주제 | 발행 | 소비 | 본문 |
| --- | --- | --- | --- |
| `grade.done` | grading | evaluation | `grade_run_id`, `axis`, `farm_ids` |
| `result.updated` | evaluation | (선택) 웹 서비스 캐시 무효화 | `farm_ids`, `axes`, `updated_at_utc` |

- 멱등: `axis_status`는 PK (`farm_id`, `axis`) + ③-1의 `basis_utc` 쓰기 규칙. 같은 `grade.done`을 두 번 받아도 결과 테이블이 같다(P2)

### ③-3 설정 (2.0.6·4.9절)

- 이 skill이 읽는 **운영 조정**(`tide.flatline_minutes`는 `processor` 전용이라 제외): `stale_threshold_hours.*`(**`chlorophyll` 제외**), `evaluation.interpolation_stale_minutes`·`grading_stale_minutes`. ConfigMap에서 **기동 시 한 번** 읽는다 — 실행 중 다시 읽지 않는다
- 이 skill이 읽는 **판정 정의**: `stale_threshold_hours.chlorophyll: null` — 클로로필은 임계 없이 게시 감시로 판정한다
- 워크로드 설정(`evaluation-sweep` 주기, 권장 10분)은 `HANDOFF.md` 몫이다 — 코드에 박지 않는다
- `<미결>` 값은 채우지 않는다. **판정 재생 픽스처가 임계에 상대적**이어서 값이 정해지면 그대로 돈다

### ③-4 운영 조정 게이트 — `evaluation gate` (2.0.6절)

1. **스키마 검사** — `contracts/config/operational.schema.json`: 키 집합 고정(누락·모르는 키는 실패 — 오타 방어), 타입·단위, `<미결>` 같은 자리 표시 거부, 스키마 버전(`operational-v1`) 일치. 하한은 **실측 근거가 있는 키만** 둔다 — `dtRecent` 축은 최장 갱신 간격 15.4분(v1.5 4.3절) 미만 거부 *(제안)*
2. **판정 재생** — `evaluation` 이미지의 `gate` 명령에 새 ConfigMap을 넣고 **7.3b 축 상태 계약 픽스처와 P3·P6·P10·P15**를 돌린다. 픽스처의 시각은 **임계에 상대적으로** 짜서(임계 직전 / 직후), 값이 바뀌어도 "임계 전에는 정상, 넘으면 해당 상태"가 나오는지와 게시 대기·산출 지연이 삼켜지지 않는지를 본다
- 건수 보존(7.7절 ②)은 여기서 돌리지 않는다. 운영 조정 키는 적재 건수에 영향을 주지 않고, 적재 건수를 바꿀 수 있는 키(좌표 범위 등)는 판정 정의로 이미지 쪽 게이트가 지킨다
- **남는 한계**: 임계 **값 자체가 적절한지**는 게이트가 판단하지 못한다. PR 리뷰의 몫이다. manifest 레포 CI가 이 명령을 실제로 부르는지도 인프라 구성에 달려 있다 — 이 모듈은 명령과 사용법을 `HANDOFF.md`로 넘기는 데까지만 한다
- **판정 재생 대상이 아닌 운영 조정 키**: `tide.flatline_minutes`는 `processor`(값 멈춤 감지, 4.1절)가 쓰므로 `evaluation` 이미지의 판정 재생으로 확인할 수 없다. 이 키는 **스키마 검사와 PR 리뷰로만** 지킨다. 운영 조정 키 중 `processor`가 쓰는 것은 이 하나뿐이다

### ③-5 결과 테이블 (5.3절)

**결과 테이블 — 웹 서비스가 읽는 것** (의미와 요구사항은 5.5절)

| 테이블 | 핵심 컬럼 | 비고 |
| --- | --- | --- |
| `farm_readings` | `farm_id`, `axis`, `value`, `lower`, `upper`, `unit`, `derivation`, `provenance`, `none_reason`(nullable), `validated_scope`(nullable), `grade`(nullable — 적조만), `alertable`, `source_ref`, `distance_km`, `observed_at_utc`, `computed_at_utc` | 현재값. PK (`farm_id`, `axis`). **`provenance = NONE`이어도 계산된 값은 비우지 않는다**(4.8절). `none_reason`은 `evaluation`의 입력 — 화면 사유는 `axis_status.reason` |
| `farm_reading_history` | 위 + `ts_utc` | 곡선용 시계열. 보존 기간 미결(11절). PK (`farm_id`, `axis`, `ts_utc`) |
| `axis_status` | `farm_id`, `axis`, `state`, `reason`, `basis_utc`, `last_checked_utc` | 4.9절 쓰기 규칙. PK (`farm_id`, `axis`) |
| `bulletins` · `bulletin_details` · `bulletin_detail_areas` | 위 표와 같음 | 적조 속보 원천. **해역 없는 속보**는 여기에만 있다(4.8절). 지점별 해역은 `bulletin_detail_areas` |
| `interpolation_weights` · `interpolation_error` · `stations` | 위 표와 같음 | "근거 보기" — 사용 관측소·거리·가중치·오차 산출 기준 |

### ③-6 대시보드 계약 — 이 skill이 배포한다 (5.5절 전문)

> 아래 "필드의 의미" 표는 `CLAUDE.md` 6절의 표와 같은 원천(계획서 5.5절)이다. 이 skill은 이것을 `contracts/tables/`로 **배포**하는 주인이라 전문을 싣는다 — 내용을 고칠 때는 계획서를 먼저 고친다

이 모듈은 판정과 값을 적재하고, **그것을 어떻게 보일지는 대시보드가 정한다**(0.2절). 이 절은 결과 테이블의 의미와, v1.5 원칙 중 **대시보드가 지켜야 하는 것**을 넘기는 계약이다. `contracts/tables/`에 같은 내용으로 배포한다.

**필드의 의미**

| 필드 | 뜻 | 뜻하지 않는 것 |
| --- | --- | --- |
| `derivation` | 값의 유래 — `COMPUTED`(계산) / `MEASURED`(인근 실측) / `OFFICIAL`(기관 발표) / `SURVEY`(조사값) | — |
| `provenance` | 영역 판정 — 오차·방법 기준 등급. `NONE`은 **신뢰 기준 밖** | 배지. `NONE`이 "값 없음"을 뜻하지 않는다 |
| `none_reason` | `grading`이 기록한 `NONE` 사유 | 화면 표시용 사유가 아니다 — 표시는 `axis_status.reason` |
| `lower` · `upper` | 수온: `value` ∓ 오늘의 오차 P95 | 최솟값·최댓값이 아니다 |
| `source_ref` | 근거 원천 행의 키 — 수온 `run_id` / 인근 실측 `station_id` / DO·클로로필 `station_id@surveyed_on` / 적조 `cod_news#seq` | 사람이 읽는 설명이 아니다 |
| `validated_scope` | 계산값의 **검증 범위** — `STATION_SITES`는 관측소 위치에서만 교차검증했다는 뜻. 계산값(`COMPUTED`)에만 채운다 | 만 안쪽 양식장의 추정이 검증됐다는 뜻이 아니다 — **만 안쪽은 미검증** |
| `alertable` | **발송 자격** — 계산 시점의 정적 자격 | 지금 보내라는 뜻이 아니다. 신선도를 담지 않는다 — 발송 후보는 `axis_status`와 함께 본다(W5) |
| `bulletins.grade` · `bulletin_details.grade` · `farm_readings.grade` | 적조 공식 4단계 `NONE`(예비특보 미만) / `PRE_ADVISORY` / `ADVISORY` / `WARNING`, 그리고 `NOT_GRADED`(비대상 종) · `UNKNOWN`(원인생물·밀도·세부 행 없음) | 여기의 `NONE`은 `provenance`의 `NONE`(신뢰 기준 밖)과 **다르다**. `farm_readings.grade`는 `grading`이 고른 현재값 행의 등급이다 — 대시보드가 다시 고르지 않는다 |
| `axis_status.state`·`reason` | 침묵 분류(4.9절 상태 값 17종)와 그 사유. 겹치면 4.9절 우선순위 | 화면 문구. `provenance`의 `NONE`과 다르다 — 값을 못 쓰는 경우는 `NOT_USABLE` |
| `observed_at_utc` · `computed_at_utc` · `basis_utc` · `last_checked_utc` | 관측 시각 · 산출 시각 · 판정에 쓴 가장 새 입력의 시각 · 판정 시각 | — |

**대시보드 요구사항** — v1.5 원칙을 대시보드가 지킨다

| # | 요구사항 | 근거 |
| --- | --- | --- |
| W1 | **배지는 `derivation`과 축으로 정한다.** `derivation = COMPUTED`인 값에 `인근 실측`·`공식 발표` 배지를 붙이지 않는다. `provenance`에서 배지를 끌어내지 않는다 — `OBSERVED`·`NEAREST` 수준의 추정값이 실측처럼 보이게 된다 | v1.5 1.4절 "추정을 실측처럼 보이게 하지 않는다", v1.5 1.3.2절 계기판 표 |
| W2 | **`provenance = NONE` 값은 표시하지 않는다.** 값은 근거 보기·운영 확인용으로 남아 있다 | v1.5 4.6.1절 ">3.0 표시하지 않음", v1.5 6.2절 하구 제외 |
| W3 | **시각으로 신선도를 판단한다.** `axis_status.last_checked_utc`가 한계를 넘으면(이 모듈이 멈춘 경우) 값 대신 "확인 불가"류로 보인다. 한계값은 대시보드 설정이다. 조사값·게시값은 `observed_at_utc`를 값 옆에 둔다 | v1.5 S3, v1.5 4.6.2절 그래픽 규칙 4 |
| W4 | **두 테이블의 순간 불일치를 감안한다.** `farm_readings`(grading)와 `axis_status`(evaluation)는 쓰는 시점이 다르다. `axis_status.basis_utc`가 `farm_readings.computed_at_utc`보다 이르면 상태가 아직 새 값을 반영하지 않은 것이다(보통 수 초, sweep이 바꾸는 상태는 최대 sweep 주기) | 4.9절 |
| W5 | **발송 시점은 대시보드가 정한다.** `alertable = true`이고 **`axis_status.state`가 정상인 축**의 값만 발송 후보다 — `alertable`은 계산 시점의 정적 자격이고, 그 뒤의 신선도·장애는 `axis_status`가 담는다. 두 판정을 조합할 뿐 다시 계산하지 않는다. 등급 상승 시에만·새 속보만·구독·중복 억제는 `alert-svc`. `UNKNOWN`은 등급 없이 "속보 발생" 문구 | v1.5 8.1절 15, 5.3절 |
| W6 | **해역 없는 속보**(`bulletins`에만 있고 대응 양식장 없음)의 표시 정책은 대시보드가 정한다. 팀 논의 권고: 전 양식장에 "해역 미상 속보"로 표시, 발송하지 않음 | 4.8절 |
| W7 | **"발송 안 된 것" 패널**의 변화 감지는 대시보드가 `farm_reading_history`와 `alertable`로 한다 | v1.5 S2' |
| W8 | 침묵 분류(`state`)별 화면 문구는 대시보드가 정한다. v1.5 4.5절 "화면" 열이 기준 | v1.5 4.5절 |

**대시보드가 하지 않는 것**: `provenance`·오차·침묵 분류를 **다시 계산하지 않는다.** DB를 거쳐 송출해도 정합성이 실제로 깨지는 경우는 이것뿐이다(0.2절).

### ③-7 운영 지표 (9절)

| 지표 | 라벨 |
| --- | --- |
| `evaluation_state_total` | `axis`, `state` |

---

## ④ 이식 출처 (6.3절)

| 새 경로 | 검증 코드 위치 | 처리 |
| --- | --- | --- |
| `evaluation/` | — | **신규** — v1.5 4.5·4.6.1절 규칙이 기준. 검증 코드 없음 |

---

## ⑤ 함정

- **조용한 것을 장애로 보지 않는다.** 어장환경 2026년 `00` + 0건은 **게시 대기**다. 조사 간격 기준(90일 등)으로 판정하면 데모 내내 STALE이 되어, "조용한 게 정상인지 구분한다"는 서비스 주장을 정반대로 보여 준다
- **장애를 조용함으로 삼키지 않는다.** 게시 감시 호출 실패·파싱 실패는 게시 대기가 아니다(N8). 빈 결과 코드는 `PARSE_FAILURE`다 — "0건"과 "못 읽음"은 다르다
- **적조 신선도는 마지막 속보가 아니라 마지막 성공 호출로 본다.** 속보가 없는 시기(10~11월)에 적조가 STALE이 되면 안 된다(P15)
- **값 멈춤은 신선도와 다르다.** 새 값이 들어오는데 같은 값인 것이다 — 판정이 아니라 "확인 중" 상태다
- **추정이 멈췄을 때 수온에 최근접 관측값을 넣지 않는다.** 수온 축은 `INTERPOLATION_STALE`로 드러나야 한다(P3)
- **`grading`이 멈춰도 인근 실측 축이 옛 값으로 "정상"이면 안 된다.** 기준은 "적재 이후 `farm_readings` 미갱신"이다 — 축별 주기와 무관하게 잡힌다(P10)
- **늦게 도착한 옛 판정이 새 판정을 덮지 않는다.** `basis_utc`로 비교하고, 같으면 `last_checked_utc`가 나중인 쪽(P12)
- **sweep은 값을 만들지 않는다.** 앞 단계를 대신 돌리면 멈춘 단계가 가려진다
- **이 단계가 멈추면 스스로 드러낼 방법이 없다.** `last_checked_utc`가 멈추는 것으로만 보이고, 판단은 대시보드(W3)다 — 그래서 `last_checked_utc`를 판정마다 반드시 갱신한다
- **v1.5 `dissolved_oxygen: 2160`을 가져오지 않는다.** 마지막 유효값이 오래됐다면 DO가 데모 내내 STALE이 된다. 값은 `<미결>`이다
- **`none_reason`보다 이 단계 자신의 사유가 우선이다.** 추정 지연이면 `EXCLUDED_ZONE`보다 `INTERPOLATION_STALE`을 쓴다
- **`provenance`의 `NONE`을 상태 자리에 쓰지 않는다.** 값을 못 쓰는 경우는 `NOT_USABLE`, 추정·산출이 멈춘 경우는 `INTERPOLATION_STALE`·`GRADING_STALE`이다. 대시보드는 `state`로 문구를 고른다(W8)
- **겹치면 우선순위표대로 하나만 쓴다.** 판정 순서에 따라 같은 상황이 다른 상태로 나오면 P12 쓰기 규칙도 흔들린다
- **계절 밖은 `axis_coverage.season_months`로만 판정한다.** 설정 키는 없다
- **배지·문구를 만들지 않는다.** 분류(`state`)와 사유(`reason`)까지다

---

## ⑥ 검사와 기대값

**침묵 분류 계약** (7.3절 — 이 skill 소유는 7.3b)

v1.5 4.5절 표의 각 행 + v1.4 추가 3종마다 입력과 기대 상태를 한 쌍씩 둔다. **분류 규칙을 바꾸면 이 표를 먼저 고친다.** 분류마다 확인할 수 있는 단계가 다르므로 둘로 나눈다.

| 묶음 | 분류 | 확인 단계 |
| --- | --- | --- |
| **7.3a 응답 해석** | 정상 / 정상적 침묵(`00`+0건) / 조건 불일치 / 일시 중단 / 타임아웃 / 요청 오류 / 파싱 실패 / 진짜 장애 / 필터 무시 / 빈 값 레코드 | S2 (`classifier`·`completeness`) — 빈 값 레코드는 S5 |
| **7.3b 축 상태** | 커버리지 밖 / 계절 밖 / 게시 대기 / 값 멈춤 — 확인 중 / 추정 지연 / **산출 지연** / 값 사용 불가 + 7.3a 결과와 `none_reason`이 축 상태로 옮겨지는지 + **겹침 우선순위**(4.9절 — 계절 밖 + 호출 실패, 게시 대기 + 산출 지연, 호출 실패 + 신선도 초과 각 1쌍 이상) | S10 (`evaluation`) |

**합성 양식장 검사** (7.5절)

| # | 검사 | 통과 기준 |
| --- | --- | --- |
| P2 | 알림 연쇄 | `obs.loaded`(조위) 1건 → `interp.done`·`grade.done`·`result.updated` 각 1건. **같은 알림을 두 번 보내도 결과 테이블이 같다** |
| P3 | `interpolation` 정지 후 신선도 임계 경과 | 수온 `axis_status.state` = `INTERPOLATION_STALE`. **`farm_readings` 수온에 인근 실측값이 들어가지 않는다** |
| P6 | 어장환경 2026 `OK_EMPTY` | 클로로필 `axis_status` = **게시 대기**, 값은 `BASELINE` + 조사일 |
| P7 | 좌표 불량 합성 양식장 (위도 32.5, 경도 140) | 전 축 `provenance = NONE`, `none_reason = INVALID_COORDS`, `axis_status.state = NOT_USABLE`·`reason`도 같음 |
| P8 | 섬진강하구 제외 구역 안 합성 양식장 | 수온 `provenance = NONE`, `none_reason = EXCLUDED_ZONE`, `axis_status.state = NOT_USABLE`이고 `value`는 저장됨, 인근 실측 축은 정상 산출 |
| P10 | `grading` 정지 후 새 `obs.loaded`(조위) 적재, 한계 경과 | 해당 양식장의 인근 실측 축 `axis_status.state` = `GRADING_STALE`. 옛 값으로 "정상"이면 실패 — v1.5 실험 8 |
| P12 | `axis_status` 쓰기 순서 — (a) 새 입력 판정 뒤 옛 입력 판정이 늦게 도착 (b) 같은 입력에 sweep이 나중에 신선도 초과 판정 | (a) 옛 판정이 덮지 못함 (b) sweep 판정이 기록됨 |
| P15 | 적조 신선도 — (a) 호출은 계속 성공, 속보는 임계보다 오래 없음 (b) 호출 실패가 임계보다 오래 이어짐 | (a) 정상적 침묵 — **`STALE`이면 실패** (b) `STALE`. 임계는 설정에 상대적으로 둔다 |

**게이트** (7.6절)

| # | 검사 | 통과 기준 |
| --- | --- | --- |
| B7 | `evaluation gate`에 (a) 임계를 바꾼 정상 ConfigMap (b) `chlorophyll` 키를 넣은 ConfigMap | (a) 통과 (b) **스키마 검사 실패** — `chlorophyll`은 판정 정의 |

- 7.3b·P3·P6·P10·P15는 `evaluation gate`의 **판정 재생** 대상이기도 하다 — 임계에 상대적으로 짜야 인프라가 값을 바꿔도 검사가 유효하다
- P7·P8은 `grading`의 출력(`none_reason`)이 `axis_status.reason`까지 옮겨지는지 보는 **통합 검사**다
- 관련 검사(다른 skill 소유): N8(게시 감시 실패) — `fishery` / Q6(`adapter_health` 갱신) — `common-core` / B6·B8(기동 시 검사) — `common-core`

---

## ⑦ 주인이 아닌 사실 — 참조만

| 사실 | 주인 |
| --- | --- |
| 상태 이름표(결과 코드 → 상태 → 분류), **축 상태 값**, 필드 의미 | `CLAUDE.md` 6절 |
| `adapter_health` 갱신 규칙, 운영 조정 스키마·기동 시 검사, 큐 | `common-core` |
| 값 멈춤 플래그 | `tide` |
| `publication_checks` 기록 | `fishery` |
| `farm_readings`, `none_reason` 값 목록 | `grading` |
| 결과 테이블 DDL | `repository` |

이 skill이 **주인인 사실**(A.3): 추정 지연·산출 지연 판정, **상태 겹침 우선순위**, 운영 조정 판정 재생(`gate`), 결과 테이블 의미 계약의 배포.

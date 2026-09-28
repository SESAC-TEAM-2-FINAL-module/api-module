---
name: interpolation
description: "IDW 수온 추정과 오늘의 오차 — src/api_module/interpolation/(IDW 컨슈머와 interpolation-error 명령)을 만들거나 고칠 때 쓴다 (지시서 I-7). 조위관측소 적재 알림(obs.loaded)에서 시작, 수온만 추정, 사용 관측소 필터와 정렬 창, 거리 역제곱 N=5, 관측소별 가중치 기록, 관측소 하나씩 빼는 교차검증 P95(집합별), interp.done 발행. 출처 등급·NONE 판정(grading), 추정 지연 판정(evaluation) 작업에는 쓰지 않는다."
---

# interpolation

조위관측소 수온으로 양식장 수온을 **IDW(거리 역가중)**로 추정하고, 그 추정이 오늘 얼마나 맞는지(**오늘의 오차**)를 교차검증으로 구한다. 추정값을 어떤 등급으로 볼지는 `grading`이 정한다. 공용 용어는 `CLAUDE.md` 6절에 있다. 괄호 속 "N절"은 계획서의 절이다.

---

## ① 범위

| 경로 | 이 skill이 만드는 것 |
| --- | --- |
| `interpolation/main.py` | 두 진입점 — **큐 컨슈머**(`obs.loaded` 중 조위관측소 적재만)와 **`interpolation-error` 명령**(하루 1회) |
| `interpolation/` 계산부 | IDW 본체, 사용 관측소 필터, 교차검증(오늘의 오차), 관측소 집합별 오차 캐시 |
| 적재 | `interpolation_runs`·`interpolation_weights`·`interpolation_error` → `interp.done` 발행 |

| 이미지 | 워크로드 | 실행 | 계기 | 하는 일 |
| --- | --- | --- | --- | --- |
| `interpolation` | `interpolation` | Deployment, 큐 컨슈머 | **`obs.loaded` (조위관측소)** | 양식장 좌표 읽기 → IDW → 오차 조회(`interpolation_error`, 없는 관측소 집합이면 산출) → 적재 → `interp.done` |
| | `interpolation-error` | CronJob, 1일 | 시각 | **오늘의 오차** 하루 1회 산출(4.7절) → `interpolation_error`. IDW 추정은 하지 않는다 *(제안 — 11절)* |

**만들지 않는 것**

- 양식장 좌표 읽기(`common/farm_sites/`), 거리 계산 함수(`common/geo/`) → `common-core`. 이 skill은 호출한다
- **출처 등급·`NONE` 판정**(오차 P95 → v1.5 4.6.1절 단계, > 3.0 → `NONE`), **제외 구역 판단**(`grading.excluded_zones`를 양식장 좌표로) → `EXCLUDED_ZONE`, **`validated_scope` 기록** → 모두 `grading`. 이 skill은 제외 구역을 보지 않고, 값·오차·가중치를 만든다
- **추정 지연 판정**(`INTERPOLATION_STALE`) → `evaluation`. 추정이 멈추면 드러나야 하므로, 이 skill이 멈췄을 때 최근접 관측값으로 대신 채우는 경로를 두지 않는다
- 값 멈춤 플래그(`STALE_SUSPECT`)를 **다는 것** → `tide`. 이 skill은 그 관측소를 뺄지(`interpolation.exclude_flatline`)만 적용한다

---

## ② 원천 절 (계획서)

1.6(양식장 좌표 입력) · 2.1(`interpolation`·`interpolation-error`) · 2.2(`interp.done`, 예외 둘) · 4.1(값 멈춤) · 4.6(`SENSOR_QUALITY`) · 4.7 · 5.3(interpolation 테이블) · 6.3(interpolation 행) · 7.7(설정)

---

## ③ 사실

### ③-1 IDW 사양 (4.7절)

| 항목 | 사양 | 근거 |
| --- | --- | --- |
| 시작 계기 | `obs.loaded` 중 **조위관측소 적재**만 | 2.2절 |
| 대상 변수 | **수온만.** 염분은 추정하지 않는다 | 염분 P95 7.55 psu (v1.5 6.2절) |
| 입력 | 최신 수온 관측값 + 양식장 좌표(1.6절) | |
| 사용 관측소 | `STATION_INACTIVE`·결측·`SENSOR_QUALITY`(4.6절 R3·R4) 제외, `STALE_SUSPECT`는 설정에 따름(4.1절). 기준 시각 이전 **정렬 창**(설정값, 기본 30분) 안의 최신값만. **기준 시각 = 이 실행을 시작시킨 `obs.loaded`의 `observed_to_utc`**(그 적재의 가장 늦은 관측 시각) → `interpolation_runs.ref_time_utc`. 알림에 있는 값이라 같은 알림이 두 번 와도 같다 | 관측소별 갱신 간격 3.6~15.4분 |
| 방법 | 거리 역제곱(p=2), 가까운 **N=5** — **설정값** | v1.5 권장 `M2` N=5. `B2`(단순평균) N=2 승격은 미결(11절) |
| 제외 구역 | 섬진강하구 인접 등 **제외 구역**(판정 정의 `grading.excluded_zones`, 값 `<미결>` — 중심·반경 목록) 안 양식장도 추정값은 계산해 저장한다. **이 단계는 제외 구역을 보지 않는다** — 구역 판단과 `provenance = NONE`(사유 `EXCLUDED_ZONE` — 검증 범위 밖)은 `grading`이 양식장 좌표로 한다(4.8절) | v1.5 6.2절 |
| 가중치 기록 | 관측소별 거리·가중치를 매 실행 저장 | "근거 보기"용. 가막만 예시에서 최근접 1곳이 약 87% |
| **오늘의 오차** | 최근 **N일**(설정값, 결과 보기 전 고정) 관측으로 **관측소 하나씩 빼고 맞히는 교차검증**을 돌려 절대오차 **P95**를 산출. 하루 1회 갱신 — `interpolation-error` 워크로드(2.1절) | v1.5 4.7절 조건 ④ |
| 관측소 집합이 바뀔 때 | 그 실행에 쓰인 **관측소 집합 기준으로 오차를 다시 구한다**(집합별 캐시). 가까운 관측소가 빠지면 오차가 자연히 커지고, 한계를 넘으면 4.8절에서 `NONE` | v1.5 S6 — 처리 방식은 팀 결정 전까지 v1.5 4.6.1절 기준을 그대로 따름 |
| 검증 범위 표시 | 모든 추정값에 `validated_scope = STATION_SITES` — **만 안쪽은 미검증**. `grading`이 `farm_readings.validated_scope`에 기록한다(계산값만) | v1.5 6.2절 |

- 교차검증에서 **같은 그룹 안의 동일 관측소 중복을 제거**한다. 안 하면 거리 0km 참조가 25% 섞인다(1차 IDW 실험에서 실제로 발생한 함정)
- 출력: `interpolation_runs`·`interpolation_weights`·`interpolation_error`(5.3절) → `interp.done`

### ③-2 설정 (7.7절 — 전부 판정 정의)

```yaml
interpolation.method: M2                # 기본값 — B2 승격 결정 대기 (11절)
interpolation.power_p: 2
interpolation.n_neighbors: 5            # 기본값 — 같음
interpolation.align_window_min: 30      # 기본값 — 결정 대기 (11절)
interpolation.exclude_flatline: <미결>
interpolation.error_window_days: <결과 보기 전 고정>
```

- 결정 대기인 기본값(`method`·`n_neighbors`·`align_window_min`)은 **기본값으로 구현**하고, 바뀌어도 코드가 그대로 돌게 한다 — `B2`(단순평균) 승격이 결정되면 설정만 바뀐다
- `exclude_flatline`은 `<미결>`, `error_window_days`는 **결과를 보기 전에 고정**해야 하는 값이다. 값을 채우지 않는다. 교차검증 결과를 보고 창을 고르면 오차를 좋게 보이도록 고른 것이 된다

### ③-3 저장과 알림 (5.3·2.2절)

| 테이블 | 핵심 컬럼 | 비고 |
| --- | --- | --- |
| `interpolation_runs` | `run_id`, `load_id`, `metric`, `method`, `power_p`, `n_neighbors`, `ref_time_utc`, `station_set_key`, `error_p95`, `error_window_days`, `computed_at_utc` | 4.7절. `station_set_key` = 사용 관측소 `station_id`를 **정렬해 `,`로 이은 값**(예: `tide:DT_0014,tide:DT_0016`). PK `run_id`, **고유 (`load_id`, `metric`)** — 적재 한 번·항목 하나에 IDW 한 번. 같은 `obs.loaded`가 두 번 와도 같은 행 |
| `interpolation_weights` | `run_id`, `farm_id`, `station_id`, `distance_km`, `weight` | "근거 보기". PK (`run_id`, `farm_id`, `station_id`) |
| `interpolation_error` | `station_set_key`, `metric`, `window_days`, `p95`, `mae`, `n_samples`, `computed_on` | 오늘의 오차 (집합별). `station_set_key`는 `interpolation_runs`와 같은 형식. PK (`station_set_key`, `metric`, `window_days`, `computed_on`) |

| 주제 | 발행 | 소비 | 본문 |
| --- | --- | --- | --- |
| `interp.done` | interpolation | grading | `run_id`, `load_id`, `farm_count`, `metric`, `error_p95`, `stations_used` |

- **멱등**: `interpolation_runs`의 고유 (`load_id`, `metric`)가 멱등 키다. 같은 `obs.loaded`가 두 번 와도 같은 행이 되고, `interp.done`도 같은 `run_id`로 나간다
- `interpolation_error`는 두 곳에서 쓴다 — `interpolation-error`(하루 1회, 그날 쓰인 관측소 집합)와 컨슈머(**처음 보는 관측소 집합**이면 그 자리에서 산출). 키가 (`station_set_key`, `metric`, `window_days`, `computed_on`)라 같은 날 같은 집합은 한 행이다
- 두 진입점 모두 **추정값(`interp.done`)을 대신 만들지 않는다.** `interpolation-error`는 오차만 만든다(2.2절 예외)

---

## ④ 이식 출처와 사용 금지 (6.3절)

검증 폴더는 별칭으로만 부르고 **읽기만** 한다. 이식할 때마다 `docs/SOURCES.md`에 `새 경로 | 출처 파일::함수 | 출처 파일 SHA-256 | 바꾼 점`을 남긴다.

| 새 경로 | 검증 코드 위치 | 처리 | 이식 시 반드시 바꿀 것 |
| --- | --- | --- | --- |
| `interpolation/` | `$SRC_IDW/src/idw.py` | **이식** | IDW 계산 본체. 입력을 CSV가 아니라 DB·양식장 좌표로 |
| | `$SRC_IDW/stage3_idw.py` (2차 재검증) | **이식** | 교차검증 — **그룹 내 동일 관측소 중복 제거가 들어간 판** |
| | `$SRC_IDW/aggregate_band_redesign.py` | 참고 | P95·계절 구간 집계 방식 |
| | `$SRC_IDW/src/experiments.py` `run_e1()` | **사용 금지** | 1차 실험 — 중복 관측소 미제거, 정선 수심 혼입 |

- **거리 계산은 `idw.py`의 방식 그대로** `common-core`의 `common/geo/`에 있어야 한다. 방식이 다르면 F12(P95 2.48) 재현이 어긋난다 — I-7에서 두 계산이 같은 값을 내는지 확인하고, 다르면 멈춰 보고한다

---

## ⑤ 함정

- **교차검증에서 같은 그룹의 동일 관측소 중복을 제거한다.** 안 하면 자기 자신을 거리 0km로 참조하는 경우가 25% 섞여 오차가 실제보다 좋아 보인다(1차 IDW 실험의 실제 사고)
- **염분은 추정하지 않는다.** IDW 염분 P95가 7.55 psu다 — 화면에 올릴 수 없는 수준이다. 염분은 `grading`이 인근 실측으로 채운다
- **정선관측 수온을 섞지 않는다.** 1차 실험은 정선 수심별 수온이 섞여 표층 추정을 오염시켰다. 입력은 조위관측소 수온(`dtRecent`)뿐이다
- **추정이 멈췄을 때 최근접 관측값으로 채우지 않는다.** 그러면 추정이 죽은 것이 화면에서 사라진다(`CLAUDE.md` 3절). 멈춤은 `evaluation`이 `INTERPOLATION_STALE`로 드러낸다
- **정렬 창 밖의 값을 쓰지 않는다.** 관측소마다 갱신 간격이 3.6~15.4분이라, 창 없이 "각자의 최신값"을 모으면 서로 다른 시각의 값이 섞인다
- **관측소 집합이 바뀌면 오차도 바뀐다.** 가까운 관측소가 빠지면 오차가 커지는 것이 정상이다. 전체 집합의 오차를 그대로 쓰지 않는다 — 집합별로 구한다
- **최근접 관측소가 가중치 대부분을 가져간다**(가막만 예시 약 87%). 그래서 가중치 기록이 "근거 보기"의 핵심이다 — 매 실행 저장한다
- **`validated_scope = STATION_SITES`는 "만 안쪽은 검증되지 않았다"는 뜻이다.** 교차검증은 관측소 위치에서만 할 수 있다. 값을 `farm_readings`에 쓰는 것은 `grading`이다
- **기준 시각을 "지금"으로 잡지 않는다.** 알림의 `observed_to_utc`를 쓴다 — "지금"을 쓰면 같은 알림을 두 번 처리할 때 정렬 창이 달라져 결과가 갈린다(멱등 위반)
- **`station_set_key`는 정렬한 뒤 잇는다.** 정렬하지 않으면 같은 집합이 순서만 달라 다른 키가 되고, 오차 캐시가 중복된다
- **계절 경계는 실행 설정이 아니다.** F12 재현(여름 6/24~8/31, 가을 9/1~9/22 MAE)에서만 쓰는 상수다

---

## ⑥ 검사와 기대값

| # | 입력 | 통과 기준 |
| --- | --- | --- |
| F12 | 같음 | 교차검증 재현: `M2` N=5 수온 **P95 2.48**, 염분 **P95 7.55** / 수온 MAE 여름(6/24~8/31) **0.9106**, 가을(9/1~9/22) **0.3646** / `B1` 대비 개선율 수온 **21.5%** — v1.3 재검증 수치와 같아야 함 |

| # | 검사 | 통과 기준 |
| --- | --- | --- |
| P1 | 가막만 합성 양식장(34.68, 127.69) | 최대 가중치 관측소 = **여수(`DT_0016`)**. 실제 가중치 값은 기록만 (목업의 87%는 근사 좌표 계산) |
| P9 | 가장 가까운 관측소를 뺀 집합 | 오차 P95가 전체 집합보다 **크거나 같다**. 값은 기록 |

| # | 규칙 (절) | 입력 | 통과 기준 |
| --- | --- | --- | --- |
| Q7 | IDW 입력 필터 (4.7) | 관측소 A는 `SENSOR_QUALITY`, B는 정렬 창 밖(창 + 1분), C는 창 안 | A·B는 `interpolation_weights`에 없고 C만 쓰인다 |

- **F12와 P9는 CI 게이트 밖이다**(실측 가공 CSV가 필요). S8에서 **로컬 수동 실행**으로 확인하고 S12에서 다시 돌린다(7.1절). 입력은 `fixtures/derived/`의 경로 참조와 해시 — 원본은 `$SRC_IDW/output/observations.csv`
- **P1은 게이트 안**이다 — `fixtures/derived/stations.csv`와 `fixtures/synthetic/farms.csv`만 쓴다
- 관련 검사(다른 skill 소유): P3(추정 정지 → `NONE`) — `evaluation` / P4(오차 → 등급)·P8(제외 구역) — `grading` / Q5(값 멈춤 플래그) — `tide`

---

## ⑦ 주인이 아닌 사실 — 참조만

| 사실 | 주인 |
| --- | --- |
| 필드 의미, `_utc` 규칙 | `CLAUDE.md` 6절 |
| 양식장 좌표 읽기, 거리 계산 함수, 큐, 품질 규칙(`SENSOR_QUALITY`) | `common-core` |
| 값 멈춤 플래그(`STALE_SUSPECT`)를 다는 규칙 | `tide` |
| 오차 → 출처 등급, `NONE`·`EXCLUDED_ZONE`(제외 구역 판단 포함), `none_reason`, `validated_scope` 기록 | `grading` |
| 추정 지연 판정 | `evaluation` |

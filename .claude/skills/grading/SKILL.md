---
name: grading
description: "출처 등급·발송 자격 — src/api_module/grading/(큐 컨슈머)을 만들거나 고칠 때 쓴다 (지시서 I-8). obs.loaded·interp.done을 받아 양식장 × 축마다 farm_readings 한 행을 채운다: 양식장 ↔ 원천 대응(최근접 관측소·정점, 적조 현재값), 표층 규칙 적용, derivation·provenance(영역 판정, NONE 포함)·none_reason·validated_scope·alertable(발송 자격), lower·upper, source_ref, grade.done 발행, 적조 위험도 지수(파생 축 red_tide_risk·risk_index_factors·risk_index_levels — 지시서 I-16). 침묵 분류·신선도 판정(evaluation), 배지·문구·발송 시점(대시보드) 작업에는 쓰지 않는다."
---

# grading

양식장 × 축마다 **값 하나와 그 값에 대한 판정**을 `farm_readings`에 쓴다. 판정은 두 축으로 나뉜다 — **표시 축 `provenance`**(오차·방법으로 본 영역, `NONE` 포함)와 **발송 축 `alertable`**(발송 자격). 값의 유래 `derivation`을 함께 기록해 **계산값은 어떤 등급이어도 발송되지 않게** 한다. 공용 용어(필드 의미 전체)는 `CLAUDE.md` 6절에 있다. 괄호 속 "N절"은 계획서의 절이다.

---

## ① 범위

| 이미지 | 워크로드 | 실행 | 계기 | 하는 일 |
| --- | --- | --- | --- | --- |
| `grading` | `grading` | Deployment, 큐 컨슈머 | **`obs.loaded`(모든 축)**, `interp.done`(수온) | 출처 등급 · `alertable` → 적재 → `grade.done` |

| 경로 | 이 skill이 만드는 것 |
| --- | --- |
| `grading/main.py` | 큐 컨슈머 — `obs.loaded`(모든 축)와 `interp.done`(수온). **두 경로는 서로 기다리지 않는다**. 기동 시 `areas`가 비어 있으면 멈춘다(빈 해역 시드 검사 — 주인 `common-core`, 개정 19) |
| `grading/` | 양식장 ↔ 원천 대응, 표층 규칙 적용, 등급·자격 판정, `farm_readings`·`farm_reading_history` 적재, `grade.done` 발행 |

**만들지 않는 것**

- 양식장 좌표 읽기·좌표 검증·거리 계산 → `common-core`(`common/farm_sites/`, `common/geo/`). 이 skill은 호출한다
- IDW 추정과 오늘의 오차 → `interpolation`. 이 skill은 `interp.done`과 `interpolation_runs`·`interpolation_error`를 읽는다
- 적조 판정 순서·`UNKNOWN`·`NOT_GRADED`(주인 `bulletin`), 표층 규칙의 **정의**(주인 `line`) — 이 skill은 **적용만** 하고 다시 정하지 않는다
- 침묵 분류, 신선도·추정 지연·산출 지연 판정, `axis_status` 기록 → `evaluation`. `none_reason`을 `axis_status.reason`으로 옮기는 것도 `evaluation`이다
- 배지·화면 문구·노출 여부·발송 시점 → 대시보드(5.5절). **배지를 만들지 않는다**

---

## ② 원천 절 (계획서)

1.6(좌표 검증) · 2.1(`grading`) · 2.2(`grade.done`) · 4.2(적조 판정 — 참조) · 4.4(표층 정의 — 참조) · 4.7(제외 구역·`validated_scope`) · **4.8** · 5.3(`farm_readings`·`farm_reading_history`) · 5.5(필드 의미, W1·W2·W5) · 7.7(설정)

---

## ③ 사실

### ③-1 출처 등급 · 발송 자격 (4.8절 전문)

양식장 × 축마다 **표시 축(`provenance`)**과 **발송 축(`alertable`)**을 따로 산출한다(v1.5 4.6.1절). 값의 **유래(`derivation`)**를 함께 기록해, 표시 라벨이 무엇이든 계산값이 발송되지 않게 한다.

| 축 | 값 (저장) | `derivation` | `provenance` (영역 판정) | `alertable` (발송 자격) |
| --- | --- | --- | --- | --- |
| 수온 | IDW 추정. **`lower`·`upper` = `value` ∓ 오늘의 오차 P95** — 등급과 같은 기준(P95)이라 "95%의 경우 이 범위 안"을 뜻한다. **영역과 무관하게 저장** | `COMPUTED` | 오늘의 오차 P95로 정한다 — **≤ 1.0℃ → `OBSERVED` 수준 · ≤ 2.0℃ → `NEAREST` 수준 · ≤ 3.0℃ → `INTERPOLATED` 수준 · > 3.0℃ → `NONE`**(v1.5 4.6.1절 — 임계는 밴드 폭에서 유도). 현 실측 P95 2.48 → `INTERPOLATED` | **항상 `false`** |
| 물때·풍속·기온 | 최근접 활성 관측소 실측 + 거리 | `MEASURED` | `NEAREST` | 다음 둘을 모두 만족하면 `true` — ① 그 관측소의 최근 결과 코드 `00` ② 관측소가 `41`·`05` 상태가 아님 (v1.5 4.6절). **신선도는 조건에 넣지 않는다** — 새 관측이 없으면 이 단계는 다시 돌지 않아, 계산 시점의 신선도가 나중에 틀린다. 신선도는 `evaluation`이 시간에 따라 `axis_status`에 반영하고, 대시보드가 발송 후보를 고를 때 함께 본다(5.5절 W5). 알림에 "인근 관측소 값"임을 낮춰 표기하는 것(v1.5 "등급 하향 후 발송")은 대시보드(5.5절 W5) |
| 염분 | 최근접 활성 관측소(`dtRecent`) 실측 + 거리 — **항상 저장** | `MEASURED` | `grading.salinity_mode`(`NEAREST_TIDE` / `NONE`)에 따름 — **채택 `NEAREST_TIDE`**(2026-09-30). 최근접 관측소가 `grading.estuary_stations`에 들면 `NONE`(`EXCLUDED_ZONE`) (아래) | `NEAREST`일 때 물때 행과 같은 두 조건, `NONE`이면 `false` |
| 적조 | 양식장이 속한 해역의 공식 속보 — 아래 대응 규칙으로 고른 **현재값 세부 행** 하나. **`value` = 그 행의 `max_density`(개체/mL), `grade` = 그 행의 등급.** 대시보드가 속보 테이블에서 행을 다시 고르지 않게 고른 결과를 담는다 | `OFFICIAL` | `OFFICIAL` | 코클로디니움 등급이 **예비특보 이상**이면 `true` · `UNKNOWN`은 `true` · `NOT_GRADED`와 등급 없음(`NONE`)은 `false` |
| DO | 정선관측 표층 최근 **유효값** + 조사일. 표층은 **`grading`이 읽을 때 `line.surface_rule`과 `depth_m`으로 판별**한다(4.4절 — 채택 `INCLUDE`). 표층 규칙이 정해지지 않은 설정이면 값 없음(사유 `SURFACE_RULE_UNDECIDED`) | `SURVEY` | `BASELINE` (규칙 미정이면 `NONE`) | `false` |
| 클로로필a | 어장환경 조사값 + 조사 시각(`observed_at_utc`). **조사 기준 추정을 계산할지**는 설정 스위치(기본 꺼짐 — 교차검증 전) | `SURVEY` / `COMPUTED` | `BASELINE` | `false` |

- **불변식: `derivation = COMPUTED`인 행의 `alertable`은 언제나 `false`.** 7.5절 N11로 전 픽스처에서 검사한다
- **`provenance = NONE`은 "값이 없다"가 아니라 "신뢰 기준 밖"이라는 영역 판정이다.** 계산할 수 있었으면 `value`·`lower`·`upper`를 저장한다. `value`가 비는 것은 **계산 자체가 불가능할 때**뿐이다 — 좌표 불량, 입력 관측 없음, 표층 규칙 미결. 그리고 적조의 **유효 기간 안 현재 속보가 없을 때**다 — 이때는 `provenance = OFFICIAL`이고 `NONE`이 아니다 *(제안 — 아래 대응 규칙)*. `NONE` 영역 값을 보일지는 대시보드가 정한다(5.5절 W2)
- **`NONE`의 사유는 `grading`이 `farm_readings.none_reason`에 기록한다** — `INVALID_COORDS`(좌표 불량), `NO_INPUT`(입력 관측 없음), `SURFACE_RULE_UNDECIDED`(표층 규칙 미결), `EXCLUDED_ZONE`(제외 구역 — `grading.excluded_zones`를 양식장 좌표로 판단. 염분은 최근접 관측소가 `grading.estuary_stations`에 들 때도), `ERROR_ABOVE_LIMIT`(오차 P95 > 3.0), `SALINITY_MODE_NONE`(염분 영역 판정 `NONE`). `evaluation`이 이를 읽어 `axis_status.reason`으로 옮긴다(4.9절). **대시보드의 사유 표시는 `axis_status.reason`만 쓴다**(5.5절)
- **`alertable`은 발송 자격만 뜻한다.** "등급이 올랐을 때만", "새 속보일 때만", 구독·중복 억제 같은 **발송 시점**은 대시보드(`alert-svc`)가 정한다(5.5절 W5)
- 배지·문구는 이 모듈이 산출하지 않는다. 대시보드가 `axis`·`derivation`으로 정한다 — 계산값에 실측 배지를 붙이지 말라는 요구사항은 5.5절 W1
- **해역 없는 속보**(`item2` 없음 — `txt_seas`가 `item2` 안에 있다)는 대응할 양식장이 없으므로 `farm_readings`에 행을 만들지 않는다. `bulletins`에 저장만 하고, 보일지는 대시보드가 정한다(5.5절 W6)
- **염분 영역 판정** (v1.5 20절 — 4.2절 `NEAREST` vs 6.3절 "NEAREST 적용 안 함"). 설정값 `grading.salinity_mode`(`NEAREST_TIDE` / `NONE`)는 **영역 판정만** 정하고, 어느 쪽이든 최근접 실측값·거리는 저장한다. **채택 `NEAREST_TIDE`(2026-09-30)** — 근거 `e0_spatial_correlation.csv` 직접 오차 0.11 psu(0~5km). 참고로 가막만 합성 양식장 기준 최근접은 `dtRecent` 여수 약 10km, 정선 남해-205-00 약 29km(근사 계산)다
  - **하구 영향 관측소** — 판정 정의 `grading.estuary_stations`(채택 2026-09-30: `[DT_0016]`). `NEAREST_TIDE`에서 최근접 염분 관측소가 이 목록에 들면 `provenance = NONE`, `none_reason = EXCLUDED_ZONE`, `alertable = false` — 값·거리는 저장한다. 목록 값은 `tide.stations`와 같은 관측소 코드(`DT_xxxx`)이고, `station_id`(`tide:DT_xxxx`, 5.3절)와는 원천 접두어를 뗀 코드로 대조한다. 품질 규칙 R1의 하구 예외(4.6절 — 정선·어장환경 정점, 미결, `common-core`)와 다른 목록이다
- **양식장 ↔ 원천 대응 — 축마다 `farm_readings` 한 행을 무엇으로 채우는가**

| 축 | 대응 규칙 | 설정 (판정 정의) |
| --- | --- | --- |
| 수온 | IDW 추정 (4.7절) | `interpolation.*` |
| 물때·풍속·기온·염분 | **가장 가까운 활성 관측소**(`STATION_INACTIVE` 아님)의 최신 관측. `distance_km`·`source_ref` 기록 | — |
| DO | **거리 한계 안에서 표층 유효값이 있는 가장 가까운 정선 정점.** 가장 가까운 정점에 유효값이 없으면 다음 정점으로 넘어간다. 한계 안에 없으면 `NONE`(`NO_INPUT`) | `grading.line_max_distance_km: 30`(채택 2026-09-30 — 합성 양식장 최근접 정선 정점 29.4km) |
| 클로로필a | 같은 방식 — 어장환경 정점의 **표층(`CHL_S`)** 최신 조사값 | `grading.fishery_max_distance_km: 10`(채택 2026-09-30 — 합성 양식장 최근접 어장환경 정점 1.2km) |
| 적조 | 양식장 좌표가 반경 안에 드는 해역(`areas`, 여럿 가능)의 세부 행 중, **유효 기간 안에서 `day_report`가 가장 최근인 속보**에서 **등급이 가장 높은** 행. 등급 순서는 `WARNING` > `ADVISORY` > `PRE_ADVISORY` > `UNKNOWN` > `NONE` > `NOT_GRADED` *(제안)* — `UNKNOWN`을 공식 등급 아래·`NONE` 위에 두는 것은 "밀도가 없다고 적조가 없는 것이 아니다"(v1.5 5.3절) 때문이다. 대응은 `bulletin_detail_areas`의 지점마다 정규화 키 → 해역(`area_aliases` → `areas`) → 양식장 좌표(v1.5 5.4절 매핑). 한 세부 행이 여러 해역에 대응할 수 있다 | `bulletin.current_window_days: 3`(채택 2026-09-30 — R1·R3 활황기 속보 간격 최대 3일, `red_tide_bulletin: 72`h와 일관) |

  - 적조 유효 기간 안에 대응 속보가 없으면 `value` 없음·`provenance = OFFICIAL`·`none_reason` 없음으로 두고, 축 상태는 정상적 침묵("새 속보 없음")이다 *(제안)*. `NONE`(신뢰 기준 밖)과 구분하기 위함이다
  - 가막만 합성 양식장은 최근접 정선 정점이 약 29km다(4.8절 염분 참고). DO 거리 한계는 이 거리를 알고 정해야 한다
- DO: 빈 값 레코드는 건너뛰고 마지막 유효값과 그 날짜를 쓴다. v1.5 4.7절은 인근 정점이 **2025-11 이후 DO 값이 비어 있다**고 적었으나, 빈 값 레코드 739행은 수온·염분·DO가 **모두** 빈 레코드라 "0m에서 DO만 빈 경우"는 따로 세지 않았다. **0m DO의 날짜별 유효 여부는 미확인** — I-4에서 B v2 원문으로 센다(4.9절 DO 신선도 임계의 선행 조건)
- **`source_ref` 형식** — "근거 보기"가 원천 행을 찾아가는 키. 축마다 고정한다: 수온 = `run_id` / 물때·풍속·기온·염분 = `station_id` / DO·클로로필 = `station_id@observed_at_utc`(조사·관측 시각, UTC ISO — 개정 14. 같은 날 여러 조사를 구분한다) / 적조 = `cod_news#seq`. `station_id`에 이미 `:`가 있어(`tide:DT_0016`) 구분자를 따로 둔다
- 인근 실측 축은 `obs.loaded`로, 수온은 `interp.done`으로 갱신한다. **두 경로는 서로 기다리지 않는다**
- 출력: `farm_readings`(5.3절) → `grade.done`

### ③-2 좌표 불량 양식장 (1.6절)

- **좌표 검증**: 이 모듈의 `common/geo/` 폐구간 검증을 통과하지 못한 양식장은 계산할 수 없으므로 전 축 `provenance = NONE`, `none_reason = INVALID_COORDS`(4.8절)

### ③-3 표층 규칙의 적용 (4.4절 — 정의의 주인은 `line`)

- 표층 = 캐스트 안의 **`wtr_dep == 0` 레코드**. 이 skill이 **읽을 때** `line.surface_rule`과 `line_observations.depth_m`으로 판별한다. 저장된 표층 표시 열은 없다
- **`line.surface_rule`이 정해지지 않은 설정이면**(채택값은 `INCLUDE`) DO는 값 없음·`provenance = NONE`·`none_reason = SURFACE_RULE_UNDECIDED`(P11)
- **0m 레코드가 없는 캐스트에는 표층값이 없다.** 가장 얕은 수심으로 대체하지 않는다. 그 정점이 표층 유효값을 못 주면 거리 한계 안의 다음 정점으로 넘어간다(③-1 대응 규칙, P14)
- **0m 레코드가 둘 이상인 캐스트**는 규칙이 없다(실측 0건). 만나면 추정하지 말고 멈춰 보고한다

### ③-4 설정 (7.7절 — 전부 판정 정의)

```yaml
bulletin.current_window_days: 3         # 적조 현재값 유효 기간 (4.8절) — 채택 2026-09-30
line.surface_rule: INCLUDE              # 0m = 표층 (4.4절) — 채택 2026-09-30
grading.p95_thresholds.water_temp: [1.0, 2.0, 3.0]
grading.salinity_mode: NEAREST_TIDE     # 영역 판정만: NEAREST_TIDE / NONE. 값은 항상 저장 (4.8절) — 채택 2026-09-30
grading.estuary_stations: [DT_0016]      # 염분 NEAREST_TIDE에서 NONE으로 돌릴 하구 영향 조위관측소 (4.8절). R1 하구 예외 아님
grading.chlorophyll_estimate_enabled: false  # 계산 여부. 표시 여부는 대시보드
grading.line_max_distance_km: 30         # DO 정점 거리 한계 (4.8절) — 채택 2026-09-30
grading.fishery_max_distance_km: 10      # 클로로필 정점 거리 한계 (4.8절) — 채택 2026-09-30
grading.excluded_zones:                  # 제외 구역 — 중심·반경 목록 (4.7·4.8절) — 채택 2026-09-30
  - {name: seomjin_estuary, center_lat: 35.00, center_lng: 127.73, radius_km: 15}
```

- 위 값은 계획서 개정 11(2026-10-01)에서 채택값으로 기록됐다. 남은 `<미결>`이 생기면 채우지 않는다. 코드는 **값이 바뀌어도 그대로 돌게** 짜고, 테스트는 설정에 상대적으로 짠다
- `grading.salinity_mode`는 `NEAREST_TIDE` / `NONE` **둘 다 구현**한다 — 어느 쪽으로 정해져도 값(최근접 실측·거리)은 저장된다
- `grading.chlorophyll_estimate_enabled`는 기본 `false`다 — 조사 기준 추정은 교차검증 전이라 계산하지 않는다

### ③-5 저장과 알림 (5.3·2.2절)

| 테이블 | 핵심 컬럼 | 비고 |
| --- | --- | --- |
| `farm_readings` | `farm_id`, `axis`, `value`, `lower`, `upper`, `unit`, `derivation`, `provenance`, `none_reason`(nullable), `validated_scope`(nullable), `grade`(nullable — 적조만), `alertable`, `source_ref`, `distance_km`, `observed_at_utc`, `computed_at_utc` | 현재값. PK (`farm_id`, `axis`). **`provenance = NONE`이어도 계산된 값은 비우지 않는다**(4.8절). `none_reason`은 `evaluation`의 입력 — 화면 사유는 `axis_status.reason` |
| `farm_reading_history` | 위 + `ts_utc` | 곡선용 시계열. 보존 기간 미결(11절). PK (`farm_id`, `axis`, `ts_utc`) |

| 주제 | 발행 | 소비 | 본문 |
| --- | --- | --- | --- |
| `grade.done` | grading | evaluation | `grade_run_id`, `axis`, `farm_ids` |

- `farm_readings`는 PK (`farm_id`, `axis`) upsert, `farm_reading_history`는 (`farm_id`, `axis`, `ts_utc`) — 같은 입력을 두 번 받아도 행이 늘지 않는다(멱등)
- `validated_scope`는 **계산값(수온)에만** `STATION_SITES`를 쓴다. 나머지 축은 비운다
- `grade`는 **적조 행에만** 채운다

---

### ③-6 적조 위험도 지수 (4.10절 전문 — 개정 20, 지시서 I-16)

v1.5 7.4절 설계 B(가중 합산 지수)를 이 모듈 범위에 넣는다(2026-10-02 팀 결정). **판정·값은 모듈, 표시는 대시보드** — 대시보드는 지수·단계를 다시 계산하지 않는다(5.5절). v1.5 7.5절에 따라 **정확도(적조 발생 예측력)는 평가하지 않는다** — 지수는 입력 축의 상태를 한 줄로 모은 것이다.

**계산 위치와 시점** — `grading` 안의 **파생 축** `red_tide_risk`. 새 이미지·큐 주제는 없다. 입력 축 4개(`red_tide`·`water_temp`·`salinity`·`chlorophyll`) 중 하나의 `farm_readings` 행을 쓴 뒤 **같은 양식장의 지수를 다시 계산**한다. 수온(`interp.done`)과 속보(`obs.loaded`)는 서로 기다리지 않으므로 **늦게 온 쪽에서 다시 계산**한다 — 입력은 언제나 그 시점의 `farm_readings` 현재값이다. 입력 축 행·지수 행(세 표)·두 축의 `farm_reading_history`를 **한 트랜잭션**에 쓰고, 커밋 뒤 축 `red_tide_risk`의 `grade.done`을 따로 한 건 낸다(메시지 하나에 축 하나 — 2.2절. `axis`는 문자열이라 계약 `queue-v1` 그대로). `obs.loaded`와 `interp.done`이 동시에 처리되면 한쪽이 다른 쪽의 커밋 전 값을 읽을 수 있다 — 그 차이는 **다음 입력 갱신에서 수렴**한다(지수는 현재값만 둔다). `axis_status`(evaluation 산출)는 읽지 않는다 — 단계 순서가 거꾸로 된다.

**항목** — 판정 정의 `risk_index.factors`(이름 고정 4개)

| `factor` | 입력 축 | 점수 규칙 (판정 정의 — 값은 11절) | 점수 범위 |
| --- | --- | --- | --- |
| `nearby_bulletin` | `red_tide` (4.8절 적조 현재값 — 반경 안 해역 대응 그대로) | 입력 `grade`별 점수표 `grade_scores`(`WARNING`·`ADVISORY`·`PRE_ADVISORY`·`UNKNOWN`·`NONE`·`NOT_GRADED`). **유효 기간 안 속보 없음 = OK, 점수 0** | 점 하나(`score_lower = score_upper = score`) |
| `water_temp_band` | `water_temp` (IDW) | 구간 목록 `bands`(`[min, max)` → 점수), 어느 구간에도 들지 않으면 0 | 입력 `lower`~`upper` 구간 위에서 점수의 최솟값·최댓값 |
| `salinity_band` | `salinity` (`dtRecent` 최근접 실측 — 화면 염분과 같은 행) | 구간 목록 `bands`, 밖이면 **0** | 입력에 범위가 없으면 점 하나 |
| `chlorophyll_level` | `chlorophyll` (어장환경 표층 조사값) | 비교 기준 대비 상승 규칙 `rule` — **구조 자체가 미결**(비교 대상·상승 기준·점수, 11절) | 점 하나 |

- 염분 입력의 기준은 v1.5 7.4절 주석("② 정선관측 기준선", `survey`)과 다르다 — 대시보드가 같은 기준을 요청했고(화면 염분 = 지수 입력) 모듈 염분 축이 이미 최근접 실측이기 때문이다. 입력 성격은 `realtime`
- 구간 경계: `min` 포함·`max` 미포함. 점수 범위는 구간 경계에서의 점수 변화를 반영한다(입력 범위가 구간 경계를 넘으면 두 구간 점수가 모두 후보)

**OK 항목** — 다음을 모두 만족하면 그 항목을 합산에 쓴다(`ok = true`)

1. 입력이 있다 — `water_temp_band`·`salinity_band`·`chlorophyll_level`은 입력 축 `farm_readings` 행에 `value`가 있다. **`nearby_bulletin`은 `value`(밀도)를 보지 않는다** — 입력 축 행에 `grade`가 있거나(`UNKNOWN`·`NOT_GRADED`처럼 밀도가 없는 행 포함), "유효 기간 안 속보 없음"(값·`grade` 없음, `provenance = OFFICIAL`, 4.8절)이면 OK. 적조 행 자체가 없으면 `NO_INPUT`
2. 입력 축 `provenance ≠ NONE`
3. 입력의 원천 관측 행 `flags`에 `SENSOR_QUALITY`가 없다 — 찾는 법: `chlorophyll_level`은 `survey_observations`(정점 = `source_ref`의 `station_id`, `observed_at_utc`, 층 표층, metric 클로로필), `salinity_band`는 `observations`(관측소 = `source_ref`, 입력 행 `observed_at_utc`, metric 염분). `water_temp_band`·`nearby_bulletin`은 **해당 없음(통과)** — 수온은 IDW 입력 단계에서 품질 플래그 관측이 이미 빠지고(4.7절), 속보 행에는 품질 플래그가 없다
4. 그 항목의 점수 규칙이 `<미결>`이 아니다 *(제안)*

OK가 아니면 **제외 항목** — `excluded_reason`: `NO_INPUT`(입력 행·값 없음) / `INPUT_NONE`(입력 `provenance = NONE`, 입력 `none_reason`을 `input_none_reason`에 옮김) / `SENSOR_QUALITY` / `RULE_UNDECIDED`(점수 규칙 미결 *(제안)*). 판정 순서는 이 나열 순서다.

**합산**

| 값 | 정의 |
| --- | --- |
| 기여도 `contribution` | `weight` × `score`. 제외 항목은 **0** |
| 지수 `value` | 기여도의 합 — **네 행의 기여도 합 = `value`**(저장 값, 반올림하지 않는다) |
| 지수 `lower` | Σ(OK 항목) `weight` × `score_lower` |
| 지수 `upper` | Σ(OK 항목) `weight` × `score_upper` **+ Σ(제외 항목) `weight`** — 빠진 항목은 0~1 어디든 될 수 있다는 불확실성을 범위에 넣는다(2026-10-02 사용자 결정). 재정규화하지 않는다 |
| `provenance` | OK 항목 수 ≥ `risk_index.quality_gate.min_factors_ok` → `INTERPOLATED`, 미만 → `NONE`(`none_reason = INSUFFICIENT_FACTORS`) |
| `derivation` · `alertable` | `COMPUTED` · **항상 `false`**(불변식, 4.8절) |
| `observed_at_utc` | OK 항목 입력의 `observed_at_utc` 중 **가장 이른 값**(값이 없는 항목은 빼고) *(제안)*. 모두 없으면 `NULL` |
| `source_ref` · `validated_scope` · `grade` · `unit` · `distance_km` | 모두 `NULL` — 근거는 `risk_index_factors.source_ref`, 지수는 교차검증 대상이 아니고, `grade`는 적조 공식 등급 전용이다 |

- `provenance = NONE`이어도 계산할 수 있었던 `value`·`lower`·`upper`·단계는 저장한다(4.8절 불변식)
- **판정 정의가 `<미결>`일 때** *(제안)* — 계산할 수 있는 만큼 저장한다(4.8절 불변식)
  - ① **가중치(`weight`) 중 하나라도 미결** → 합산 자체가 불가능하다. 지수 행은 `value`·`lower`·`upper` 없음, `provenance = NONE`, `none_reason = RULE_UNDECIDED`. `risk_index_factors`·`risk_index_levels`에는 쓰지 않고 그 양식장의 기존 행은 지운다(옛 규칙의 분해가 남지 않게)
  - ② **항목 점수 규칙만 미결** → 그 항목만 `RULE_UNDECIDED`로 제외(OK 조건 4), 지수는 계산한다
  - ③ **품질 하한(`min_factors_ok`) 미결** → `value`·`lower`·`upper`·분해는 저장하고 `provenance = NONE`, `none_reason = RULE_UNDECIDED`(하한이 없으면 신뢰 기준을 정할 수 없다)
  - ④ **단계(`levels`) 미결** → `value`·분해는 저장, `risk_index_levels` 행만 쓰지 않는다(기존 행은 지운다). `provenance`는 ③에 따른다
  - 적용 순서: ① → (②·③·④ 각각). `none_reason`이 둘 이상 해당하면 `INVALID_COORDS` > `RULE_UNDECIDED` > `INSUFFICIENT_FACTORS` 순으로 하나를 쓴다
- **좌표 불량 양식장**(1.6절 — 양식장 좌표 검증 실패)이면 지수도 `provenance = NONE`, `none_reason = INVALID_COORDS`로 둔다(다른 축과 같은 사유) *(제안)*. 판정 근거는 양식장 좌표 검증 결과다 — 입력 축 행으로 판단하지 않는다(좌표 불량 양식장은 IDW가 건너뛰어 수온 행이 아예 없다). 가중치가 정해져 있으면 계산할 수 있었던 `value`·`lower`·`upper`·분해는 그대로 저장한다
- **판정 정의 값의 전제** — 값이 정해지면 `grading` 기동 시 검사로 확인하고 어기면 멈춘다: 점수 ∈ [0, 1], Σ`weight` = 1, `levels`의 첫 `min` ≤ 0(모든 값에 단계가 있다). 그래서 `value`·`lower`·`upper` ∈ [0, 1]이다. 미결 값은 검사하지 않는다(채우지 않는다)

**단계** — 판정 정의 `risk_index.levels`(오름차순 `{code, min}` 목록, 값·코드 이름 미결). 값 x의 단계 = `min ≤ x`인 것 중 `min`이 가장 큰 코드(경계값은 위 단계). `value`의 단계를 `level`에, `lower`·`upper`의 단계를 `level_at_lower`·`level_at_upper`에 둔다 *(제안 — 대시보드 확인 중. 대시보드가 요청한 것은 걸침 여부)*. `level_straddle = (level_at_lower ≠ level_at_upper)`. 웹이 `value`를 잘라 단계를 만들면 판정을 다시 하는 것이 되므로 모듈이 넣는다.

**저장** (5.3절) — `farm_readings` 축 `red_tide_risk` 한 행(이력은 기존 `farm_reading_history`에 합산값만) + `risk_index_factors`(양식장 × 항목 4행, 현재값만) + `risk_index_levels`(양식장당 한 행, 현재값만). 세 표는 같은 트랜잭션에서 쓴다.

**축 상태** (4.9절) — `axis_status`에 축 `red_tide_risk`: `provenance = NONE` → `NOT_USABLE`(`reason` = `none_reason`), 산출 지연 → `GRADING_STALE`(**4.9절 기준 그대로** — 정기 경로 적재 뒤 이 축의 `farm_readings`가 한계 안에 갱신되지 않음), 그 밖 → `NORMAL`. **이 축에는 수집 원천 대응이 없다** — 커버리지·계절·원천·호출 문제(3번 묶음)·신선도 판정을 적용하지 않고, sweep은 이 축에서 산출 지연만 본다. **입력 축 상태 중 가장 나쁜 것을 옮기지 않는다** — 항목 하나가 `STALE`이어도 지수는 계산된다(OK 판정이 본다). 새 신선도 임계·새 상태 값은 없다. 커버리지·계절 선언(`axis_coverage`)은 이 축에 두지 않는다.

**설정** (2.0.6절) — `risk_index.*`는 전부 **판정 정의**(`config/definitions.yaml`, 게이트 기준 문서와 같은 커밋). 값이 정해지기 전에는 `<미결>`이고, 검사는 **시험용 판정 정의**(테스트 안에서만 주는 값)로 임계 상대로 짠다. v1.5 원안 값(가중치 0.40·0.30·0.15·0.15, 수온 구간 22/24/27, 염분 32~33 → 0.5, `min_factors_ok: 2`)은 채택 전이다(11절)

| 키 | 내용 |
| --- | --- |
| `risk_index.factors.<factor>.weight` | 가중치 |
| `risk_index.factors.nearby_bulletin.grade_scores` | 등급별 점수 |
| `risk_index.factors.water_temp_band.bands` · `salinity_band.bands` | 구간 목록 |
| `risk_index.factors.chlorophyll_level.rule` | 상승 규칙 — 구조 미결 |
| `risk_index.quality_gate.min_factors_ok` | OK 항목 수 하한 |
| `risk_index.levels` | 단계 경계·코드 |

## ④ 이식 출처 (6.3절)

| 새 경로 | 검증 코드 위치 | 처리 |
| --- | --- | --- |
| `grading/` | — | **신규** — 규칙은 4.8절(③-1)이 기준. 검증 코드 없음 |

- 참고: 등급 임계(1.0 / 2.0 / 3.0℃)는 데이터가 아니라 **밴드 폭에서 유도**한 값이다(v1.5 4.6.1절). 실측 오차를 보고 임계를 옮기지 않는다

---

## ⑤ 함정

- **`provenance`가 `OBSERVED`여도 계산값은 발송하지 않는다.** 오차 기준으로 높은 등급을 받는 것과 발송 자격은 별개다 — v1.5가 풀지 못했던 모순을 두 축으로 나눈 이유다. `derivation = COMPUTED` → `alertable = false`(N11, 불변식)
- **`provenance = NONE`이라고 값을 버리지 않는다.** `NONE`은 "신뢰 기준 밖"이다. 계산했으면 `value`·`lower`·`upper`를 저장한다
- **적조 현재값이 없을 때는 `NONE`이 아니다.** 유효 기간 안 속보가 없으면 `value` 없음·`provenance = OFFICIAL`이다 *(제안)* — 적조가 없다는 것과 판정을 못 믿는다는 것은 다르다
- **해역 없는 속보로 행을 만들지 않는다.** 대응할 양식장이 없다 — `alertable`도 매겨지지 않는다
- **적조 대응은 `bulletin_detail_areas`의 모든 지점을 쓴다.** 첫 지점만 쓰면 "및"·"~"로 이어진 나머지 해역의 양식장이 빠진다
- **추정이 멈췄을 때 최근접 관측값을 수온에 넣지 않는다.** 수온 행은 `interp.done`으로만 갱신된다. 멈춤은 `evaluation`이 드러낸다(P3)
- **배지를 `provenance`에서 끌어내지 않는다** — 이 skill은 배지를 만들지 않는다. `OBSERVED`·`NEAREST` 수준의 추정값이 실측처럼 보이게 되는 사고를 막는 것은 대시보드 계약 W1이다
- **표층 대체 금지.** 0m가 없으면 가장 얕은 수심이 아니라 **다음 정점**이다
- **염분을 IDW로 추정하지 않는다.** 염분은 최근접 실측이다 — IDW 염분 P95는 7.55 psu다
- **`alertable`에 신선도를 넣지 않는다.** 이 단계는 새 관측이 올 때만 돌아서, 계산 시점에 신선했던 값이 나중에 오래돼도 판정이 바뀌지 않는다. 신선도는 `evaluation`의 `axis_status`가 담고, 대시보드가 둘을 함께 본다(5.5절 W5)
- **두 경로를 서로 기다리게 하지 않는다.** 수온(`interp.done`)이 늦어도 인근 실측 축은 `obs.loaded`로 갱신된다

---

## ⑥ 검사와 기대값

| # | 검사 | 통과 기준 |
| --- | --- | --- |
| P4 | 오차 P95 0.8 / 1.6 / 2.6 / 3.4 입력 | 차례로 `OBSERVED` / `NEAREST` / `INTERPOLATED` / **`NONE`**(`none_reason = ERROR_ABOVE_LIMIT`)(4.8절). 모든 경우 `value`·`lower`·`upper`가 저장됨 |
| P5 | 적조 공식 속보 (코클로디니움 주의보) / Scrippsiella 20,000 / 원인생물 결측 속보 / 해역 없는 속보 | 첫째 `OFFICIAL`·`alertable=true`, 둘째 `NOT_GRADED`·`alertable=false`, 셋째 `UNKNOWN`·`alertable=true`(등급 없음), 넷째 `bulletins`에 저장되고 `farm_readings` 변화 **0건** |
| P11 | DO 표층 규칙 미결 설정 | DO `provenance = NONE`, `none_reason = SURFACE_RULE_UNDECIDED`, `axis_status.state = NOT_USABLE`·`reason`도 같음 |
| P13 | 적조 현재값 — (a) 같은 해역에 `day_report`가 다른 속보 둘, 최신 속보에 세부 행 둘(주의보·예비특보), 유효 기간 밖 속보 하나 (b) 최신 속보의 세부 행이 `NOT_GRADED`·`UNKNOWN` (c) 유효 기간 안 대응 속보 없음 | (a) 최신 속보의 **주의보** 행이 현재값, 유효 기간 밖 속보는 쓰지 않는다 (b) `UNKNOWN` 행이 현재값 (c) `value` 없음·`provenance = OFFICIAL`·축 상태 정상적 침묵 *(제안 — 4.8절)*. 기간은 설정에 상대적으로 둔다 |
| P14 | DO 정점 선택 — 최근접 정점은 유효값 없음, 두 번째 정점은 한계 안·유효값 있음 / 한계 안에 유효값 정점 없음 | 앞은 두 번째 정점 값, 뒤는 `NONE`(`NO_INPUT`). 거리 한계는 설정에 상대적으로 둔다 |
| N11 | **전 픽스처 결과 전체** | `derivation = COMPUTED`이고 `alertable = true`인 행이 **0건** |

- 전부 **합성 입력**이다(`fixtures/synthetic/farms.csv` 등). 거리 한계·유효 기간 같은 `<미결>` 값은 **설정에 상대적으로** 짠다
- 관련 검사(다른 skill 소유): 아래 둘은 이 skill의 출력을 보지만 A.3상 `evaluation`(S10)에 배정돼 있다

| # | 검사 | 통과 기준 |
| --- | --- | --- |
| P7 | 좌표 불량 합성 양식장 (위도 32.5, 경도 140) | 전 축 `provenance = NONE`, `none_reason = INVALID_COORDS`, `axis_status.state = NOT_USABLE`·`reason`도 같음 |
| P8 | 섬진강하구 제외 구역 안 합성 양식장 | 수온 `provenance = NONE`, `none_reason = EXCLUDED_ZONE`, `axis_status.state = NOT_USABLE`이고 `value`는 저장됨, 인근 실측 축은 정상 산출 |

---
- **K1~K9 (7.5절, 개정 20)** — 적조 위험도 지수: K1 품질 하한 직전·직후, K2 제외 사유 3종과 `upper` 상향, K3 수온 추정 정지 시 대체 없음, K4 갱신 순서 두 가지의 같은 결과, K5 기여도 합 = `value`·분해 4행·`alertable = false`, K6 단계 경계·걸침, K7 규칙 `<미결>` 네 경우 *(제안)*, K8 적조 입력 `UNKNOWN`·`NOT_GRADED`·속보 없음·행 없음, K9 판정 정의 전제 위반 기동 멈춤. 임계·경계는 시험용 판정 정의로 상대적으로 짠다

## ⑦ 주인이 아닌 사실 — 참조만

| 사실 | 주인 |
| --- | --- |
| 필드 의미 전체(`derivation`·`provenance`·`alertable`·`grade`·`source_ref` 등) | `CLAUDE.md` 6절 |
| 양식장 좌표 읽기, 좌표 검증, 거리 계산 | `common-core` |
| IDW 추정, 오늘의 오차, `station_set_key` | `interpolation` |
| 적조 판정 순서, `UNKNOWN`·`NOT_GRADED`, 해역 없는 속보 | `bulletin` |
| 표층 규칙의 정의, 0m DO | `line` |
| `none_reason` → `axis_status.reason`, 신선도·추정 지연·산출 지연 | `evaluation` |

이 skill이 **주인인 사실**(A.3): 양식장 ↔ 원천 대응 규칙(적조 등급 순서 포함), `none_reason` 값 목록, 표층 규칙의 **적용**.

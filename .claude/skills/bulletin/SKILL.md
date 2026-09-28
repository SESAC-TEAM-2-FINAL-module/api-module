---
name: bulletin
description: "적조정보(redtideList) 수집·가공 어댑터 — src/api_module/collector/adapters/bulletin/ 와 processor/adapters/bulletin/ 를 만들거나 고칠 때 쓴다 (지시서 I-3). outer·item2 두 층 보관(item2 없는 속보 포함), 적조 등급 판정 순서(UNKNOWN·NOT_GRADED·공식 4단계), txt_seas 정규화·지점 분리(bulletin_detail_areas)와 검토 큐(unmapped_locations), 분할 수집, 시드 파일 형식과 적재 코드. 양식장별 적조 현재값 선택·alertable(grading), 계절 밖 판정(evaluation) 작업에는 쓰지 않는다."
---

# bulletin

국립수산과학원 적조정보 `redtideList`를 수집하고, 속보를 두 층(outer 속보 · `item2` 세부 행)으로 저장하며 등급을 판정한다. 공용 용어(상태 이름, 필드 의미 — `grade` 포함, `_utc` 규칙)는 `CLAUDE.md` 6절에 있다. 괄호 속 "N절"은 계획서의 절이다.

---

## ① 범위

| 경로 | 이 skill이 만드는 것 |
| --- | --- |
| `collector/adapters/bulletin/` | 최근 14일 창 호출, 원문 저장 요청. `collector-bulletin` 명령에 **등록**. `collector-completeness`용 **분할 수집**(같은 창을 월 분할) |
| `processor/adapters/bulletin/` | outer·`item2` 해석 → `bulletins`·`bulletin_details`·`bulletin_detail_areas` 행, **등급 판정**, `txt_seas` 정규화·지점 분리, 검토 큐(`unmapped_locations`) 적재. `processor/main.py`에 **등록** |
| 시드 | `area_aliases`·`areas`·`axis_coverage`의 **파일 형식과 적재 코드** — 내용은 미결(⑧) |

**만들지 않는 것**

- 호출층·응답 해석·원문 저장·분할 합산 **비교** → `common-core`
- 양식장별 적조 현재값 선택(유효 기간·등급 순서), `farm_readings` 적조 행, `alertable` → `grading`
- 계절 밖·커버리지 밖 판정, 적조 신선도(마지막 성공 호출 기준) → `evaluation`
- 화면 문구("속보 발생", "해역 미상 속보")와 발송 시점 → 대시보드(5.5절 W5·W6)

---

## ② 원천 절 (계획서)

1.1(`redtideList` 행) · 1.3 · 2.1(`collector-bulletin`·`collector-completeness`) · 3.3(분할 합산) · 4.2 · 4.3 · 5.3(`bulletins`·`bulletin_details`·`bulletin_detail_areas`·`unmapped_locations`·`area_aliases`·`areas`·`axis_coverage`) · 6.3(bulletin 행) · 8절

---

## ③ 사실

### ③-1 API (1.1·1.3절)

| 축 | API | 기관 | 엔드포인트 | 키 | 형식 | 페이징 | 수집 주기 (워크로드 권장값) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 적조 | 적조정보 `redtideList` | 국립수산과학원 | `https://www.nifs.go.kr/OpenAPI_json` (→ `/api/OpenAPI_json` 리다이렉트) | `NIFS_KEY_BULLETIN` | JSON | **없음** (`pageNo` 무시) | 1시간 (시즌 외 6시간) |

| 항목 | 사양 |
| --- | --- |
| 요청 | `id=redtideList&key=…&sdate=yyyyMMdd&edate=yyyyMMdd` |
| 구조 | outer `cod_news`·`day_report`·`item2` / `item2` 내부 `nam_biology`·`txt_seas`·`min/max_density`·`min/max_watertemp`·`min/max_salt` |
| 날짜 | **`day_report`와 `cod_news` 앞 8자리 둘 다 저장.** 명세의 `rdate`는 실응답에 없다 |
| `item2` | **없는 속보가 있다**(20250924-001). outer 기준으로 1행 보관 |
| 해역 | `txt_seas`는 **`item2` 내부**, 텍스트. 정규화 규칙은 4.3절 |
| 수록 범위 | **공식 특보 발표는 수록되지 않는다**(2건 모두 미수록). `day_report`당 1건만 제공되는 정황 → 이 API는 **속보 축** |
| 결측 | 밀도 `0`과 빈 값을 구분해 저장. 판정 규칙은 4.2절 |

- 키는 **nifs.go.kr 자체 키** `NIFS_KEY_BULLETIN`이다. data.go.kr 키와 호환되지 않는다. 키 파라미터명은 `key` — 쿼리에 들어가므로 `final_url`까지 마스킹된다(`common-core`)
- 요청주소는 `.env` 값을 그대로 쓴다. `/OpenAPI_json` → `/api/OpenAPI_json`으로 **리다이렉트**된다 — egress 허용 목록에 둘 다 필요하다

### ③-2 수집 (2.1·3.3·8절)

- 워크로드 `collector-bulletin` — CronJob 1시간, 적조 시즌 외 6시간(워크로드 설정). **최근 14일 창**. 호출 예산은 하루 24회
- **페이징이 없다** — `pageNo`는 무시되고 `header`에 `totalCount`가 없다. 그래서 완전성은 **분할 합산**으로 본다: `collector-completeness`(주 1회)가 같은 창을 월 분할로 받아 `tag = completeness` 원문을 남기고, 합산 비교는 `common-core`의 `processor/completeness/`가 한다. **비교 범위를 먼저 맞춘다**(N12)
- 적조 시즌은 **시드 `axis_coverage.season_months`**에만 있다 — 계절 밖 판정(`evaluation`)의 유일한 원천이다. 설정 키는 없다. 수집 주기 전환(시즌 1시간 / 비시즌 6시간)은 워크로드 설정이며, `HANDOFF.md` 권장 스케줄을 시드의 계절과 **같은 달로** 맞춘다

### ③-3 저장 — 두 층과 지점 (4.2·4.3·5.3절)

| 테이블 | 핵심 컬럼 | 비고 |
| --- | --- | --- |
| `bulletins` | `cod_news`(PK), `day_report`, `detail_count`, `grade`(nullable), `raw_id` | `item2` 없는 속보도 1행. `grade`는 **`item2` 없는 속보에만** 채운다(`UNKNOWN`, 4.2절). 나머지는 `bulletin_details.grade` |
| `bulletin_details` | `cod_news`, `seq`, `nam_biology`, `species_class`, `txt_seas_raw`, `txt_seas_key`, `min/max_density`, `grade` | `grade`는 `NOT_GRADED`·`UNKNOWN` 포함. `species_class`는 `TARGET`/`NON_TARGET`/`MISSING`(4.2절). `txt_seas_key`는 분리 전 정규화 문자열(4.3절). PK (`cod_news`, `seq`) |
| `bulletin_detail_areas` | `cod_news`, `seq`, `part_no`, `area_key`, `area_id`(nullable) | 4.3절 4~5단계로 나뉜 **지점마다 1행**. PK (`cod_news`, `seq`, `part_no`). `area_id`는 별칭으로 해역이 정해진 경우만 — 비면 `unmapped_locations`에도 있다 |
| `unmapped_locations` | `area_key`(PK), `kind`, `raw_sample`, `occurrence_count`, `first_seen_utc`, `last_seen_utc`, `resolved_at_utc`(nullable) | 검토 큐(4.3절). `kind`는 `PARSE_FAILED`/`OUT_OF_SCOPE` — 코드 상수로 검사 |
| `area_aliases` | `alias_key`, `area_id`, `source` | 정규화 별칭 테이블. PK `alias_key` — 별칭 하나는 해역 하나로 간다. 광역 해역은 `areas`에 그 자체로 한 행 |
| `areas` | `area_id`, `name`, `center_lat`, `center_lng`, `radius_km` | 적조 해역 → 양식장 대응 기준 (시드). PK `area_id` |
| `axis_coverage` | `area_id`, `axis`, `covered`, `season_months`, `reason` | 커버리지 밖·계절 밖 **선언** (시드). v1.5 13절 `zone_axis_coverage` 대응. 4.9절. PK (`area_id`, `axis`). **`season_months`가 계절 밖 판정의 유일한 원천**이다 |

- **outer 1속보 = `bulletins` 1행**이다. `item2`가 없어도 행을 만든다(20250924-001). `item2` 행마다 `bulletin_details` 1행, 그 `txt_seas`가 나뉜 **지점마다 `bulletin_detail_areas` 1행**
- 날짜는 **`day_report`와 `cod_news` 앞 8자리를 둘 다** 저장한다. 명세의 `rdate`는 실응답에 없다
- 밀도는 **`0`과 빈 값을 구분**해 저장한다 — 등급 판정 4단계에서 둘 다 `UNKNOWN`이지만 원자료는 다르다

### ③-4 등급 판정 (4.2절)

- 출력: `bulletins`(outer 1행) + `bulletin_details`(`item2` 행)
- **등급** — 판정 순서
  1. `item2`가 없다 → `UNKNOWN` (outer 행에 기록 — 5.3절 `bulletins.grade`)
  2. `nam_biology`가 빈 값 → `UNKNOWN`
  3. `nam_biology`가 `Cochlodinium polykrikoides` 또는 개정 학명 `Margalefidinium polykrikoides`(대소문자·공백 무시, 앞부분 일치)가 아니다 → `NOT_GRADED`
  4. `max_density`가 0 또는 결측 → `UNKNOWN` (v1.5 5.3절 — `NONE`이 아니다)
  5. `max_density` 기준 공식 4단계
- `UNKNOWN`은 **발송 자격이 있고**(`alertable = true`), `NOT_GRADED`는 없다 (v1.5 5.3절, 충족계획서 3.2절) — 4.8절. 발송 문구("속보 발생")와 시점은 대시보드(5.5절 W5). 단 **해역 없는 속보**는 대응 양식장이 없어 `farm_readings` 행이 생기지 않으므로 **`alertable`이 매겨지지 않는다**(4.8절)
- 등급 기준값(10 / 100 / 1,000 개체/mL)은 설정 파일에 두고 코드에 박지 않는다
- **`bulletin_details.species_class`**는 위 판정 순서의 2·3단계 결과를 그대로 남긴다 — `TARGET`(`bulletin.species_allow`와 일치) / `NON_TARGET`(일치하지 않음) / `MISSING`(`nam_biology` 빈 값). DB `ENUM`을 쓰지 않고 코드 상수로 검사한다

- 기준값은 판정 정의 **`bulletin.grade_thresholds`**(현재 `[10, 100, 1000]`), 대상 종은 **`bulletin.species_allow`**(현재 `[Cochlodinium polykrikoides, Margalefidinium polykrikoides]`)에서 읽는다. 둘 다 `config/definitions.yaml` — 코드에 박지 않는다
- 등급 값의 이름과 뜻은 `CLAUDE.md` 6절(`grade` 필드)에 있다. 이 skill이 정하는 것은 **기준값과의 대응**이다: 10 미만 → `NONE`, 10~99 → `PRE_ADVISORY`, 100~999 → `ADVISORY`, 1,000 이상 → `WARNING`
- **비대상 종에 자체 등급을 만들지 않는다** — `NOT_GRADED` 저장까지만. 비대상 종을 화면에 어떻게 보일지는 대시보드·팀 결정이다(11절)

### ③-5 `txt_seas` 정규화 (4.3절)

| 단계 | 처리 | 사례 |
| --- | --- | --- |
| 1 | `strip()` — 공백·CR·LF | `"경남 남해군 미조~상주면\r\n"` |
| 2 | 별칭 테이블 (오타 포함) | `"충천남도"` → 충청남도 |
| 3 | 시도명 약칭·"해역" 접미 정규화 | `"충청남도 천수만"` = `"충남 천수만 해역"` |
| 4 | **"및" 분리** | `"충남 서산 창리 및 태안 황도 해역"` |
| 5 | **"~" 구간 → 양 끝 지점** | `"경남 남해군 미조~상주"` |

- **원문(`txt_seas_raw`)과 정규화본을 둘 다 저장.** 정규화 키로 비교하고 원문은 표시·감사용
- **정규화 키의 저장 위치**: 1~3단계를 거친 문자열(분리 전)은 `bulletin_details.txt_seas_key`에, 4~5단계로 **나뉜 지점마다 1행**을 `bulletin_detail_areas`에 둔다. "및"은 나뉜 수만큼, "~" 구간은 양 끝 두 지점이다. 해역 대응(4.8절)은 `bulletin_detail_areas`의 모든 행을 쓴다 — 첫 지점만 쓰지 않는다
- 매핑되지 않은 문자열은 **검토 큐**(`unmapped_locations`, 5.3절)로 (v1.5 5.4절). 두 종류로 나눈다 — `PARSE_FAILED`(미등록 문구: 별칭 등록 대상) / `OUT_OF_SCOPE`(해석했으나 관심 구역 밖, 예: 서해: 통계로만). 같은 정규화 키가 다시 나오면 행을 늘리지 않고 횟수·마지막 시각만 갱신한다. 별칭을 등록해 해소되면 `resolved_at_utc`를 채운다

- 정규화는 **이 skill의 순수 함수**로 둔다. 비교는 정규화 키로 하고 DB 콜레이션에 맡기지 않는다(`CLAUDE.md` 3절)
- `txt_seas`는 **`item2` 안에 있다.** outer에서 찾으면 빈 값이 나온다 — 그래서 `item2` 없는 속보는 해역이 없다

### ③-6 시드 (5.3절, A.6)

- `area_aliases`(정규화 별칭), `areas`(해역 중심·반경 — 적조 해역 → 양식장 대응 기준), `axis_coverage`(해역 × 축의 커버리지·계절 **선언** — 적조 계절 포함)의 **파일 형식과 적재 코드**를 만든다
- **내용은 미결이다**(11절) — 해역 목록·중심·반경, 선언, 초기 별칭을 추정해 채우지 않는다. 합성 검사(P13 등)는 합성 시드를 쓴다. 실데이터 대응은 S12 전에 내용이 확정돼야 돈다

---

## ④ 이식 출처와 사용 금지 (6.3절)

검증 폴더는 별칭으로만 부르고 **읽기만** 한다. 이식할 때마다 `docs/SOURCES.md`에 `새 경로 | 출처 파일::함수 | 출처 파일 SHA-256 | 바꾼 점`을 남긴다.

| 새 경로 | 검증 코드 위치 | 처리 | 이식 시 반드시 바꿀 것 |
| --- | --- | --- | --- |
| `processor/adapters/bulletin/` (수집부는 `collector/`) | `$SRC_API/verify_nifs_api.py` 적조 중첩 처리(`nested_items`) | 참고 | 날짜 필드 `rdate` → **`day_report`**로 |
| | `$SRC_API/probe_followup.py` `probe_redtide()` 평탄화 | **사용 금지** | **`item2` 없는 속보를 버림** (51 → 50) |
| | `txt_seas` 정규화 · 종 판정 | 신규 | 검증 코드 없음. 규칙은 ③-4·③-5 |

---

## ⑤ 함정

- **`item2` 없는 속보가 있다.** `item2`를 펼쳐서만 저장하면 속보가 사라진다(1주차 스크립트가 51건을 50건으로 만든 결함)
- **`txt_seas`는 `item2` 안에 있다.** outer를 참조하면 빈 값을 받는다
- **날짜 필드는 명세의 `rdate`가 아니라 `day_report`다.** 필드명 불일치는 이 API 전반의 문제다
- **`cod_news` 앞 8자리와 `day_report`가 다른 속보가 있다** — R1+R3에서 5건, 최대 14일 차이. 그래서 둘 다 저장한다
- **하루에 속보가 여럿(`-001`~`-003`)이어도 API는 `day_report`당 1건만 준다** — `-001`이 없는 날짜가 6개 있었다. 선택 기준은 제공기관 문의 대상이다. "하루 1건"을 누락으로 판정하지 않는다
- **공식 특보 발표는 이 API에 없다**(2024-08-02 코클로디니움 5해역, 2026-08-10 모두 미수록). 이 API는 **속보 축**이다. 특보가 없는 것을 수집 누락으로 보지 않는다
- **`txt_seas`에 CR·LF와 말단 공백이 섞여 온다**(`"경남 남해군 미조~상주면\r\n"`). 원문 오타도 있다(`"충천남도 천수만 해역"`) — 원문은 그대로 `txt_seas_raw`에 두고 정규화본만 고친다
- **"및"·"~"로 나뉘는 해역은 지점이 여럿이다.** 분리 전 문자열 하나로만 대응하거나 첫 지점만 쓰면 나머지 해역의 양식장이 빠진다 — R3 창에서 5건
- **같은 만이 날짜마다 다르게 표기된다**(`"충청남도 천수만"` / `"충남 천수만 해역"`)
- **비대상 종도 고밀도로 온다** — Scrippsiella 20,000, Chattonella 최대 3,345개체/mL. 종 필터 없이 밀도만 보면 "경보"가 된다
- **밀도 `0`·결측이 흔하다** — 1주차 50건 중 27건(54%). 등급 `NONE`이 아니라 `UNKNOWN`이다
- **진행상황 필드(`pstate`/`state`)는 응답에 없다**

---

## ⑥ 검사와 기대값

| # | 입력 | 통과 기준 |
| --- | --- | --- |
| F7 | A `redtideList` R1 창 | outer **51**, 세부 **50**, `item2` 없는 속보 **20250924-001** 1건 보관, 그 행 `bulletins.grade` = **`UNKNOWN`** |
| F8 | 같음 | 종: 코클로디니움 45 · Scrippsiella 2 · Akashiwo 2 · Mesodinium 1 / 등급(코클로디니움): 10~99 **10**, 100~999 **2**, 1000+ **1** |
| F9 | A `redtideList` R3 창 | 15건, Chattonella 10건 전부 `NOT_GRADED`. `bulletin_detail_areas` **20행** — "및"·"~"로 나뉘는 5건(20240731·0801·0807·0808·0809)은 각 2행, 나머지 10건은 각 1행 |
| F10 | R1 + R3 | 고유 `day_report` **66**, `txt_seas` 정규화 후 `"전남 여수"` 1종 |

| # | 입력 | 기대 |
| --- | --- | --- |
| N10 | `Margalefidinium polykrikoides`, 밀도 150 | 주의보 |

- 원문은 A 재검증의 `redtideList` R1·R3 창(`$SRC_API/output/raw/redtideList_r1_*`·`_r3_*`)이다(A.7절)
- 게이트 기대값(7.7절 `counts`): `redtide_r1: {outer: 51, details: 50, stored_bulletins: 51, cochlodinium: 45, item2_missing_unknown: 1}`, `redtide_r3: {outer: 15, not_graded: 10, detail_area_parts: 20}`, `redtide_all: {unique_day_report: 66}`
- 관련 검사(다른 skill 소유): N12·N13(분할 합산) — `common-core` / P5·P13(발송 자격·적조 현재값) — `grading` / P15(적조 신선도) — `evaluation`

---

## ⑦ 주인이 아닌 사실 — 참조만

| 사실 | 주인 |
| --- | --- |
| 상태 이름표, `grade` 필드 의미, `_utc` 규칙 | `CLAUDE.md` 6절 |
| 호출층, 응답 해석, 원문 저장·키 마스킹, 분할 합산 비교 | `common-core` |
| 적조 현재값(유효 기간 `bulletin.current_window_days`·등급 순서), 해역 → 양식장 대응, `alertable` | `grading` |
| 계절 밖·커버리지 밖 판정, 적조 신선도 | `evaluation` |

이 skill이 **주인인 사실**: 적조 판정 순서, `UNKNOWN`·`NOT_GRADED`, 해역 없는 속보(A.3). `grading`은 이것을 참조만 한다.

---

## ⑧ 미결 — 값을 채우지 않는다

계획서 11절에 미결로 등록된 것이다. 12.1절 규칙대로 **추정해 채우지 않는다.** 형식과 코드만 만들고, 내용이 필요한 검사는 합성 입력으로 짠다.

| 항목 | 계획서의 상태 |
| --- | --- |
| **시드 내용** | `areas`의 해역 목록·중심·반경, `axis_coverage`의 선언(**적조 계절 포함**), `area_aliases`의 초기 별칭 — 11절 미결, S12 선행 조건. 정하는 순서: 별칭 → 해역 목록 → 커버리지 선언 → 계절 |

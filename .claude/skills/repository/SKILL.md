---
name: repository
description: "DB 접근 계층 — src/api_module/common/repository/(tables.py, base.py, sql.py, dialect.py)와 contracts/tables/의 PostgreSQL·MySQL DDL 생성본·해역 시드 적용 SQL 생성본을 만들거나 고칠 때 쓴다 (지시서 I-6). DB 중립 테이블 모델(SQLAlchemy 2.0), 방언 분기는 dialect.py 한 곳, 금지·대체 목록과 타입 규칙(시각은 초 단위), 테이블 키(= upsert 멱등 키), DB 연결 양식(.env.example에서 하나를 고름), DB 검사(고른 DB 필수, 두 DB 비교 선택). 마이그레이션·운영 스키마 적용, 원천별 정규화 규칙 작업에는 쓰지 않는다."
---

# repository

이 모듈이 쓰는 테이블을 **어느 DB에도 묶이지 않게** 정의하고, 그 정의로 PostgreSQL·MySQL DDL 두 벌을 생성해 **제안**한다. DB는 아직 확정되지 않았다 — 이중 설계로 확정 전의 시간을 사되, 실행은 사용자가 고른 DB 하나로 한다. 운영 DB에 스키마를 적용하거나 바꾸는 것은 DB 소유 측이다. 공용 용어(`_utc` 규칙 포함)는 `CLAUDE.md` 6절에 있다. 괄호 속 "N절"은 계획서의 절이다.

---

## ① 범위

| 경로 | 이 skill이 만드는 것 |
| --- | --- |
| `common/repository/tables.py` | SQLAlchemy 2.0 테이블 모델 — **DDL 생성과 기동 시 검사의 기준** |
| `common/repository/base.py` | 인터페이스 — `upsert_observations`, `insert_raw_index`, … 각 단계가 부르는 쓰기·읽기 |
| `common/repository/sql.py` | SQLAlchemy Core 구현 — 방언 무관 부분 |
| `common/repository/dialect.py` | **방언 분기는 여기만** — upsert, 대량 적재, DDL 생성, **해역 시드 적용 SQL 생성**(개정 19) |
| `contracts/tables/` | PostgreSQL·MySQL **DDL 생성본 두 벌**, **해역 시드 적용 SQL 생성본 두 벌**(`seeds_pg.sql`·`seeds_my.sql`, 개정 19) |
| `.env.example`의 DB 연결 양식 | 두 DB 양식을 **주석으로** 둔다(③-4). `.env.example` 파일 자체는 I-0이 만들고, 이 skill은 DB 부분의 내용을 맞춘다 |
| DB 검사 | 7.4절 (⑥). 고른 DB의 테스트 컨테이너 구성은 I-0 몫이다(10절 S1) |

**만들지 않는 것**

- **마이그레이션 코드, 운영 DB 스키마 적용** — DB 소유 측이 한다. 테이블이 없으면 기동이 멈추고 보고한다(`CLAUDE.md` 3절)
- 기동 시 테이블 검사의 **실행 코드**(`common/contract_check/`) → `common-core`. 이 skill은 그 검사가 기준으로 삼는 `tables.py`를 만든다
- 결과 테이블의 **의미 계약**(5.5절, `contracts/tables/`의 설명 문서) → `evaluation`. 이 skill은 같은 폴더의 **DDL 생성본과 해역 시드 적용 SQL 생성본**만 만든다. 시드 파일 형식·내용은 `bulletin`, 시드 읽기·빈 시드 기동 검사·`seed-check`는 `common-core`
- 원천별 정규화 규칙(어떤 행을 어떻게 만드는가) → 각 원천 skill. 이 skill은 받은 행을 저장한다
- 양식장 좌표 테이블(`farm_sites`) — **웹 서비스 소유**라 DDL을 생성하지 않는다(1.6절)

---

## ② 원천 절 (계획서)

2.0.2(DB 행) · 2.0.3(DB 테이블 계약) · 2.0.7(`.env`) · 5.1 · 5.2 · 5.3 · 5.4 · 7.4 · 7.7(게이트의 DB 검사) · 12절·12.1절(DB 규칙, 연결 문자열 취급)

---

## ③ 사실

### ③-1 원칙 (5.1·2.0.3절)

**v1.5 13절의 SQL은 MySQL 방언(`ENUM`, `AUTO_INCREMENT`)으로 쓰여 있고, v1.5 12.2절은 PostgreSQL을 권고한다.** 문서 안에서 이미 두 DB가 섞여 있다. 이 모듈은 **어느 쪽에도 묶이지 않는 테이블 정의**를 SQLAlchemy 2.0 모델로 작성하고, 여기서 **PostgreSQL·MySQL DDL 두 벌을 생성해 제안**한다(`contracts/tables/`). 운영 DB 적용과 마이그레이션은 DB 소유 측이 한다(2.0.3절). 13절 SQL은 이 생성본으로 대체를 제안한다.

- **DB 테이블 계약**: 이 모듈이 쓰는 테이블의 **정의를 제안**한다 — 계약 문서 + PostgreSQL·MySQL DDL 생성본 — **DB 소유 측**이 스키마를 만들고 바꾼다. 읽는 쪽은 스키마를 바꾸지 않는다

### ③-2 금지·대체 목록과 타입 규칙 (5.2절)

| 쓰지 않는 것 | 이유 | 대신 |
| --- | --- | --- |
| DB `ENUM` 타입 | PG는 별도 타입, MySQL은 컬럼 속성. 값을 추가할 때 두 DB의 변경 방식이 다르다 | `VARCHAR(n)` + **`CHECK` 제약** (MySQL 8.0.16+ 강제) 또는 코드 테이블 |
| `SERIAL` / `AUTO_INCREMENT` 직접 기술 | 방언 | SQLAlchemy `Identity()` / `autoincrement=True` |
| `JSONB` 연산자·GIN 인덱스 | MySQL에 없음 | `JSON` 컬럼은 **저장·통째 조회만.** 조회 조건이 되는 값은 정규 컬럼으로 뺀다 |
| 배열 타입 | MySQL에 없음 | 자식 테이블 |
| `ON CONFLICT` / `ON DUPLICATE KEY` 직접 기술 | 방언 | **`repository.upsert()` 한 곳**에서 방언 분기 |
| 부분 인덱스, `RETURNING` 의존 | MySQL 미지원 | 일반 인덱스, 재조회 |
| `TIMESTAMPTZ` 의존 | MySQL `DATETIME`은 시간대 없음 | **모든 시각을 UTC `DATETIME`(naive, 초 단위)으로 저장**, 애플리케이션에서 KST 변환. 컬럼명에 `_utc` 접미 |
| `LISTEN/NOTIFY`, 권고 잠금 | PG 전용 | 큐 사용 |
| 원문 본문을 `TEXT`에 저장 | **MySQL `TEXT`는 64KB.** `sooList` 1년 응답은 약 4MB | 객체 저장소 (2.3절). DB에는 색인만 |
| 대소문자·공백 무시 비교에 기댄 조회 | MySQL 기본 콜레이션은 대소문자 무시, 구형 콜레이션은 **뒤 공백 무시** | 비교는 **정규화 키 컬럼**으로만. 문자셋 `utf8mb4`, 콜레이션 `utf8mb4_0900_ai_ci`(NO PAD) 명시 |
| 식별자 길이 64자 초과 | MySQL 한계 | 테이블·인덱스·제약 이름 규칙 (SQLAlchemy `MetaData(naming_convention=…)`) |

**타입 규칙** — 열마다 정하지 않고 이 규칙을 적용한다. 규칙에서 벗어나는 열만 `tables.py`에 이유를 적고 보고한다

| 종류 | 타입 | 이유 |
| --- | --- | --- |
| 식별자·코드·상태 값 (관측소 ID, `api`, `metric`, `axis`, `state` 등) | `VARCHAR(64)` | MySQL 식별자 규칙(64자)과 맞춘다 |
| 정규화 키·원문 문자열 (`area_key`, `txt_seas_raw` 등) | `VARCHAR(255)` | 키로 쓰는 열은 MySQL 인덱스 길이 한계(`utf8mb4`) 안에 들어가야 한다 |
| 관측값·좌표·오차·가중치 | `DOUBLE` | 원천마다 자릿수가 달라 고정소수로 묶기 어렵다 |
| 개수·바이트 수 | `INTEGER` / `BIGINT` | |
| **시각** | **`DATETIME` 초 단위**(소수 자리 없음) — PostgreSQL은 `TIMESTAMP(0)` 시간대 없음 | 실측 갱신이 빨라도 수 분 단위라 초 미만은 의미가 없다. **초 미만은 버린다(절삭)** — 반올림하지 않는다. 두 DB에서 같은 값이 저장된다. 원문 파일의 `fetched_at`은 원래 정밀도 그대로 둔다(2.3절) |
| 날짜 | `DATE` | |
| 참/거짓 | `BOOLEAN` | MySQL은 `TINYINT(1)`로 생성된다 |
| JSON | `JSON` | 저장·통째 조회만 (위 표) |

**뒤 공백 문제는 우리 데이터에 실제로 있다.** `txt_seas`의 `"전남 여수"`와 `"전남 여수 "`가 별개로 세어졌던 사례다. PAD SPACE 콜레이션이면 DB가 둘을 같다고 판단해 버그를 숨긴다. 정규화 키로 비교하면 DB가 무엇이든 결과가 같다.

- **값 목록이 정해진 열**(`source_api`, `kind`, `species_class`, `grade`, `derivation`, `provenance`, `state` 등)은 `VARCHAR(n)` + **`CHECK` 제약**으로 만든다. 허용 값은 **코드 상수 한 곳**에서 가져와 모델과 제약을 함께 생성한다 — 계획서가 "코드 상수로 검사"라고 적은 곳(4.2·4.3절)도 DB 쪽은 이 방식이다

### ③-3 테이블과 키 (5.3절)

| 테이블 | 핵심 컬럼 | 비고 |
| --- | --- | --- |
| `raw_index` | `id`, `api`, `tag`, `storage_key`, `fetched_at_utc`, `http_status`, `body_sha256`, `body_bytes`, `precheck_code` | 본문은 객체 저장소. PK `id`, 고유 `storage_key`. **processor가 원문 메타로 쓴다**(2.3절). `api`는 **api_id**(`dtRecent`·`redtideList`·`sooList`·`femoSeaList`, 변형은 접미 `-watch`·`-backfill`. `-completeness`는 원문 키에만 — `raw_index`에 들어가지 않는다) — 수집 원천과의 대응은 `common/`의 대응표 한 곳(결정 D2) |
| `ingest_runs` | `id`, `raw_id`, `parser_version`, `status`, `result_code`, `total_count`, `item_count`, `format`, `format_mismatch`, `processed_at_utc` | `status`는 **응답 상태**(3.2절 — `OK`·`OK_EMPTY`·`PARSE_FAILURE` 등, 결정 D6). 재처리할 때마다 행 추가. PK `id`(대리 키), **고유 (`raw_id`, `parser_version`)** — 재처리는 파서를 고친 뒤 하므로 버전이 바뀐다. 같은 파서로 같은 원문을 다시 처리하면(중복 알림) 행을 늘리지 않는다 |
| `stations` | `id`, `source_api`, `name`, `lat`, `lng`, `sea_area`, `active` | **processor가 원문의 좌표로 upsert**한다(결정 D5 — 조위 위경도, 정선 십진도, 어장환경 도분초 변환). `active`는 `STATION_INACTIVE`(4.1절)로 갱신. `source_api`는 `VARCHAR`+`CHECK`. PK `id` = **`원천:원천키`** — 원천마다 관측소 코드 체계가 달라 겹치지 않게 한다. 예: `tide:DT_0016`, `line:` + `gru_nam`·`sln_cde`·`sta_cde`를 `-`로 이은 값, `fishery:` + `FISHERY`·`LOCATION_POINT`를 `-`로 이은 값. 모든 `station_id` 열이 이 형식을 쓴다 |
| `observations` | `station_id`, `observed_at_utc`, `metric`, `value`(nullable), `missing_reason`, `flags`, `raw_id` | PK (`station_id`, `observed_at_utc`, `metric`) |
| `line_observations` | 위 + `depth_m`, `cast_id`, `cast_rule_version`, `group_type` | PK에 `depth_m` 포함. 표층 표시 열은 두지 않는다 — 표층은 `grading`이 `line.surface_rule`과 `depth_m`으로 판별(4.4절) |
| `survey_observations` | `station_id`, `observed_at_utc`, `surveyed_on`, `layer`, `metric`, `value`, `missing_reason`, `flags`, `raw_id` | PK (`station_id`, `observed_at_utc`, `layer`, `metric`) — **조사 시각이 키**다(개정 14). 같은 날 여러 조사가 각각 남고, 모니터링의 시간축과 맞는다. `surveyed_on`(KST 조사일)은 조회용으로 남긴다. 원문의 완전 중복(같은 시각·같은 값)은 하나로 합쳐진다(7.7절 `loaded`). `flags`(JSON, nullable)는 R1·R2 `SENSOR_QUALITY` 저장용 — 다른 관측 테이블과 같은 형태(결정 D3) |
| `bulletins` | `cod_news`(PK), `day_report`, `detail_count`, `grade`(nullable), `raw_id` | `item2` 없는 속보도 1행. `grade`는 **`item2` 없는 속보에만** 채운다(`UNKNOWN`, 4.2절). 나머지는 `bulletin_details.grade` |
| `bulletin_details` | `cod_news`, `seq`, `nam_biology`, `species_class`, `txt_seas_raw`, `txt_seas_key`, `min/max_density`, `grade` | `grade`는 `NOT_GRADED`·`UNKNOWN` 포함. `species_class`는 `TARGET`/`NON_TARGET`/`MISSING`(4.2절). `txt_seas_key`는 분리 전 정규화 문자열(4.3절). PK (`cod_news`, `seq`) |
| `bulletin_detail_areas` | `cod_news`, `seq`, `part_no`, `area_key`, `area_id`(nullable) | 4.3절 4~5단계로 나뉜 **지점마다 1행**. PK (`cod_news`, `seq`, `part_no`). `area_id`는 별칭으로 해역이 정해진 경우만 — 비면 `unmapped_locations`에도 있다 |
| `unmapped_locations` | `area_key`(PK), `kind`, `raw_sample`, `occurrence_count`, `first_seen_utc`, `last_seen_utc`, `resolved_at_utc`(nullable) | 검토 큐(4.3절). `kind`는 `PARSE_FAILED`/`OUT_OF_SCOPE` — 코드 상수로 검사 |
| `area_aliases` | `alias_key`, `area_id`, `source` | 정규화 별칭 테이블. PK `alias_key` — 별칭 하나는 해역 하나로 간다. 광역 해역은 `areas`에 그 자체로 한 행. 시드 — 운영 적용은 DB 소유 측 — 계획서 4.3절, 개정 19 |
| `publication_checks` | 4.5절 | PK `raw_id` — 감시 호출 한 번 = 원문 하나 = 기록 하나 |
| `adapter_health` | `adapter`, `last_success_utc`, `last_failure_utc`, `consecutive_failures`, `retry_recovered` | `processor`가 원문을 해석한 뒤 기록한다. 갱신 규칙은 4.9절. PK `adapter` = 수집 원천(결정 D2). `retry_recovered`는 **정수(복구 횟수)** — 7.8절 Q6 "1 증가", v1.5 12절 "별도 카운터"(결정 D4) |
| `ops_events` | `id`, `event_type`, `api`, `detail(JSON)`, `occurred_at_utc` | `CAST_RULE_ASSUMPTION_BROKEN` 등. PK `id`(대리 키), **고유 키 없음** — 운영 이벤트 로그라 쌓이는 것이 정상이다. 중복 알림으로 같은 이벤트가 두 번 기록될 수 있고, 로그이므로 허용한다 |
| `completeness_checks` | `run_key`, `api`, `window_start`, `window_end`, `parts`, `single_count`, `split_sum`, `truncated_side`, `status`, `reason`, `checked_at_utc` | 분할 합산 결과 — **운영 기록**(결과 테이블 계약 밖). PK (`run_key`, `api`). `status`·`reason`·`truncated_side`는 `VARCHAR`+`CHECK`. 기동 시 검사에서 **processor만** 요구한다(`OPTIONAL_TABLES`, `check_schema(include=…)`) (개정 17) |
| `areas` | `area_id`, `name`, `center_lat`, `center_lng`, `radius_km` | 적조 해역 → 양식장 대응 기준 (시드 — 운영 적용은 DB 소유 측 — 계획서 4.3절, 개정 19). PK `area_id` |
| `axis_coverage` | `area_id`, `axis`, `covered`, `season_months`, `reason` | 커버리지 밖·계절 밖 **선언** (시드 — 운영 적용은 DB 소유 측 — 계획서 4.3절, 개정 19). v1.5 13절 `zone_axis_coverage` 대응. 4.9절. PK (`area_id`, `axis`). **`season_months`가 계절 밖 판정의 유일한 원천**이다 |
| `interpolation_runs` | `run_id`, `load_id`, `metric`, `method`, `power_p`, `n_neighbors`, `ref_time_utc`, `station_set_key`, `error_p95`, `error_window_days`, `computed_at_utc` | 4.7절. `station_set_key` = 사용 관측소 `station_id`를 **정렬해 `,`로 이은 값**(예: `tide:DT_0014,tide:DT_0016`). PK `run_id`, **고유 (`load_id`, `metric`)** — 적재 한 번·항목 하나에 IDW 한 번. 같은 `obs.loaded`가 두 번 와도 같은 행 |
| `interpolation_weights` | `run_id`, `farm_id`, `station_id`, `distance_km`, `weight` | "근거 보기". PK (`run_id`, `farm_id`, `station_id`) |
| `interpolation_error` | `station_set_key`, `metric`, `window_days`, `p95`, `mae`, `n_samples`, `computed_on` | 오늘의 오차 (집합별). `station_set_key`는 `interpolation_runs`와 같은 형식. PK (`station_set_key`, `metric`, `window_days`, `computed_on`) |

**결과 테이블 — 웹 서비스가 읽는 것** (의미와 요구사항은 5.5절)

| 테이블 | 핵심 컬럼 | 비고 |
| --- | --- | --- |
| `farm_readings` | `farm_id`, `axis`, `value`, `lower`, `upper`, `unit`, `derivation`, `provenance`, `none_reason`(nullable), `validated_scope`(nullable), `grade`(nullable — 적조만), `alertable`, `source_ref`, `distance_km`, `observed_at_utc`, `computed_at_utc` | 현재값. PK (`farm_id`, `axis`). **`provenance = NONE`이어도 계산된 값은 비우지 않는다**(4.8절). `none_reason`은 `evaluation`의 입력 — 화면 사유는 `axis_status.reason` |
| `farm_reading_history` | 위 + `ts_utc` | 곡선용 시계열. 보존 기간 미결(11절). PK (`farm_id`, `axis`, `ts_utc`) |
| `axis_status` | `farm_id`, `axis`, `state`, `reason`, `basis_utc`, `last_checked_utc` | 4.9절 쓰기 규칙. PK (`farm_id`, `axis`). `state`는 4.9절 상태 값 17종 — `VARCHAR` + `CHECK` |
| `farm_areas` | `farm_id`, `area_id`(nullable), `distance_km`, `rule`, `computed_at_utc` | **모듈이 정한 양식장 해역**(1.6절, 개정 15). PK `farm_id`. `area_id`가 비면 반경 안 해역 없음. `rule` = `NEAREST_CENTER_WITHIN_RADIUS`. `evaluation`이 판정할 때마다 쓴다 |
| `risk_index_factors` | `farm_id`, `factor`, `input_axis`, `input_value`, `input_lower`, `input_upper`, `input_unit`, `input_grade`, `input_baseline`, `score`, `score_lower`, `score_upper`, `weight`, `contribution`, `ok`, `excluded_reason`, `input_none_reason`, `source_ref`, `observed_at_utc`, `computed_at_utc` | 적조 위험도 지수 항목 분해(계획서 4.10절, 개정 20). PK (`farm_id`, `factor`). `factor`(`nearby_bulletin`·`water_temp_band`·`salinity_band`·`chlorophyll_level`)·`excluded_reason`(`NO_INPUT`·`INPUT_NONE`·`SENSOR_QUALITY`·`RULE_UNDECIDED`)은 `VARCHAR`+`CHECK`. `weight`·`contribution`·`ok`·`input_axis`·`computed_at_utc` NOT NULL |
| `risk_index_levels` | `farm_id`, `level`, `level_at_lower`, `level_at_upper`, `level_straddle`, `computed_at_utc` | 지수 단계(4.10절). PK `farm_id`. 전 열 NOT NULL. 단계 코드 `CHECK`는 코드 이름이 정해지면 붙인다 |

- **축 목록 `AXIS_VALS` (개정 20)**: `red_tide_risk`를 더한다 — `farm_readings`·`farm_reading_history`·`axis_status`·`axis_coverage`의 `axis` `CHECK`. 열 변경 없음
| `bulletins` · `bulletin_details` · `bulletin_detail_areas` | 위 표와 같음 | 적조 속보 원천. **해역 없는 속보**는 여기에만 있다(4.8절). 지점별 해역은 `bulletin_detail_areas` |
| `interpolation_weights` · `interpolation_error` · `stations` | 위 표와 같음 | "근거 보기" — 사용 관측소·거리·가중치·오차 산출 기준 |

**읽기 전용 입력 — 이 모듈이 만들지 않는 것**

| 테이블 | 필요한 컬럼 | 소유 |
| --- | --- | --- |
| `farm_sites` (이름은 웹 쪽 결정) | `farm_id`, `lat`, `lng`, `active`, `updated_at_utc` | 웹 서비스 (1.6절) |

- `DECIMAL` 정밀도: 좌표 `(9,6)`, 수온·염분 `(6,3)`, 밀도 `(12,2)` — 두 DB 동일
- 불린은 SQLAlchemy `Boolean` (MySQL에서 `TINYINT(1)`로 생성됨)

- **모든 테이블의 키가 위 표에 있다.** upsert의 충돌 키가 그 키다(③-4). `ingest_runs`의 고유 (`raw_id`, `parser_version`)와 `interpolation_runs`의 고유 (`load_id`, `metric`)는 PK가 아니라 **고유 제약**으로 만든다
- `farm_sites`는 웹 소유라 모델을 만들지 않는다. 읽는 코드와 입력 계약은 `common-core`(`common/farm_sites/`, `contracts/inputs/farm_sites.md`)다

### ③-4 DB 접근 계층과 연결 (5.4절)

테이블 모델은 `common/repository/tables.py`에 두고, 정의 제안(계약·DDL 생성본)은 `contracts/tables/`에 둔다(2.0.1절). 마이그레이션 코드는 없다.

```
common/repository/
  tables.py      # SQLAlchemy 모델 — DDL 생성과 기동 시 검사의 기준
  base.py        # 인터페이스: upsert_observations, insert_raw_index, …
  sql.py         # SQLAlchemy Core 구현 — 방언 무관 부분
  dialect.py     # 방언 분기는 여기만: upsert, 대량 적재, DDL·시드 SQL 생성
```

- **방언 분기는 `dialect.py` 한 파일로 제한한다.** 다른 파일에서 `postgresql`/`mysql` 문자열이 나오면 리뷰에서 반려
- 대량 적재는 `executemany` 기준. PG `COPY` 같은 최적화는 필요해질 때 `dialect.py`에만
- **upsert의 충돌 키 = 멱등 키**다(2.2절). 5.3절의 PK·고유 키가 그 키다. 복합 키는 `Index(..., unique=True)`로 두고 **생성기(`dialect._ddl`)가 `CREATE UNIQUE INDEX`로 낸다** — `CreateTable`은 `Index`를 내지 않는다
- **DB 연결은 양식에서 하나를 고른다.** DB가 확정되지 않았으므로 `.env.example`에 두 DB의 양식을 **주석으로** 두고, 사용자가 고른 쪽의 주석을 풀어 `.env`에 쓴다. DB 종류를 따로 설정하지 않는다 — URL의 앞부분이 방언을 정한다

```
# --- DB 연결: 하나를 골라 주석을 푼다 ---
# DATABASE_URL=postgresql+psycopg://<user>:<password>@<host>:5432/<db>
# DATABASE_URL=mysql+pymysql://<user>:<password>@<host>:3306/<db>?charset=utf8mb4
# --- 테스트 DB: 위와 같은 쪽을 고른다 ---
# TEST_DATABASE_URL=postgresql+psycopg://<user>:<password>@localhost:5432/<db>_test
# TEST_DATABASE_URL=mysql+pymysql://<user>:<password>@localhost:3306/<db>_test?charset=utf8mb4
# --- (선택) 두 DB 비교 검사용 — 다른 쪽 DB (7.4절) ---
# TEST_DATABASE_URL_ALT=
```

- 연결 문자열에는 비밀번호가 들어가므로 **인증키와 같게 다룬다** — `.env`에만 두고 출력하지 않으며, `HANDOFF.md`에는 이름만 적는다(12.1절). 드라이버(`psycopg`·`PyMySQL`)는 I-6에서 정하고 `pyproject.toml`과 보고서에 적는다

- **`upsert()`는 `dialect.py` 한 곳**에서 방언별로 만든다(PG `ON CONFLICT` / MySQL `ON DUPLICATE KEY`). 다른 파일은 `upsert()`를 부르기만 한다
- `ingest_runs`는 **재처리(파서 버전이 바뀐 경우)마다 행을 추가**한다. 같은 파서 버전의 중복 처리는 고유 제약으로 행이 늘지 않는다
- `ops_events`는 고유 키가 없다 — 쌓이는 로그다

---

## ④ 이식 출처 (6.3절)

| 새 경로 | 검증 코드 위치 | 처리 |
| --- | --- | --- |
| `common/repository/` | — | **신규** — 검증 코드는 전부 CSV 출력이었다 |

- 이식할 코드가 없다. `docs/SOURCES.md`에는 "신규"로 적는다

---

## ⑤ 함정

- **MySQL `TEXT`는 64KB다.** `sooList` 1년 응답은 약 4MB — 원문 본문을 DB에 넣으면 잘린다. 본문은 객체 저장소, DB는 색인(`raw_index`)만
- **MySQL 콜레이션은 대소문자를 무시하고, 구형은 뒤 공백도 무시한다.** `"전남 여수"`와 `"전남 여수 "`가 따로 세어진 버그를 PAD SPACE 콜레이션은 숨긴다. 비교는 **정규화 키 열로만** 한다. 문자셋 `utf8mb4`, 콜레이션 `utf8mb4_0900_ai_ci`(NO PAD)를 **명시**한다
- **시각은 초 단위로 절삭한다.** 반올림하면 같은 관측이 경계에서 다른 초로 저장돼 키가 어긋날 수 있다. 원문 파일의 `fetched_at`은 원래 정밀도를 유지한다 — DB 열만 초 단위다
- **MySQL `CHECK`는 8.0.16부터 강제된다.** 그 전 버전은 조용히 무시한다 — MySQL을 고른다면 테스트 컨테이너는 8.0 최신 패치로 둔다
- **식별자는 64자 이하.** 긴 테이블·인덱스·제약 이름은 MySQL에서 실패한다 — `MetaData(naming_convention=…)`로 규칙을 정한다. PostgreSQL을 골라도 지킨다(나중에 바뀔 수 있다)
- **`RETURNING`에 기대지 않는다** — MySQL에 없다. 삽입 후 필요한 값은 다시 조회한다
- **`JSON` 열은 저장·통째 조회만 한다.** 조건에 쓰는 값은 정규 열로 뺀다 — `ops_events.detail`에서 값을 꺼내 검색하는 쿼리를 만들지 않는다
- **`TIMESTAMPTZ`에 기대지 않는다.** 시간대가 있는 값은 넣기 전에 UTC naive로 바꾼다
- **테이블이 없다고 만들지 않는다.** 테스트용 스키마는 테스트 컨테이너에 **생성본 DDL을 적용**해 만든다 — 그것이 DDL 검증도 겸한다(7.4절)
- **고른 DB 쪽만 검증된다.** 고르지 않은 DB의 방언 분기와 DDL은 실행되지 않으므로, PostgreSQL을 골랐다고 MySQL 분기를 비워 두거나 반대로 해서는 안 된다 — 두 분기 모두 작성하고, 검증되지 않은 쪽을 보고서에 적는다
- **연결 문자열에는 비밀번호가 있다.** 인증키와 같게 다룬다 — 출력하지 않는다(`CLAUDE.md` 2절)
- **`postgresql`·`mysql` 문자열이 `dialect.py` 밖에 나오면 반려**다. 연결 URL은 설정에서 읽으므로 코드에 쓰지 않는다

---

## ⑥ 검사와 기대값 (7.4절)

DB가 확정되지 않았다. 설계는 두 DB에 중립(5절)이고 **DDL 생성본도 두 벌 만든다** — 확정 전의 시간을 사는 이중 설계다. 실행 검사는 **사용자가 `.env`에서 고른 DB 하나**로 돈다. 두 DB를 모두 띄우는 것은 필수가 아니다.

**필수 — 고른 DB에서**

- DB에 쓰는 검사 전체(7.1의 F1~F10, 7.3, 7.5)
- 고른 DB용 **DDL 생성본이 오류 없이 적용**되고, 적용 결과가 모델로 만든 스키마와 같다
- 기동 시 검사: 테이블 하나를 빼거나 열 하나를 바꾸거나 **고유 키(고유 인덱스) 하나를 지운** DB에서 **기동이 멈추고 차이를 보고**한다. 같은 컬럼 조합의 키가 다른 이름으로 있으면 통과한다(개정 22)
- **생성본에 모델의 고유 키가 모두 있다**(PK·고유 제약·고유 인덱스 — `tables.unique_keys()`). 같은 키로 두 번 upsert하면 한 행. **코드의 모든 upsert 충돌 키 = 모델 고유 키 중 하나**(정적 검사). 다른 DB용 생성본에도 고유 인덱스 문장이 있다 — 개정 22 점검 후속: 생성기가 고유 인덱스를 건너뛰어 12개 표의 키가 빠졌고, 테스트가 모델 `create_all`로 스키마를 만들어 놓쳤다
- **해역 시드 생성본 (개정 19, 계획서 7.4절)**: SD2 — 고른 DB용 생성본 적용 결과 = `load_seeds` 결과(행 단위), 시드에서 행 하나를 지운 생성본을 다시 적용하면 그 행이 사라진다. 다른 DB용은 생성까지. 생성본은 한 트랜잭션에서 `DELETE` 후 전체 삽입(MySQL `TRUNCATE` 금지 — 암묵 커밋), 실수는 왕복 가능한 표기, 머리에 시드 파일 해시. SD4 — 커밋된 생성본 = 지금 시드로 만든 생성기 출력(바이트 단위, DB 없이 게이트 안)
- 콜레이션 검사: `txt_seas_raw`에 `"전남 여수"`와 `"전남 여수 "`를 넣고 **정규화 키로는 같고 원문 비교로는 다르게** 나오는지
- 다른 DB용 DDL 생성본은 **생성까지** 확인한다(파일이 만들어지고 비어 있지 않다)

**선택 — `TEST_DATABASE_URL_ALT`가 있을 때만**

- 같은 픽스처를 두 DB에 적재한 뒤 **테이블별 행 수와 정렬된 전체 행의 해시가 같아야** 통과
- 다른 DB용 DDL 생성본의 적용 검증

- **남는 한계**: 고르지 않은 DB의 방언 분기(`dialect.py`)와 DDL 생성본은 실행으로 검증되지 않는다. **DB가 확정되면 선택 검사를 한 번 돌린다** — 확정 DB가 처음 고른 DB와 다르면 반드시

- 필수 항목은 **7.7절 CI 게이트 안**에 들어간다("7.4 DB 검사(필수 항목)")
- S3~S6은 정규화 결과(메모리)까지만 검증했다. S7에서 DB 적재를 붙이고 **같은 픽스처를 고른 DB로 다시** 돌린다 — F1~F10의 기대값(7.7절 `counts`)이 그대로 나와야 한다
- 관련 검사(다른 skill 소유): B4(테이블 계약 불일치 → 기동 멈춤) — `common-core`의 `contract_check`, I-10에서 돈다

---

## ⑦ 주인이 아닌 사실 — 참조만

| 사실 | 주인 |
| --- | --- |
| `_utc` 규칙, 필드 의미, 연결 문자열 취급(2절) | `CLAUDE.md` |
| 기동 시 테이블·계약 버전 검사의 실행, 원문 저장(객체 저장소), 큐, 설정 로딩 | `common-core` |
| 각 테이블에 무엇을 쓰는가(정규화 규칙), `station_id` 값을 만드는 곳 | `tide`·`bulletin`·`line`·`fishery`·`interpolation`·`grading`·`evaluation` |
| 결과 테이블의 의미 계약(5.5절) 배포 | `evaluation` |

### MySQL "있으면 그대로" 업서트 (2026-10-01 수정)

- `upsert(update_cols=[])`는 PostgreSQL `ON CONFLICT DO NOTHING`, MySQL은 **키 열을 자기 값으로 두는 무변경 `ON DUPLICATE KEY UPDATE`** — 일반 INSERT로 두면 중복에서 오류가 나고, `INSERT IGNORE`는 CHECK 위반까지 경고로 삼킨다. 한 문장의 바인드 매개변수는 6만 단위로 나눠 보낸다(PostgreSQL·MySQL 한도 65,535)

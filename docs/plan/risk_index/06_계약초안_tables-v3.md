# 적조 위험도 지수 — 결과 테이블 계약 초안 `tables-v3` (선공유용)

작성 2026-10-02 · API 모듈 → 대시보드 · **보류 — 구현을 마친 뒤 확정본으로 전달한다(2026-10-02 사용자 결정)**

**초안입니다.** 표 모양(열 이름·형식·키)은 이 초안으로 미리 맞춰 보셔도 됩니다. **값(가중치·점수·단계 경계·단계 코드 이름)은 아직 정해지지 않았습니다.** 아래 예시 행의 숫자와 단계 코드는 모양을 보여 주기 위한 것이고 확정값이 아닙니다. 확정되면 같은 열에 실제 값이 들어갑니다.

---

## 1. 바뀌는 것 한눈에

| 구분 | 내용 |
| --- | --- |
| 지수 값 | 기존 `farm_readings`에 축 **`red_tide_risk`** 한 행(양식장마다). 열 추가 없음 |
| 항목 분해 | 새 표 **`risk_index_factors`** — 양식장 × 항목 4개 |
| 단계 | 새 표 **`risk_index_levels`** — 양식장당 한 행. 단계 코드와 경계 걸침 |
| 상태 | 기존 `axis_status`에 축 `red_tide_risk` 한 행. 상태 값 목록은 그대로 |
| 이력 | 지수 값의 이력은 기존 `farm_reading_history`에 함께 쌓입니다. 항목 분해와 단계는 현재값만 둡니다 |
| 기존 표 정의 변경 | 열 추가는 없습니다. **축 목록 제약(CHECK)에 `red_tide_risk` 값 하나 추가** — `farm_readings`·`farm_reading_history`·`axis_status`·`axis_coverage`. `none_reason` 새 값 `INSUFFICIENT_FACTORS`·`RULE_UNDECIDED` |

계산은 모듈이 합니다. 입력 축(수온·적조·염분·클로로필)이 새로 적재될 때마다 다시 계산합니다(약 10분 주기). 대시보드는 표시만 하고 다시 계산하지 않습니다.

---

## 2. `farm_readings` — 축 `red_tide_risk` 행

| 열 | 값 |
| --- | --- |
| `value` | 지수 합산값 0~1 = 항목 기여도의 합 |
| `lower` · `upper` | 지수가 될 수 있는 범위(아래 4절). 최솟값·최댓값 관측이 아니라 **입력의 불확실성이 만드는 범위**입니다 |
| `unit` | `NULL` (무차원) |
| `derivation` | `COMPUTED` |
| `provenance` | OK 항목 수가 하한 이상이면 `INTERPOLATED`, 미만이면 `NONE` |
| `none_reason` | `provenance = NONE`일 때 `INSUFFICIENT_FACTORS`(OK 항목 부족) 또는 `RULE_UNDECIDED`(규칙 일부가 아직 정해지지 않음 — 가중치가 미정이면 값·분해·단계 행이 없고, 품질 하한만 미정이면 값·분해는 있습니다. 단계 경계가 미정이면 단계 행만 없습니다) |
| `validated_scope` | `NULL` — 지수는 적조 발생 예측력을 검증하지 않습니다 |
| `grade` | `NULL` — `grade`는 적조 공식 등급 전용입니다. 지수의 단계는 `risk_index_levels`에 있습니다 |
| `alertable` | 항상 `false` |
| `source_ref` | `NULL` — 근거는 항목마다 `risk_index_factors.source_ref`에 있습니다 |
| `observed_at_utc` | OK 항목 입력의 `observed_at_utc` 중 **가장 이른 값** *(제안)* — 지수가 그 시각 이후의 입력만으로 이뤄졌다는 뜻. 값이 없는 항목은 제외합니다(아래 7절 확인 요청) |
| `computed_at_utc` | 계산 시각 |

- `provenance = NONE`이어도 계산할 수 있었던 `value`·`lower`·`upper`는 저장합니다. 화면에서 가리는 규칙(기존 W2)은 그대로입니다.

---

## 3. `risk_index_factors` — 항목 분해 (신설)

키: (`farm_id`, `factor`). 양식장마다 항목 4행.

| 열 | 형식 | 뜻 |
| --- | --- | --- |
| `farm_id` | `VARCHAR(64)` | 양식장 |
| `factor` | `VARCHAR(32)` | 항목 — `nearby_bulletin` · `water_temp_band` · `salinity_band` · `chlorophyll_level` |
| `input_axis` | `VARCHAR(64)` | 입력으로 쓴 축 — `red_tide` · `water_temp` · `salinity` · `chlorophyll` |
| `input_value` | `DOUBLE`, null 가능 | 입력값(단위는 `input_unit`). 적조는 `NULL`(등급을 씁니다) |
| `input_lower` · `input_upper` | `DOUBLE`, null 가능 | 입력 축의 `lower`·`upper` 그대로(수온: 값 ∓ 오늘의 오차) |
| `input_unit` | `VARCHAR(64)`, null 가능 | 입력 단위 |
| `input_grade` | `VARCHAR(16)`, null 가능 | 적조 항목만 — 입력 축 `red_tide`의 `grade`. 유효 기간 안 속보가 없으면 `NULL` |
| `input_baseline` | `DOUBLE`, null 가능 | 클로로필 항목만 — 상승을 판단한 비교 기준값. **비교 대상의 정의가 정해지지 않아 열 자체가 바뀔 수 있습니다** |
| `score` | `DOUBLE`, null 가능 | 항목 점수 0~1. 제외 항목은 `NULL` |
| `score_lower` · `score_upper` | `DOUBLE`, null 가능 | 입력 범위(`input_lower`~`input_upper`)가 만들 수 있는 점수 범위. 범위가 없는 입력은 `score`와 같습니다. 제외 항목은 `NULL` |
| `weight` | `DOUBLE` | 가중치 |
| `contribution` | `DOUBLE` | 기여도 = `weight` × `score`. **제외 항목은 0** |
| `ok` | `BOOLEAN` | 이 항목을 합산에 썼는가 |
| `excluded_reason` | `VARCHAR(32)`, null 가능 | `ok = false`일 때의 사유 코드(아래) |
| `input_none_reason` | `VARCHAR(64)`, null 가능 | `excluded_reason = INPUT_NONE`일 때 입력 축의 `none_reason`을 옮긴 값 |
| `source_ref` | `VARCHAR(255)`, null 가능 | 입력 축 행의 `source_ref` 그대로 |
| `observed_at_utc` | `DATETIME`, null 가능 | 입력 축 행의 `observed_at_utc` 그대로 |
| `computed_at_utc` | `DATETIME` | 계산 시각 |

**보장**: 네 행의 `contribution` 합 = `farm_readings.value`(반올림하지 않은 저장 값 기준). 화면 반올림은 대시보드가 합니다.

**제외 사유 코드** (`excluded_reason`)

| 코드 | 뜻 |
| --- | --- |
| `SENSOR_QUALITY` | 원천 관측값에 품질 플래그(관측값 이상) |
| `INPUT_NONE` | 입력 축의 `provenance = NONE` — 사유는 `input_none_reason` |
| `NO_INPUT` | 입력 축 행이 없거나 `value`가 없음 |
| `RULE_UNDECIDED` | 그 항목의 점수 규칙이 아직 정해지지 않음 *(제안)* |

적조 항목에서 "유효 기간 안 속보 없음"은 제외가 아닙니다 — **OK, 점수 0**입니다(속보가 없는 것은 정상적 침묵).

---

## 4. 계산 규칙 요약

| 규칙 | 내용 |
| --- | --- |
| OK 항목 | 입력 축에 `value`가 있고(적조는 속보 없음도 OK), `provenance ≠ NONE`이고, 품질 플래그가 없는 항목 |
| 기여도 | `weight` × `score` |
| 지수 `value` | OK 항목 기여도의 합(제외 항목은 0) |
| 지수 `lower` | Σ `weight` × `score_lower` (OK 항목) |
| 지수 `upper` | Σ `weight` × `score_upper` (OK 항목) **+ 제외 항목 `weight`의 합** — 빠진 항목은 0~1 어디든 될 수 있다는 불확실성을 범위에 넣습니다 |
| 품질 하한 | OK 항목 수가 하한(값 미정) 미만이면 `provenance = NONE`, `none_reason = INSUFFICIENT_FACTORS` |
| 단계 | `value`·`lower`·`upper` 각각을 단계 경계(값 미정)로 판정 — 5절 |

---

## 5. `risk_index_levels` — 단계 (신설)

키: `farm_id`. 양식장당 한 행.

| 열 | 형식 | 뜻 |
| --- | --- | --- |
| `farm_id` | `VARCHAR(64)` | 양식장 |
| `level` | `VARCHAR(16)` | `value`의 단계 코드 |
| `level_at_lower` | `VARCHAR(16)` | `lower`의 단계 코드 |
| `level_at_upper` | `VARCHAR(16)` | `upper`의 단계 코드 |
| `level_straddle` | `BOOLEAN` | `lower`~`upper`가 단계 경계에 걸치는가(= `level_at_lower ≠ level_at_upper`) |
| `computed_at_utc` | `DATETIME` | 계산 시각 — `farm_readings`의 `red_tide_risk` 행과 같은 값 |

- 단계 판정은 모듈이 합니다. 대시보드가 `value`를 잘라 단계를 만들지 않아도 됩니다
- `provenance = NONE`이어도 계산할 수 있었던 단계는 저장합니다(표시 여부는 대시보드 규칙 그대로)
- **단계 수와 코드 이름, 경계값은 미정입니다.** 예시는 5단계 `VERY_LOW`·`LOW`·`MEDIUM`·`HIGH`·`VERY_HIGH`로 적었습니다

---

## 6. `axis_status` — 축 `red_tide_risk`

| 상태 | 언제 |
| --- | --- |
| `NOT_USABLE` | 품질 하한 미달(`reason = INSUFFICIENT_FACTORS`) 또는 규칙 미정(`RULE_UNDECIDED`) |
| `GRADING_STALE` | 산출 지연(기존 규칙 그대로) |
| `NORMAL` | 그 밖 |

입력 항목 하나가 `STALE`이어도 지수의 상태로 옮기지 않습니다 — 그 항목이 OK인지는 품질 하한이 판단합니다. 새 상태 값은 없습니다.

---

## 7. 항목별 입력 단위·판정 값

| `factor` | 입력 축 | 입력 단위 | 판정 | 미정인 값 |
| --- | --- | --- | --- | --- |
| `nearby_bulletin` | `red_tide` | 적조 등급(`input_grade`) | 등급별 점수 | 등급별 점수(`WARNING`·`ADVISORY`·`PRE_ADVISORY`·`UNKNOWN`·`NONE`·`NOT_GRADED`), 가중치 |
| `water_temp_band` | `water_temp` | ℃ | 수온 구간별 점수. 범위(∓ 오늘의 오차)로 `score_lower`·`score_upper` | 구간 경계·점수, 가중치 |
| `salinity_band` | `salinity` | psu | 염분 구간이면 점수, 밖이면 0. 입력은 화면의 염분과 같은 행(가까운 조위관측소 실측) | 구간·점수, 가중치 |
| `chlorophyll_level` | `chlorophyll` | μg/L | 비교 기준 대비 상승이면 점수 | 비교 대상·상승 기준·점수, 가중치 |

참고(미확정): 원안의 가중치는 `nearby_bulletin` 0.40 · `water_temp_band` 0.30 · `salinity_band` 0.15 · `chlorophyll_level` 0.15, 품질 하한은 OK 항목 2개입니다. 아래 예시 행은 이 원안과 임시 점수로 계산했습니다.

---

## 8. 예시 행 (값은 임시 — 모양 확인용)

예시 A — 클로로필이 품질 플래그로 빠진 양식장. 수온 범위가 구간 밖까지 걸치고, 빠진 항목 때문에 `upper`가 올라가 단계가 걸칩니다.

```json
{
  "farm_readings": [
    {"farm_id": "syn_gam_001", "axis": "red_tide_risk", "value": 0.655, "lower": 0.355, "upper": 0.805,
     "unit": null, "derivation": "COMPUTED", "provenance": "INTERPOLATED", "none_reason": null,
     "validated_scope": null, "grade": null, "alertable": false, "source_ref": null, "distance_km": null,
     "observed_at_utc": "2026-08-14T03:00:00", "computed_at_utc": "2026-08-14T03:10:00"}
  ],
  "risk_index_factors": [
    {"farm_id": "syn_gam_001", "factor": "nearby_bulletin", "input_axis": "red_tide",
     "input_value": null, "input_lower": null, "input_upper": null, "input_unit": null,
     "input_grade": "ADVISORY", "input_baseline": null,
     "score": 0.7, "score_lower": 0.7, "score_upper": 0.7, "weight": 0.40, "contribution": 0.28,
     "ok": true, "excluded_reason": null, "input_none_reason": null,
     "source_ref": "20260812-003#1", "observed_at_utc": null, "computed_at_utc": "2026-08-14T03:10:00"},
    {"farm_id": "syn_gam_001", "factor": "water_temp_band", "input_axis": "water_temp",
     "input_value": 25.1, "input_lower": 22.62, "input_upper": 27.58, "input_unit": "°C",
     "input_grade": null, "input_baseline": null,
     "score": 1.0, "score_lower": 0.0, "score_upper": 1.0, "weight": 0.30, "contribution": 0.30,
     "ok": true, "excluded_reason": null, "input_none_reason": null,
     "source_ref": "acf4de85-c5cb-447b-b539-ac475003ac3d", "observed_at_utc": "2026-08-14T03:00:00",
     "computed_at_utc": "2026-08-14T03:10:00"},
    {"farm_id": "syn_gam_001", "factor": "salinity_band", "input_axis": "salinity",
     "input_value": 32.4, "input_lower": null, "input_upper": null, "input_unit": "psu",
     "input_grade": null, "input_baseline": null,
     "score": 0.5, "score_lower": 0.5, "score_upper": 0.5, "weight": 0.15, "contribution": 0.075,
     "ok": true, "excluded_reason": null, "input_none_reason": null,
     "source_ref": "tide:DT_0014", "observed_at_utc": "2026-08-14T03:00:00", "computed_at_utc": "2026-08-14T03:10:00"},
    {"farm_id": "syn_gam_001", "factor": "chlorophyll_level", "input_axis": "chlorophyll",
     "input_value": 4.57, "input_lower": null, "input_upper": null, "input_unit": "μg/L",
     "input_grade": null, "input_baseline": null,
     "score": null, "score_lower": null, "score_upper": null, "weight": 0.15, "contribution": 0.0,
     "ok": false, "excluded_reason": "SENSOR_QUALITY", "input_none_reason": null,
     "source_ref": "fishery:<정점>@2025-10-19T04:00:00", "observed_at_utc": "2025-10-19T04:00:00",
     "computed_at_utc": "2026-08-14T03:10:00"}
  ],
  "risk_index_levels": [
    {"farm_id": "syn_gam_001", "level": "HIGH", "level_at_lower": "LOW", "level_at_upper": "VERY_HIGH",
     "level_straddle": true, "computed_at_utc": "2026-08-14T03:10:00"}
  ],
  "axis_status": [
    {"farm_id": "syn_gam_001", "axis": "red_tide_risk", "state": "NORMAL", "reason": null,
     "basis_utc": "2026-08-14T03:00:00", "last_checked_utc": "2026-08-14T03:10:00"}
  ]
}
```

계산: `value` = 0.28 + 0.30 + 0.075 = 0.655 · `lower` = 0.28 + 0.30×0.0 + 0.075 = 0.355 · `upper` = 0.28 + 0.30×1.0 + 0.075 + **0.15**(빠진 클로로필) = 0.805. 예시 단계 경계(임시) 0.2 / 0.4 / 0.6 / 0.8.

예시 B — OK 항목이 하나뿐이라 품질 하한 미달. 값은 저장하지만 `provenance = NONE`입니다.

```json
{
  "farm_readings": [
    {"farm_id": "syn_gam_002", "axis": "red_tide_risk", "value": 0.075, "lower": 0.075, "upper": 0.925,
     "unit": null, "derivation": "COMPUTED", "provenance": "NONE", "none_reason": "INSUFFICIENT_FACTORS",
     "validated_scope": null, "grade": null, "alertable": false, "source_ref": null, "distance_km": null,
     "observed_at_utc": "2026-08-14T03:00:00", "computed_at_utc": "2026-08-14T03:10:00"}
  ],
  "risk_index_factors": [
    {"farm_id": "syn_gam_002", "factor": "nearby_bulletin", "ok": false, "excluded_reason": "NO_INPUT",
     "score": null, "weight": 0.40, "contribution": 0.0, "...": "그 밖의 열은 NULL"},
    {"farm_id": "syn_gam_002", "factor": "water_temp_band", "ok": false, "excluded_reason": "INPUT_NONE",
     "input_none_reason": "ERROR_ABOVE_LIMIT", "input_value": 24.8, "score": null, "weight": 0.30, "contribution": 0.0},
    {"farm_id": "syn_gam_002", "factor": "salinity_band", "ok": true, "input_value": 32.6, "score": 0.5,
     "weight": 0.15, "contribution": 0.075},
    {"farm_id": "syn_gam_002", "factor": "chlorophyll_level", "ok": false, "excluded_reason": "NO_INPUT",
     "score": null, "weight": 0.15, "contribution": 0.0}
  ],
  "risk_index_levels": [
    {"farm_id": "syn_gam_002", "level": "VERY_LOW", "level_at_lower": "VERY_LOW", "level_at_upper": "VERY_HIGH",
     "level_straddle": true, "computed_at_utc": "2026-08-14T03:10:00"}
  ],
  "axis_status": [
    {"farm_id": "syn_gam_002", "axis": "red_tide_risk", "state": "NOT_USABLE", "reason": "INSUFFICIENT_FACTORS",
     "basis_utc": "2026-08-14T03:00:00", "last_checked_utc": "2026-08-14T03:10:00"}
  ]
}
```

(예시 B의 분해 행은 읽기 쉽게 일부 열만 적었습니다. 실제 행은 3절의 열을 모두 가집니다.)

---

## 9. 새 표 정의 (초안)

PostgreSQL

```sql
CREATE TABLE risk_index_factors (
	farm_id VARCHAR(64) NOT NULL,
	factor VARCHAR(32) NOT NULL,
	input_axis VARCHAR(64) NOT NULL,
	input_value DOUBLE PRECISION,
	input_lower DOUBLE PRECISION,
	input_upper DOUBLE PRECISION,
	input_unit VARCHAR(64),
	input_grade VARCHAR(16),
	input_baseline DOUBLE PRECISION,
	score DOUBLE PRECISION,
	score_lower DOUBLE PRECISION,
	score_upper DOUBLE PRECISION,
	weight DOUBLE PRECISION NOT NULL,
	contribution DOUBLE PRECISION NOT NULL,
	ok BOOLEAN NOT NULL,
	excluded_reason VARCHAR(32),
	input_none_reason VARCHAR(64),
	source_ref VARCHAR(255),
	observed_at_utc TIMESTAMP WITHOUT TIME ZONE,
	computed_at_utc TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	CONSTRAINT pk_risk_index_factors PRIMARY KEY (farm_id, factor),
	CONSTRAINT ck_risk_index_factors_factor CHECK (factor IN ('nearby_bulletin', 'water_temp_band', 'salinity_band', 'chlorophyll_level')),
	CONSTRAINT ck_risk_index_factors_excluded_reason CHECK (excluded_reason IN ('SENSOR_QUALITY', 'INPUT_NONE', 'NO_INPUT', 'RULE_UNDECIDED'))
);

CREATE TABLE risk_index_levels (
	farm_id VARCHAR(64) NOT NULL,
	level VARCHAR(16) NOT NULL,
	level_at_lower VARCHAR(16) NOT NULL,
	level_at_upper VARCHAR(16) NOT NULL,
	level_straddle BOOLEAN NOT NULL,
	computed_at_utc TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	CONSTRAINT pk_risk_index_levels PRIMARY KEY (farm_id)
);
```

MySQL 8.0 — 형식만 다릅니다(`DOUBLE`, `BOOL`, `DATETIME`, 문자셋 `utf8mb4`). 같은 열·키·제약입니다.

- 단계 코드 열(`level`·`level_at_*`)의 허용 값 제약은 코드 이름이 정해지면 붙입니다
- 기존 표: 축 목록 제약 4곳에 `'red_tide_risk'` 추가. 열 변경 없음

---

## 10. 확인 요청

1. **`level_at_lower`·`level_at_upper`**: 걸침 여부(`level_straddle`)만 원하셨는데, 화면에 "LOW~VERY_HIGH"처럼 범위를 보이실 수 있도록 양 끝의 단계 코드도 넣었습니다. 필요 없으면 빼겠습니다
2. **지수의 `observed_at_utc`**: "OK 항목 입력 중 가장 이른 관측 시각"으로 제안합니다. 지금은 적조 행의 `observed_at_utc`가 비어 있어 적조 항목은 이 계산에서 빠집니다(적조 관측 시각의 정의는 따로 정하는 중입니다). 신선도 표시에 다른 기준이 더 편하시면 알려 주세요
3. **`input_baseline`**: 클로로필 "상승"의 비교 대상이 정해지지 않아 열 이름·뜻이 바뀔 수 있습니다. 화면에서 비교 기준값을 보이실 계획인지 알려 주세요 — 보이지 않으면 열을 빼는 쪽으로 정하겠습니다
4. 예시 행으로 가짜 데이터를 미리 맞추실 때, 값이 정해지면 같은 열에 실제 값이 들어갑니다. 열이 바뀌면 다시 알려 드리겠습니다

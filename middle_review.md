# AquaSentinel API 모듈 중간 점검 보고서

**점검 일자**: 2026-09-30  
**점검 범위**: I-0 ~ I-10 전 구현 코드  
**목적**: 수정 없이 체크만 — 규칙 위반·경고·통과 항목 기록  
**수정 적용**: 2026-09-30 (V-1·W-1·W-2·W-3 모두 수정 완료)  
**참조 규칙**: `CLAUDE.md` 실행자 규칙(12.1절), 금지 규칙(12절), 계획서 4.8·5.5·7.7절  

---

## 요약

| 구분 | 건수 | 상태 |
| --- | --- | --- |
| **위반** | 1 | ✓ 수정 완료 (V-1) |
| **경고** | 3 | ✓ 모두 수정 완료 (W-1·W-2·W-3) |
| **통과** | 27 | — |
| **계획서 반영 후보** | 2 | — |

---

## 위반 — DB CHECK 제약 위반

### V-1: `PROVENANCE_VALS`에 `"BASELINE"` 누락

**파일**: `src/api_module/common/repository/tables.py:41`  
**연관**: `src/api_module/grading/main.py:221`, `main.py:252`

**현상**

```python
# tables.py:41
PROVENANCE_VALS = ("NONE", "OBSERVED", "NEAREST", "INTERPOLATED", "OFFICIAL", "SURVEY")
```

`"BASELINE"`이 없다. 그런데 `grading/main.py`에서 DO(line 221)와 클로로필(line 252)에 `"provenance": "BASELINE"`을 할당한다.

```python
# grading/main.py:221 — DO 행
"provenance": "BASELINE",

# grading/main.py:252 — 클로로필 행
"provenance": "BASELINE",
```

`tables.py`의 `PROVENANCE_VALS`는 `farm_readings` 및 `farm_readings_history` 테이블의 `CheckConstraint`에 직접 사용된다(line 358, 384). 즉 `upsert_farm_readings()` 호출 시 DB가 거부한다.

**원인**

계획서 4.8절 표(line 624–625)와 grading SKILL.md는 DO·클로로필에 `BASELINE`을 명시한다:

```
| DO       | ... | SURVEY | BASELINE (결정 전 NONE) | false |
| 클로로필a | ... | SURVEY | BASELINE                | false |
```

`grading/main.py`는 계획서를 올바르게 구현했으나, `tables.py`에 `"BASELINE"`을 추가하지 않았다.

**수정 방향**

`tables.py:41`의 튜플에 `"BASELINE"` 추가:

```python
PROVENANCE_VALS = ("NONE", "OBSERVED", "NEAREST", "INTERPOLATED", "OFFICIAL", "SURVEY", "BASELINE")
```

`CHECK` 제약이 바뀌므로 **게이트 기준 문서(`ci/gate/expected.yaml`)도 같은 커밋에서 갱신**해야 한다(판정 정의 변경 규칙, CLAUDE.md 금지 규칙).

---

## 경고 — 운영 전 확인 권고

### W-1: `datetime.utcnow()` 사용 — Python 3.12 deprecated

**파일**: `src/api_module/evaluation/main.py:23`

```python
now = datetime.utcnow()
```

Python 3.12에서 `datetime.utcnow()`가 deprecated되었다. `interpolation/main.py`는 올바른 방식을 쓴다:

```python
datetime.now(timezone.utc).replace(tzinfo=None)
```

`evaluation/main.py`만 구식 방법을 사용한다. 기능적 결함은 아니지만 Python 3.13에서 제거 예정이므로 조기 수정을 권고한다.

---

### W-2: STALE_SUSPECT 플래그 검사 대상 관측소 불명확

**파일**: `src/api_module/evaluation/main.py` — `handle_grade_done()` 내 STALE_SUSPECT 처리

`STALE_SUSPECT` 플래그는 "수온값 멈춤 감지"이며 특정 관측소의 플래그다. 현재 코드는 `obs_rows[0].get("flags")`로 첫 번째 관측 행의 플래그를 읽는다. `obs_rows`가 양식장과 연결된 관측소 기준으로 정렬되어 있다면 문제없지만, 여러 관측소 행이 섞여 있다면 엉뚱한 관측소의 플래그를 보게 된다.

**확인 필요 사항**: `obs_rows`가 해당 양식장의 연결 관측소 기준으로 이미 필터·정렬된 결과인지, 아니면 전체 관측 결과인지 검토가 필요하다.

---

### W-3: `queue.publish()` 인수 타입 불일치

**파일**: `src/api_module/evaluation/main.py` — `handle_grade_done()` 내 `queue.publish()`

```python
# evaluation/main.py
queue.publish({"topic": "grade.done", ...})   # 딕셔너리 직접 전달
```

```python
# grading/main.py:318
queue.publish(Message(topic="grade.done", payload={...}))  # Message 래퍼 사용
```

`evaluation`만 raw dict를 전달한다. `MemoryQueue`가 양쪽을 수용하면 단위 테스트는 통과하지만 운영 큐 구현체가 `Message` 타입을 강제할 경우 런타임 오류가 발생한다. `queue._interface.py`의 `publish()` 시그니처를 확인하고 `evaluation/main.py`도 `Message(...)` 래퍼를 사용하도록 통일을 권고한다.

---

## 통과 항목

### 응답 코드 처리 (3.2절)

| 항목 | 결과 | 위치 |
| --- | --- | --- |
| `00` + 0행 → `OK_EMPTY` | ✓ | `_parser.py:102, 156, 173, 194` (4개 경로) |
| `00` + 행 있음 → `OK` | ✓ | `_parser.py` |
| `12` → `NO_SERVICE` (폐기 아님) | ✓ | `_parser.py` `_CODE_MAP` |
| 빈 결과 코드 → `PARSE_FAILURE` | ✓ | `_parser.py:_classify()` |
| HTTP 오류·연결 실패 코드 처리 | ✓ | `_parser.py` + `http/_client.py` |

### DB 제약 (repository skill ③-2)

| 항목 | 결과 | 위치 |
| --- | --- | --- |
| ENUM 없음 — VARCHAR + CHECK 사용 | ✓ | `tables.py` 전체 |
| JSONB 연산자 없음 — JSON은 저장·통째 조회만 | ✓ | `tables.py` `flags`, `season_months` 컬럼 |
| 배열 타입 없음 | ✓ | `tables.py` 전체 |
| DB 문자열 비교 없음 — Python에서 정규화 키로 처리 | ✓ | `sql.py` |
| `_utc` 접미 datetime 컬럼 | ✓ | `tables.py` 전체 |
| 마이그레이션 코드 없음 | ✓ | 저장소 전체 |

### 방언 격리

| 항목 | 결과 | 위치 |
| --- | --- | --- |
| 방언 분기 `dialect.py` 밖 없음 | ✓ | `dialect.py` 단독 처리 |
| `_upsert_pg` / `_upsert_my` 분기 | ✓ | `dialect.py` |

### 보안·키 관리

| 항목 | 결과 | 위치 |
| --- | --- | --- |
| API 키 마스킹 — `url`, `params`, `final_url` | ✓ | `http/_client.py:_mask_key()` |
| 인증 키 로그 미출력 | ✓ | 코드 전체 |

### 계약·설정

| 항목 | 결과 | 위치 |
| --- | --- | --- |
| 계약 버전 불일치 시 `SystemExit` | ✓ | `contract_check/_checker.py` |
| 운영 조정 ConfigMap 없으면 `SystemExit` | ✓ | `common/config/_operational.py:32` |
| 운영 조정 스키마 불일치 시 `SystemExit` | ✓ | `common/config/_operational.py:52` |
| `<미결>` 기본값 채움 없음 | ✓ | `_operational.py`, `_do.py`, `_chlorophyll.py`, `_red_tide.py`, `_filter.py`, `interpolation/main.py` |
| 판정 정의 이미지 포함, 운영 조정 이미지 미포함 | ✓ | 5개 `Dockerfile` 전체 |

### 단계 간 교차 import 금지 (금지 규칙)

| 항목 | 결과 |
| --- | --- |
| `collector` → 타 단계 import 없음 | ✓ |
| `processor` → 타 단계 import 없음 | ✓ |
| `interpolation` → 타 단계 import 없음 | ✓ |
| `grading` → 타 단계 import 없음 | ✓ |
| `evaluation` → 타 단계 import 없음 | ✓ |
| 공유 코드 `common/`에만 위치 | ✓ |

### 불변식 (4.8절, CLAUDE.md 7절)

| 항목 | 결과 | 위치 |
| --- | --- | --- |
| N11: `derivation=COMPUTED` → `alertable=False` | ✓ | `grading/main.py:417` (명시 주석 포함) |
| `provenance=NONE` 시에도 `value` 저장 | ✓ | `grading/_water_temp.py` — `ERROR_ABOVE_LIMIT`에서도 lower/upper 보존 |
| NONE → 최근접값 대체 없음 | ✓ | `evaluation/_state.py`, 추정 중단 시 `NONE` 유지 |

### grading 핵심 규칙 (4.7·4.8절)

| 항목 | 결과 | 위치 |
| --- | --- | --- |
| `excluded_zones`: `center_lat`/`center_lng` 필드명 일치 | ✓ | `grading/_zone.py`, `definitions.yaml` (수정 반영) |
| `estuary_stations` → NEAREST_TIDE 분기에서 `NONE/EXCLUDED_ZONE` | ✓ | `grading/main.py:165-168` |
| `STATION_INACTIVE` — DB `active` 필드 기준 | ✓ | `grading/_nearest.py` |
| 적조 `alertable` — 예비특보 이상 or UNKNOWN | ✓ | `grading/_red_tide.py:128` |

### CI·Docker (2.0.2·2.0.5·7.6절)

| 항목 | 결과 | 위치 |
| --- | --- | --- |
| CI: 이미지 알림만 전송, manifest 커밋·PR 없음 | ✓ | `.gitlab-ci.yml` notify 단계 |
| 레지스트리 주소 코드·매니페스트 없음 — `REGISTRY` CI 변수만 | ✓ | `.gitlab-ci.yml:99` |
| `evaluation` 이미지에 `fixtures/synthetic/` 포함 | ✓ | `docker/evaluation/Dockerfile` |
| 각 이미지에 해당 단계 코드만 복사 | ✓ | 5개 `Dockerfile` 전체 |
| 게이트 ①: `definitions.yaml` ↔ `expected.yaml` 대조 | ✓ | `ci/gate/run_gate.py:_check_definitions()` |
| 게이트 ①′: 운영 조정 스키마·판정 재생 | ✓ | `ci/gate/run_gate.py:_check_operational()` |
| 게이트 ②: 픽스처 건수 보존 pytest | ✓ | `tests/gate/test_counts.py` |

### 수집·가공 (2.1·3절)

| 항목 | 결과 | 위치 |
| --- | --- | --- |
| collector에서 판정 없음 — 원문·메타만 저장 | ✓ | `collector/main.py` |
| 원문 자르거나 재직렬화 없음 | ✓ | `collector` 어댑터 |
| 빈 값 레코드 버리지 않음 — `missing_reason='MISSING'`으로 저장 | ✓ | `processor/adapters/line/_adapter.py:141`, `fishery/_adapter.py:138` |
| `0.000` 결측 처리 — `ZERO_SENTINEL` (수온·염분만, 클로로필 제외) | ✓ | `processor/adapters/fishery/_adapter.py:144` |
| 좌표 폐구간 검증 — 경계값(33.0) 포함 | ✓ | `common/geo/_coords.py`, `expected.yaml:soo_v2.south_lat33_kept=523` |

### 보간 (4.7절)

| 항목 | 결과 | 위치 |
| --- | --- | --- |
| `SENSOR_QUALITY` 플래그 → IDW 입력 제외 | ✓ | `interpolation/_filter.py:44` |
| LOOCV 동일 station_id 중복 제거 | ✓ | `interpolation/_loocv.py:72` (주석: "1차 IDW 실험 함정") |
| `exclude_flatline` 미결 시 `None` — 대체 없음 | ✓ | `interpolation/_filter.py:46` (None이면 조건 미적용) |

---

## 계획서 반영 후보

다음 항목은 `*(제안)*` 또는 현재 구현 방식이 계획서에 미반영된 것으로, 계획서 개정 논의가 필요하다.

1. **soo_v2 `south` / `empty_value_dropped` 건수 테스트 미구현**  
   `tests/gate/test_counts.py`에서 `test_south_count`와 `test_empty_value_dropped`가 `pytest.skip()`으로 처리되어 있다. 이유는 어댑터가 `_region` 메타를 외부에 노출하지 않기 때문이다. `expected.yaml`에 `south: 2584`, `empty_value_dropped: 739`가 기준값으로 있으나 자동 검증이 없다. 어댑터 계약에 `_region` 필드 추가 또는 기준 문서에서 해당 건수 제거를 계획서에 반영해야 한다.

2. **`evaluation/main.py` `queue.publish()` 인수 — `Message` 래퍼 미사용 (W-3과 연동)**  
   W-3의 타입 불일치를 `_interface.py` 시그니처 수준에서 강제하려면 프로토콜 정의 수정이 필요하다. 이 결정이 계획서의 큐 계약(queue-v1) 범위에 포함되는지 확인 후 반영한다.

---

## 미결 항목 현황 (점검 시점 기준)

운영 투입 전에 결정이 필요한 `<미결>` 목록. 값 채움은 이 보고서 범위 밖이며, 결정 권한자가 별도 절차로 진행한다.

| 키 | 파일 | 비고 |
| --- | --- | --- |
| `tide.flatline_minutes` | `operational.initial.yaml` | — |
| `stale_threshold_hours.tide_level` | `operational.initial.yaml` | — |
| `stale_threshold_hours.wind_speed` | `operational.initial.yaml` | — |
| `stale_threshold_hours.air_temp` | `operational.initial.yaml` | — |
| `stale_threshold_hours.dissolved_oxygen` | `operational.initial.yaml` | I-4 0m DO 집계 보고 후 결정 |
| `evaluation.interpolation_stale_minutes` | `operational.initial.yaml` | — |
| `evaluation.grading_stale_minutes` | `operational.initial.yaml` | — |
| `bulletin.current_window_days` | `definitions.yaml` | 4.8절 유효 기간 |
| `line.surface_rule` | `definitions.yaml` | DO 표층 규칙 — 결정 전 `SURFACE_RULE_UNDECIDED` |
| `interpolation.exclude_flatline` | `definitions.yaml` | — |
| `interpolation.error_window_days` | `definitions.yaml` | 교차검증 결과 보기 전 필요 |
| `grading.line_max_distance_km` | `definitions.yaml` | DO 정점 거리 한계 |
| `grading.fishery_max_distance_km` | `definitions.yaml` | 클로로필 정점 거리 한계 |

---

## 긴급 조치 항목

| 순서 | 항목 | 파일 | 영향 |
| --- | --- | --- | --- |
| 1 | V-1 수정: `PROVENANCE_VALS`에 `"BASELINE"` 추가 | `tables.py:41`, `expected.yaml` | DO·클로로필 upsert 전면 실패 |
| 2 | W-1 수정: `datetime.utcnow()` → `datetime.now(timezone.utc).replace(tzinfo=None)` | `evaluation/main.py:23` | Python 3.13 대비 |
| 3 | W-3 확인: `evaluation` `queue.publish()` 인수 타입 통일 | `evaluation/main.py` | 운영 큐 적용 시 실패 가능 |

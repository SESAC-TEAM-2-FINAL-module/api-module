# I-1 결과

지시서: common-core 구현  
실행일: 2026-09-28  
참조 skill: `common-core` (`.claude/skills/common-core/SKILL.md`)

---

## 0. 실행 환경

| 항목 | 값 |
|---|---|
| Python | 3.13.9 |
| httpx | 0.27.2 |
| PyYAML | 6.0.3 |
| pytest | (conda 기본) |
| 수정사항 | 없음 |
| 커밋 해시 | 미커밋 (사용자 대기 중) |

이식 출처 확인:
- `$SRC_C/probe.py` — 수정사항 4 적용본 확인 (ParsedResponse, _classify 등 이식 대상 전부 확인)
- `$SRC_IDW/src/normalizer.py` — B 수정본 확인 (`validate_coords_closed` 폐구간, `validate_coords` 사용 금지)
- `$SRC_IDW/src/collector.py` — B 수정본 확인 (`save_raw_response()` 절단 없음. `[:100000]`은 `_save_parse_failure()`에만 존재 — 이식 대상 아님)
- `$SRC_API/verify_nifs_api.py` — `DMS_RE`, `dms_to_decimal()` 이식 대상 확인

---

## 1. 판정표

### 음성 입력 (7.2절)

| # | 검사 | 결과 |
|---|---|---|
| N1 | `{"foo": {"bar": 1}}` → `PARSE_FAILURE` | **통과** |
| N2 | `response.header{}` resultCode 없음 → `PARSE_FAILURE` | **통과** |
| N3 | `resultCode: ""` → `PARSE_FAILURE` | **통과** |
| N4 | `totalCount: 5`, item 0개 → `PARSE_FAILURE` | **통과** |
| N5 | `OpenAPI_ServiceResponse` + `returnReasonCode: 05` → `TIMEOUT_05` | **통과** |
| N6 | `resultCode: 12` → `NO_SERVICE`, 폐기 판정 없음 | **통과** |
| N7 | 필터 창 2024년 요청, 1997년 행 반환 → `FILTER_IGNORED` | **통과** |
| N12 | 분할 합산 — 비교 범위 다른 두 결과 → `COMPARISON_RANGE_MISMATCH`, 절단·INCOMPLETE 아님 | **통과** |
| N13 | 분할 합산 — 범위 일치 후 분할 합 < 단일 창 → `INCOMPLETE` | **통과** |

### 판정 규칙 검사 (7.8절)

| # | 검사 | 결과 |
|---|---|---|
| Q1 | R3 물리 범위 — 수온 −0.5·35.5만 `SENSOR_QUALITY`, 경계값 0.0·35.0은 정상 | **통과** |
| Q2 | R4 급변 — +5.5℃만 `SENSOR_QUALITY`, 태풍 특보 중 면제, +4.9℃ 정상 | **통과** |
| Q3 | R1 생물부착 — 정선·어장환경 30.9만 `SENSOR_QUALITY`, 하구 예외·dtRecent 제외 | **통과** |
| Q4 | R2 클로로필 급변 — max 초과 + delta 초과 조건 둘 다여야 `SENSOR_QUALITY` | **통과** |
| Q5 | 값 멈춤 감지 (R4 STALE_SUSPECT) | **실행 안 함** — `tide` skill 소유 (S3). 이 skill 범위 밖 |
| Q6 | adapter_health 갱신 — 순서별 last_success_utc·consecutive_failures·retry_recovered | **통과** |

### 기동 시 검사 (7.6절)

| # | 검사 | 결과 |
|---|---|---|
| B3 | 계약 버전 불일치 시 처리 안 하고 운영 이벤트 | **실행 안 함** — I-10에서 동작 확인 (SKILL.md ① 명시) |
| B4 | 결과 테이블 계약이 DB와 다른 상태로 기동 → 멈춤 | **실행 안 함** — I-10에서 동작 확인 |
| B6 | ConfigMap 없음·키 누락·모르는 키·미결 자리 표시·버전 불일치 → 각각 기동 멈춤 | **통과** (5개 케이스 모두 `SystemExit`) |
| B8 | 기동 성공 시 설정 해시 반환 | **통과** |

**전체 단위 테스트: 72/72 통과**

---

## 2. 예상과 달랐던 결과

### API 특성
없음. 이번 지시서는 실제 API를 호출하지 않는 구현 단계.

### 우리 코드·명세 결함

| 항목 | 내용 |
|---|---|
| `_classify()` 맵 누락 | `probe.py` 원본에 `22`(QUOTA), `41`(SUSPENDED)가 없었다. CLAUDE.md 6절 상태 이름표에 두 코드가 명시되어 있어 이식 시 추가. |
| `_definitions.py` 경로 depth | 초기 작성 시 `parents[5]`로 썼으나 실제 depth가 `parents[4]`. 테스트 전 확인·수정. |
| `docs/plan_report/` 디렉토리 | 계획서에는 `docs/reports/`로 표기, 사용자가 `docs/plan_report/`로 요청 — 요청 경로로 생성. |

---

## 3. 새로 발견한 함정

1. **`_parse_json`의 공단 JSON 계열**: 루트 키가 오퍼레이션명이고 그 안에 `header.code`가 있다. `for key, val in data.items()` 루프로 탐색하되, 이 계열에 `header`가 없는 다른 딕셔너리(예: `"version": "1.0"`)가 루트에 섞이면 오탐 가능. 확정 4종은 모두 JSON이므로 실제 도달 경로가 없으나, 향후 원천 추가 시 주의 필요.

2. **`validate_coords_closed`의 기본값 하드코딩**: 파라미터에 기본값 `(33.0, 39.0)`, `(124.0, 132.0)`을 두었다. 판정 정의에서 읽어야 하는 값이 기본값으로 남아 있어, 어댑터가 실수로 기본값을 쓰면 정의 변경이 반영되지 않는다. 어댑터(I-2~I-5)에서 반드시 `load_definitions()`로 읽은 범위를 주입해야 한다.

3. **`processor/main.py` 적재 미구현**: DB 접근 계층(`repository` skill, I-6) 인터페이스 호출 자리에 주석만 두었다. `adapter_health` 갱신, `ingest_runs` 중복 방지(같은 `raw_id::parser_version`)도 마찬가지. I-6 이전에는 적재가 동작하지 않는다.

4. **`_raw_key()`의 `fetched_at` 포맷 의존**: `save_raw()`는 `fetch_result["fetched_at"]`이 `%Y-%m-%dT%H:%M:%S` 형식임을 전제한다. `http/_client.py`와 포맷을 맞춰 두었으나, 외부에서 다른 포맷으로 생성한 raw 결과를 넣으면 `ValueError`가 발생한다.

---

## 4. 계획서 반영 후보

### 구현한 *(제안)* 항목

| 항목 | 절 | 내용 |
|---|---|---|
| `TIMEOUT_05` 재시도 복구 → `retry_recovered`만 증가, 실패 카운트 제외 | ③-11 | 구현 및 Q6 테스트로 확인 |
| `NO_SERVICE`·`KEY_ERROR`·`QUOTA`·`INCOMPLETE`·`FILTER_IGNORED` → adapter_health "어느 쪽도 아님" | ③-11 | 구현 (성공도 실패도 아닌 분류) |
| `interpolation-error` 워크로드 언급 | 2.2절 *(제안)* | `collector/main.py` 워크로드 목록에 포함 가능 — I-11에서 확정 |

### 만난 `<미결>` 항목

| 항목 | 절 | 현재 처리 |
|---|---|---|
| 하구 예외 정점 목록 (R1 적용 제외 — 섬진강하구 등) | 4.6절, 11절 | `_ESTUARY_STATIONS: set[str] = set()` 빈 집합. 테스트는 합성 목록으로 주입 |
| 태풍 특보 입력 원천 (R4 급변 면제 플래그) | 4.6절, 11절 | `_TYPHOON_ACTIVE: bool = False`. 테스트는 합성 플래그로 주입 |
| 운영 조정 `dtRecent` 축 최장 갱신 간격 15.4분 미만 거부 하한 | 2.0.6절 *(제안)* | 스키마 검사에 하한 조건 미포함. 스키마 파일(`contracts/config/operational.schema.json`)은 I-10 몫 |
| 원문 저장 위치 최종 결정 (S3/GCS vs 로컬 디스크) | 2.3절 | `LocalDiskStore` 기본 구현, `RawStore` 인터페이스로 교체 가능 |

### 참조한 skill 및 커밋

- `.claude/skills/common-core/SKILL.md` (커밋 해시: 미커밋)

---

*이식 기록 전체: `docs/SOURCES.md`*

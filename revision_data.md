# 계획서 반영 후보 누적 로그

I-1~I-4 실행 중 발견한 "계획서 반영 후보" 항목을 누적한다.
계획서 개정 시 이 목록을 참조해 해당 항목을 반영하거나 폐기한다.

상태: `대기` = 개정 전 / `반영` = 계획서에 포함됨 / `폐기` = 논의 후 채택 안 함 / `해결됨` = 코드·문서 단에서 수정 완료

---

## I-1 (common-core, 2026-09-28)

### 구현한 *(제안)* 항목

| 항목 | 절 | 내용 | 상태 |
|---|---|---|---|
| TIMEOUT_05 재시도 복구 시 `retry_recovered`만 증가, 실패 카운트 미포함 | ③-11 | 구현 및 Q6 테스트 확인 | 대기 |
| `NO_SERVICE`·`KEY_ERROR`·`QUOTA`·`INCOMPLETE`·`FILTER_IGNORED` → adapter_health "어느 쪽도 아님" 분류 | ③-11 | 구현 | 대기 |
| `interpolation-error` 워크로드를 collector/main.py 워크로드 목록에 포함 가능 | 2.2절 *(제안)* | I-11에서 확정 예정 | 대기 |

### 만난 `<미결>` 항목

| 항목 | 절 | 현재 처리 |
|---|---|---|
| 하구 예외 정점 목록 (R1 적용 제외 — 섬진강하구 등) | 4.6절, 11절 | `_ESTUARY_STATIONS = set()` — 내용 미결 |
| 태풍 특보 입력 원천 (R4 급변 면제 플래그) | 4.6절, 11절 | `_TYPHOON_ACTIVE = False` — 내용 미결 |
| 운영 조정 `dtRecent` 축 최장 갱신 간격 하한(15.4분 미만 거부) | 2.0.6절 *(제안)* | 스키마 검사에 하한 조건 미포함 |
| 원문 저장 위치 최종 결정 (S3/GCS vs 로컬 디스크) | 2.3절 | `LocalDiskStore` 기본 구현, 인터페이스 교체 가능 |

---

## I-2 (tide adapter, 2026-09-28)

### 새 *(제안)* 등록 요청

| 항목 | 내용 | 상태 |
|---|---|---|
| `check_completeness` 단위 정의 | dtRecent는 totalCount = 관측 시점 수. metric 분해 후 rows ≠ totalCount — "수령 건수 대조" 단위(collector 기준 / processor 기준) 명시 필요 | 대기 |
| 다중 페이지 원문 합산 정책 | 여러 HTTP 응답 합산 시 "재직렬화 금지" 규칙 적용 여부 명시 필요 | 대기 |

### 만난 `<미결>` 항목

| 항목 | 절 | 현재 처리 |
|---|---|---|
| `tide.flatline_minutes` | 4.1절, 11절 | 운영 조정에서 읽음. 값 없으면 플래그 미적용 |
| `interpolation.exclude_flatline` | 4.1절 | 플래그만 달고 적용은 `interpolation` 담당 |

### 미해결 코드·정책 결함 (I-6 이후 보완 예정)

| 항목 | 내용 |
|---|---|
| `STATION_INACTIVE` 판정 범위 | 현재 단일 수집 결과 내에서만 최근 24h 판단. 이전 수집 데이터 없으면 INACTIVE 판정 불가 — I-6 DB 이후 보완 |

---

## I-3 (bulletin adapter, 2026-09-28)

### 새 *(제안)* 등록 요청

| 항목 | 내용 | 상태 |
|---|---|---|
| `unmapped_locations` 적재 시점 정책 | normalize() 중 미매핑 지점을 현재 stderr로만 로그. I-6 이후 DB 적재 전환 시 인터페이스 정책 명시 필요 | 대기 |

### 만난 `<미결>` 항목

| 항목 | 절 | 현재 처리 |
|---|---|---|
| 시드 내용 (`areas`·`area_aliases`·`axis_coverage`) | 5.3절, 11절 | 형식·로딩 코드만. 내용 비움 |
| `bulletin.current_window_days` | 4.8절 | `grading` 담당. 미처리 |

---

## I-4 (line adapter, 2026-09-29)

### 새 계획서 반영 후보

| 항목 | 내용 | 상태 |
|---|---|---|
| `obs_dtm` 시간대 직접 확인 경로 | IDW 코드 KST 취급하나 API 공식 문서 미확인. 직접 확인 방법 또는 공식 명시 필요 | 대기 |
| `cast_rule_version` 형식 명시 | `f"x{cast_gap_minutes}"` 형식 채택 (`x60`). 계획서 11절에 정의 요청 | 대기 |
| SKILL.md ④ 파일명 오기 수정 | `line_depth_collect.py` → `line_depth_collect_v2.py` | **해결됨 (2026-09-29)** |

### 만난 `<미결>` 항목

| 항목 | 절 | 현재 처리 |
|---|---|---|
| `line.surface_rule` | 4.4절, 11절 | `<미결>` 유지. `grading`이 읽을 때 적용 |
| `line.cast_gap_minutes` | 4.4절, 11절 | 현재 60 — 결정 대기. `cast_rule_version="x60"` |
| `stale_threshold_hours.dissolved_oxygen` | 4.9절 | DO 마지막 유효 2025-11-07. evaluation skill 소유 |

---

---

## I-5 (fishery = femoSeaList, 2026-09-29)

### 구현한 *(제안)* 항목

해당 없음.

### 만난 `<미결>` 항목

해당 없음 — 이번 지시서 범위에서 미결 설정 키 없음.

### 계획서 반영 후보

| 항목 | 내용 | 상태 |
|---|---|---|
| 게시 감시 `prev_count=None` 시 동작 명시 | I-5 스텁에서는 매 실행 전량 수집. I-6 DB 연동 후 delta 비교로 전환. 계획서에 명시 없음 | 대기 |
| chlorophyll R0 제외 근거 명시 | SKILL.md fishery에 R0 대상 `water_temp`·`salinity`만 있음. 클로로필 0.0 유효값 여부 계획서 4.6절에 명시 없음 | 대기 |

---

*갱신: I-5 완료 시점 (2026-09-29)*

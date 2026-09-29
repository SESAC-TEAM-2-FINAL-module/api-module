# I-2 결과

지시서: tide adapter 구현  
실행일: 2026-09-28  
참조 skill: `tide` (`.claude/skills/tide/SKILL.md`)

---

## 0. 실행 환경

| 항목 | 값 |
|---|---|
| Python | 3.13.9 |
| httpx | 0.27.2 |
| PyYAML | 6.0.3 |
| pytest | 8.3.3 |
| 커밋 해시 | 미커밋 (사용자 대기 중) |

이식 출처 확인:
- `$SRC_IDW/stage2_collect.py` — B 수정본 확인 (`_fetch_all_pages()` 절단 코드 없음, `_save_raw()` 사용 금지)
- `$SRC_IDW/stage1_verify.py` — 필드명(`bscTdlvHgt`, `wspd`, `artmp`, `wdir`) 확인
- `$SRC_IDW/output/observations.csv` — `obsrvnDt` KST naive 확인 (시각 형식 `YYYY-MM-DD HH:MM:SS`, timezone 없음)

---

## 1. 판정표

### 검사 항목

| # | 규칙 (절) | 입력 | 통과 기준 | 결과 |
|---|---|---|---|---|
| Q5 (전) | 값 멈춤 감지 (4.1) | 같은 값이 `tide.flatline_minutes` 직전까지 | 플래그 없음 | **통과** |
| Q5 (후) | 값 멈춤 감지 (4.1) | 같은 값이 `tide.flatline_minutes` 도달 | `STALE_SUSPECT` | **통과** |
| R0 | 0.000 결측 | water_temp·salinity = `0.0` | `ZERO_SENTINEL` | **통과** |
| R0 경계 | 0.000 비적용 | tide_level·wind_speed·wind_dir·air_temp = `0.0` | 정상값 | **통과** |
| KST→UTC | obsrvnDt 변환 | `09:00 KST` → `00:00 UTC` | `-9h` | **통과** |
| interpret | 행 분해 | item 1개 | 6개 metric 행 | **통과** |
| station_id | 접두어 | obsCode `DT_0016` | `tide:DT_0016` | **통과** |
| INACTIVE (전) | 관측소 미가동 | 최근 24h 내 정상 값 있음 | `station_inactive` 없음 | **통과** |
| INACTIVE (후) | 관측소 미가동 | 최근 24h 전 행 모두 결측 | `station_inactive=True` | **통과** |
| INACTIVE 독립 | 관측소별 | DT_0049 결측, DT_0016 정상 | 각각 독립 판정 | **통과** |

**단위 테스트: 27/27 통과 (F11 2건 skip — 로컬 수동 전용)**

### F11 검사 (CI 게이트 밖)

| 검사 | 기준 | 실행 방법 |
|---|---|---|
| DT_0049·DT_0092 전 기간 STATION_INACTIVE | 90일 전체 `0.000` | `IDW_OUTPUT_DIR=$SRC_IDW/output pytest -k F11` |
| DT_0061 염분 최장 연속 결측 ≥ 518분 | 518분 이상 | 위와 동일 |

S12에서 재실행 후 `docs/reports/`에 기록 예정.

---

## 2. 예상과 달랐던 결과

### API 특성

| 항목 | 내용 |
|---|---|
| `obsrvnDt` 시간대 | KST naive 확인. 계획서에 "추정하지 않는다 — 원문으로 확인" 지침. `stage2_collect.py`의 `parse_dt()`와 `observations.csv` 시각 패턴으로 KST 확인, `SOURCES.md`에 기록. |
| `wdir` 풍향 | `stage1_verify.py`에서 필드명 확인. SKILL.md ③-3에 `wind_dir`로 열거되어 있으나 필드명은 `wdir`. |

### 우리 코드·명세 결함

| 항목 | 코드 상태 | 내용 |
|---|---|---|
| completeness 불일치 | **해결됨 (2026-09-29)** | `check_completeness`에 `actual_items: int \| None` 파라미터 추가. `processor/main.py`에서 `actual_items=len(pr.items)` 전달 — items 단위로 totalCount 비교. rows(metric 분해 후)는 비교 기준에서 제외. |
| 다중 페이지 body 구성 | **미해결 — 알려진 규칙 충돌** | 페이지가 2개 이상일 때 synthetic body를 구성하므로 "원문 재직렬화 금지" 규칙과 충돌. 폴링 방식(numOfRows=300)에서 단일 페이지가 대부분이라 실제 발동 빈도는 낮으나 정책 미결. 계획서에 다중 페이지 합산 정책 명시 요청 등록. |

---

## 3. 새로 발견한 함정

1. **`interpret()` rows 수와 `pr.total_count` 단위 불일치** (**해결됨 — 2026-09-29**): `check_completeness`에 `actual_items` 파라미터 추가. `processor/main.py`에서 `len(pr.items)` 주입으로 items 단위 비교 확립.

2. **`STATION_INACTIVE` 판정 범위** (**미해결 — I-6 이후 보완 예정**): 현재 normalize()는 단일 수집 결과의 rows 내에서 최근 24h를 판단한다. 이전 수집의 데이터가 없으면 INACTIVE를 판정하지 못한다. DB 접근 계층(I-6)이 구현된 후 이전 rows를 쿼리해서 보완해야 한다.

3. **`_apply_flatline_flags`의 정렬 비용** (**알려진 제한 — 운영 범위 내 허용**): `rows` 전체를 station×metric별로 groupby한 뒤 각 그룹을 시각순 정렬한다. 대용량(90일치) rows를 한 번에 처리하면 메모리·CPU 부하가 크다. F11 테스트는 로컬 수동 실행이므로 현재 허용범위. 운영에서는 10분 폴링 단위이므로 rows 수가 작아 문제 없음.

4. **`tide_level = 0.0`** (**코드에 반영 완료**): 조위 0.0은 실제로 "조위가 0m"일 수 있다. `_ZERO_SENTINEL_METRICS`에서 tide_level 제외하여 정상값으로 처리. SKILL.md R0 "수온·염분·pH에 적용"을 따름.

---

## 4. 계획서 반영 후보

### 구현한 *(제안)* 항목

없음.

### 만난 `<미결>` 항목

| 항목 | 절 | 현재 처리 |
|---|---|---|
| `tide.flatline_minutes` | 4.1절, 11절 | `_load_flatline_minutes()`로 운영 조정에서 읽음. 값 없으면 플래그 미적용. 테스트는 절댓값이 아닌 상대값으로 설계. |
| `interpolation.exclude_flatline` | 4.1절 | SKILL.md에 따라 플래그만 달고 적용은 `interpolation` 담당. |

### 새 *(제안)* 등록 요청

| 항목 | 내용 |
|---|---|
| `check_completeness` 단위 정의 | dtRecent는 totalCount = 관측 시점 수. 어댑터가 metric별로 분해하면 rows 수 ≠ totalCount. "수령 건수 대조"가 어떤 단위인지 명시 필요 (collector 기준 / processor 기준 구분). |
| 다중 페이지 원문 합산 정책 | 여러 HTTP 응답을 합산해 단일 raw로 저장할 때 "재직렬화 금지" 규칙 적용 여부 명시 필요. |

### 참조한 skill 및 커밋

- `.claude/skills/tide/SKILL.md` (커밋 해시: 미커밋)

---

*이식 기록 전체: `docs/SOURCES.md`*

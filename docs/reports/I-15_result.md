# I-15 결과 보고서 — 해역 시드 운영 적재

작성 2026-10-02 · 실행자: aquasentinal-api-module-impl 세션

---

## 0. 실행 전 확인

| 항목 | 결과 |
|---|---|
| `CLAUDE.md`, skill 파일, 계획서 | 작업 트리 존재 확인 |
| Docker Desktop | 켜짐 확인 (`docker info` 응답) |
| 기준선 pytest | **543 passed · 14 skipped** (작업 시작 전) |
| `.env` / 로컬 배치 | 파일 내용 출력 없이 존재 확인 |

---

## 1. 판정표

| # | 검사 | 결과 | 비고 |
|---|---|---|---|
| SD1 | 빈 시드 기동 검사 (DB) | **통과** | `check_seed_tables` 5개 테스트 — areas/axis_coverage 0행 → SystemExit, 시드 적재 후 통과 |
| SD2 | 생성본 적용 (DB) | **통과** | PG 생성본 적용 결과 = `load_seeds` 결과 (행 단위), 임시 행 DELETE 검증, FK 없어 참조 행 존재해도 오류 없음. MySQL 생성본은 내용 있음 확인 |
| SD3 | seed-check (DB) | **통과** | 일치 DB → 종료 0. 값 변경·행 삭제·추가 행·별칭 참조 오류·커버리지 참조 오류·유효 기간 안 BDA area_id 오류 → ①②③ 보고. 유효 기간 밖·경계(cutoff-1) → ③ 통과 |
| SD4 | 시드 파일·생성본 (DB 없음) | **통과** | `contracts/tables/seeds_pg.sql`·`seeds_my.sql` = 신선 생성기 출력(바이트 단위). area_aliases·axis_coverage area_id ⊂ areas.yaml |
| 판별력 | — | **확인** | SD1: 빈 repo에서 `check_seed_tables` → SystemExit 확인. SD3: `compare_seed_tables` 변경 행 검출 확인. SD4: 생성본 한 줄 수정 → 신선 생성과 불일치 확인 |
| 회귀 | — | **통과** | `pytest` 566 passed · 14 skipped (+23). 게이트 통과. `scan_keys.py` 0건 |

---

## 2. 예상과 달랐던 결과

- **`_adapter.py`의 `_SEEDS_DIR` 제거로 인한 기존 테스트 깨짐**: `tests/unit/test_bulletin_processor.py::TestSeedsStopInsteadOfEmpty`가 `ad._SEEDS_DIR`를 monkeypatch하고 있었다. 리팩토링으로 `_SEEDS_DIR`가 `common.seeds`로 이동했으므로, monkeypatch 대상을 `common.seeds._SEEDS_DIR`로 변경. 기존 동작(RuntimeError 발생) 유지됨.
- **DB FK 제약 없음**: `area_aliases.area_id` → `areas.area_id`에 FK 제약이 tables.py에 선언되지 않아, DELETE 순서가 실제로 무관하다. SD2 "지운 행이 다른 표에서 참조돼도 오류 없이"는 FK 제약 부재로 자연히 충족. 지시서 조건 충족 확인.

---

## 3. 새로 발견한 함정

- `json.dumps([5, 6, 7, 8, 9, 10])` = `'[5, 6, 7, 8, 9, 10]'` (공백 포함). SQLAlchemy JSON 컬럼에서 읽어오면 Python list로 자동 역직렬화되므로, `_normalize_months`에서 문자열인 경우(MySQL 직접 읽기 등)를 위해 json.loads 처리 포함.
- `repr(float(34.740))` = `'34.74'` (trailing zero 제거). 결정적 출력 요건은 충족되나, SQL 가독성이 다소 떨어진다. 동작 영향 없음.

---

## 4. 계획서 반영 후보

### 구현한 *(제안)*
없음.

### 만난 `<미결>`
- `bulletin.current_window_days`: `_is_pending` 확인 → seed-check ③에서 미결이면 건너뜀 처리. 보고서 기록.

---

## 참조한 skill과 상태

| skill | 상태 |
|---|---|
| `common-core` | 작업 트리, 개정 19 반영본 |
| `repository` | 작업 트리, 개정 19 반영본 |
| `bulletin` | 작업 트리, 개정 19 반영본 |
| `grading` | 작업 트리, 개정 19 반영본 |
| `evaluation` | 작업 트리, 개정 19 반영본 |

---

## 변경 파일 목록

**신규**
- `src/api_module/common/seeds.py` — 시드 읽기·적재·대조 통합
- `src/api_module/common/contract_check/_seed_check.py` — `check_seed_tables`
- `contracts/tables/seeds_pg.sql` — PostgreSQL 시드 적용 SQL 생성본
- `contracts/tables/seeds_my.sql` — MySQL 8.0 시드 적용 SQL 생성본
- `tests/db/test_seed_check.py` — SD1·SD2·SD3 DB 테스트
- `tests/unit/test_seed_sql.py` — SD4 단위 테스트

**수정**
- `src/api_module/processor/adapters/bulletin/_seed.py` — `common.seeds` 위임
- `src/api_module/processor/adapters/bulletin/_adapter.py` — `_load_area_aliases` → `common.seeds.load_area_aliases_dict`
- `src/api_module/common/repository/dialect.py` — `generate_seed_sql_pg`, `generate_seed_sql_my` 추가
- `src/api_module/common/repository/__init__.py` — 새 generator 내보내기
- `src/api_module/common/repository/base.py` — `count_table_rows`, `get_bulletin_detail_areas_in_window` 추상 메서드 추가
- `src/api_module/common/repository/sql.py` — 두 메서드 구현
- `src/api_module/common/contract_check/__init__.py` — `check_seed_tables` 내보내기
- `src/api_module/grading/main.py` — `check_seed_tables(repo, ["areas"])` 추가
- `src/api_module/evaluation/main.py` — `check_seed_tables(repo, ["areas", "axis_coverage"])` 추가
- `src/api_module/processor/main.py` — `seed-check` 하위 명령 추가
- `handoff/HANDOFF.md` — 7절 빈 시드 검사 항목 추가, 7a절 신규
- `tests/unit/test_bulletin_processor.py` — monkeypatch 대상을 `common.seeds._SEEDS_DIR`로 변경

---

## 제안 커밋 메시지

```
feat(I-15): 해역 시드 운영 적재 — SQL 생성본·빈 시드 기동 검사·seed-check (개정 19)

- common/seeds.py: 시드 읽기·적재·대조 로직 통합 (processor.adapters.bulletin에서 이동)
- common/repository/dialect.py: generate_seed_sql_pg/my() 추가
- contracts/tables/seeds_pg.sql, seeds_my.sql: 시드 적용 SQL 생성본 (DB 소유 측 적용)
- common/contract_check/_seed_check.py: check_seed_tables() — 빈 시드이면 SystemExit
- grading/main.py: 기동 시 areas 빈 시드 검사
- evaluation/main.py: 기동 시 areas·axis_coverage 빈 시드 검사 (gate 제외)
- processor/main.py: seed-check 하위 명령 추가 (startup() 없이 DB 대조)
- handoff/HANDOFF.md: 7절 업데이트, 7a절 추가 (배포 선행 조건·변경 조항)
- tests/db/test_seed_check.py: SD1·SD2·SD3
- tests/unit/test_seed_sql.py: SD4 (DB 없음)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

---

## 5. 검수 (2026-10-02, 지시 세션 — 수정 반영)

구현 세션 보고(566 passed · 14 skipped, 게이트 통과, scan_keys 0건)를 다시 실행해 같은 결과를 확인한 뒤, 지시서 1~6과 계획서 4.3·7.4 기준으로 코드를 읽었다.

| # | 지적 | 조치 |
| --- | --- | --- |
| R1 | 시드 해시가 파일 바이트 그대로 — 저장소가 `core.autocrlf=true`라 다른 Windows 체크아웃(CRLF)에서 해시가 달라져 SD4가 실패한다 | 해시를 줄바꿈 LF로 맞춘 내용으로 계산(`dialect.py` `_sha`) |
| R2 | 생성본을 `write_text`로 써 Windows에서 CRLF — DB 소유 측이 받는 바이트가 만든 OS마다 다르다. SD4는 텍스트 비교라 이를 못 잡았다 | LF 바이트로 쓰기(`write_bytes`), SD4를 줄바꿈만 맞춘 **바이트 비교**로, 생성 파일이 LF인지도 확인 |
| R3 | MySQL 생성본이 백슬래시를 이스케이프하지 않는다(기본 SQL 모드에서 이스케이프 문자) — 지시서 "방언에 맞게 이스케이프" | MySQL만 백슬래시를 두 번 쓴다(`_sq(..., backslash=True)`). 현재 시드에는 백슬래시가 없어 생성본 내용은 같다 |
| R4 | SD1 검사가 `check_seed_tables` 함수만 불렀다 — grading `main`·evaluation `evaluate`·`sweep`·`gate`·processor 기동이 실제로 그렇게 도는지는 보지 않았다(계획서 7.9절이 경계하는 부품 단위 검사) | `tests/db/test_seed_wiring.py` 신설 — 실제 진입점으로 SD1 6건(빈 `areas`·`axis_coverage`만 빈 경우·`gate`는 DB를 열지 않음·processor 기동·시드 후 기동). 판별력: grading 검사를 끄면 실패 확인 |
| R5 | `seed-check` 명령 자체(종료 코드·DB 쓰기 0건)를 본 검사가 없었다 | 같은 파일에 하위 프로세스 검사 2건 — 빈 DB 종료 1, 시드와 같은 DB 종료 0, 두 경우 모두 전 표 행 수 불변. 끝에 `[seed-check] 차이 N건` 한 줄 출력 추가, 쓰지 않는 `import os` 삭제 |
| R6 | `HANDOFF.md` 7a — 삭제 순서의 이유가 계획서와 다름("seed-check ② 통과"), 변경 조항이 "각 측이 재생성·재적용"(계획서: 모듈이 생성, DB 소유 측이 적용), `seed-check` 실행 위치가 저장소 기준 | 계획서 4.3절 근거(별칭이 DB에 없는 해역 → grading이 조용히 건너뜀, 재처리 불필요)로, 생성·적용 주체 구분, processor 이미지에서 실행·대조 항목 ①~③ 명시. 7절 머리에 4번 대상 이미지 |

검수 뒤: 전체 `pytest` **576 passed · 14 skipped**(+10 — SD1 진입점 6·`seed-check` 명령 2·SD4 바이트 비교 갱신), 게이트 통과, `scan_keys` 0건. 생성본 두 벌 재생성(LF, 내용 변화 없음).
